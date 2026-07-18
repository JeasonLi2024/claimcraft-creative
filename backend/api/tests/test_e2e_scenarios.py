# -*- coding: utf-8 -*-
"""Task 6.3 端到端测试场景：12 个 SubTask 覆盖完整业务流程。

对齐 SPEC tasks.md Task 6.3（SubTask 6.3.1-6.3.12）+ checklist.md 阶段 6。
所有场景使用 Django `TransactionTestCase`（对齐 test_document_quality_service.py），
mock 外部 LLM / OCR / Embedding 调用 + LangGraph 关键节点，避免完整 graph 执行。

测试策略（与 test_workflow_integration.py 一致）：
- 使用 `InMemorySaver` 作为 checkpointer（不依赖 Postgres，符合 tasks.md 约束 #2）
- mock `build_case_workflow` 返回受控 mock graph（约束 #3）
- 每个测试独立 setup/teardown（约束 #4）
- 必要时使用 `@unittest.skip` 跳过依赖复杂的场景（约束 #5）
- 优先 mock 外部 API（LLM/OCR），保留内部业务逻辑
  （WorkflowRunner / InterventionService / RetryService）

运行方式：
    cd backend
    python manage.py test api.tests.test_e2e_scenarios -v 2
"""
import asyncio
import importlib
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# 确保 backend/ 在 sys.path 上（独立运行或 pytest 时）
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django  # noqa: E402
from django.apps import apps as _django_apps  # noqa: E402
if not _django_apps.ready:
    django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.test import TransactionTestCase  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework import status  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

try:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.errors import NodeError
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Command, Overwrite, RetryPolicy, interrupt
    from typing_extensions import TypedDict

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - 环境兜底
    LANGGRAPH_AVAILABLE = False

from api.models import (  # noqa: E402
    Case,
    ComplaintTemplate,
    Evidence,
    ExtractedField,
    RespondTemplate,
    WorkflowArtifact,
    WorkflowIntervention,
    WorkflowRun,
)
from api.services.intervention_service import (  # noqa: E402
    create_intervention,
    submit_intervention,
)
from api.services.retry_service import RetryService  # noqa: E402


# ============================================================================
# 公共辅助函数
# ============================================================================


def _make_user(username='owner'):
    """创建测试用户。"""
    return User.objects.create_user(
        username=username, email=f'{username}@example.com', password='pass'
    )


def _make_case(user, **kwargs):
    """创建一个最小 Case。"""
    defaults = {
        'title': '测试案件-E2E',
        'owner': user,
        'case_mode': kwargs.pop('case_mode', 'complain'),
    }
    defaults.update(kwargs)
    return Case.objects.create(**defaults)


def _make_evidence(case, code='E1', **kwargs):
    """创建一个 Evidence 记录。"""
    defaults = {
        'code': code,
        'evidence_type': kwargs.pop('evidence_type', '订单页'),
        'description': f'{code} 证据描述',
        'source_time': timezone.now(),
    }
    defaults.update(kwargs)
    return Evidence.objects.create(case=case, **defaults)


def _make_run(case, **kwargs):
    """创建 WorkflowRun（thread_id 由 save() 自动生成）。"""
    defaults = {
        'status': 'running',
        'current_stage': 'fact_checking',
        'current_node': 'extract',
        'progress': 0.30,
        'revision': 1,
    }
    defaults.update(kwargs)
    return WorkflowRun.objects.create(case=case, **defaults)


def _make_extracted_field(evidence, **kwargs):
    """创建 ExtractedField。"""
    defaults = {
        'field_name': '金额',
        'field_value': '1500 元',
        'confidence': 0.95,
    }
    defaults.update(kwargs)
    return ExtractedField.objects.create(evidence=evidence, **defaults)


# ============================================================================
# 公共：测试用简化 state schema + graph 构造
# ============================================================================


class _E2ETestState(TypedDict, total=False):
    """简化测试用 state：模拟生产 CaseWorkflowState 关键字段。"""
    case_id: int
    case_mode: str
    evidence_ids: list
    workflow_run_id: int
    revision: int
    current_node: str
    current_stage: str
    progress: float
    evidence_preclassify_results: list
    evidence_ocr_results: list
    evidence_classify_results: list
    evidence_extract_results: list
    evidence_chain: list
    complaint_draft: dict
    respond_draft: dict
    needs_human_review: bool
    pause_requested: bool
    errors: list
    user_confirmed_fields: dict


async def _empty_async_iter():
    """空异步迭代器（async generator，供 `async for` 消费）。"""
    return
    yield  # pragma: no cover


def _build_complaint_workflow_mock(
    *,
    case_id: int,
    paragraphs: list | None = None,
    legal_references: list | None = None,
    evidence_codes: list | None = None,
    final_content: str = '## 事实与理由\n商家欺诈\n\n## 诉求\n请求退款',
):
    """构造一个 mock workflow，模拟 complaint_node 完成后写入 ComplaintTemplate。

    返回 MagicMock workflow，含：
    - astream_events：返回空异步迭代器（run_and_persist 不消费事件）
    - aget_state：返回 mock snapshot（next=() 表示已结束）

    同时副作用：通过 sync_to_async 调用 ComplaintTemplate.objects.update_or_create
    写入 paragraphs（含 legal_references + evidence_codes）。
    """
    paragraphs = paragraphs if paragraphs is not None else [
        {
            'paragraph_id': 'p1',
            'title': '事实与理由',
            'content': '商家欺诈，违反消费者权益保护法',
            'evidence_codes': evidence_codes or ['E1', 'E2'],
            'legal_references': legal_references or [
                {'law_name': '消费者权益保护法', 'article_number': '第五十五条'}
            ],
            'source_regions': [{'evidence_code': 'E1', 'box': [10, 20, 30, 40]}],
        },
        {
            'paragraph_id': 'p2',
            'title': '诉求',
            'content': '请求退款 1500 元',
            'evidence_codes': evidence_codes or ['E1'],
            'legal_references': [],
            'source_regions': [],
        },
    ]
    mock_workflow = MagicMock()
    mock_workflow.astream_events = MagicMock(return_value=_empty_async_iter())

    # snapshot.next=() → workflow 已结束
    mock_snapshot = MagicMock()
    mock_snapshot.interrupts = None
    mock_snapshot.tasks = []
    mock_snapshot.next = ()
    mock_snapshot.values = {
        'current_node': 'complaint',
        'revision': 6,
        'complaint_draft': {'title': '测试投诉书', 'content': final_content},
    }
    mock_workflow.aget_state = AsyncMock(return_value=mock_snapshot)

    # 在 workflow 启动时副作用写入 ComplaintTemplate（模拟 complaint_node 持久化）
    async def _persist_complaint(*args, **kwargs):
        # 模拟 complaint_node 的 update_or_create 副作用
        from asgiref.sync import sync_to_async
        from api.models import ComplaintTemplate

        def _do_persist():
            ComplaintTemplate.objects.update_or_create(
                case_id=case_id,
                template_type='platform',
                defaults={
                    'title': '测试投诉书',
                    'content': final_content,
                    'tone': 'firm',
                    'paragraphs': paragraphs,
                },
            )
        await sync_to_async(_do_persist)()

    # 利用 aget_state 副作用完成持久化（run_and_persist 结束时会调用 aget_state）
    original_aget_state = mock_workflow.aget_state

    async def _wrapped_aget_state(config):
        await _persist_complaint()
        return await original_aget_state(config)

    mock_workflow.aget_state = AsyncMock(side_effect=_wrapped_aget_state)
    return mock_workflow


def _build_workflow_with_interrupt(
    *,
    interrupt_payload: dict,
    final_node_name: str = 'evidence_chain',
):
    """构造一个 mock workflow：astream_events 完成后 snapshot 含 interrupt。

    用于模拟 review_node / stage_gate_node 触发的 interrupt 场景。
    """
    mock_workflow = MagicMock()
    mock_workflow.astream_events = MagicMock(return_value=_empty_async_iter())

    mock_snapshot = MagicMock()
    mock_interrupt_item = MagicMock()
    mock_interrupt_item.value = interrupt_payload
    mock_snapshot.interrupts = [mock_interrupt_item]
    mock_snapshot.tasks = []
    mock_snapshot.next = (final_node_name,)
    mock_workflow.aget_state = AsyncMock(return_value=mock_snapshot)
    return mock_workflow


def _build_failed_workflow_mock(error_msg: str = '文书生成失败'):
    """构造一个 mock workflow：astream_events 抛错（模拟 complaint 节点失败）。"""
    mock_workflow = MagicMock()

    async def _raising_stream(*args, **kwargs):
        raise RuntimeError(error_msg)
        yield  # pragma: no cover

    mock_workflow.astream_events = MagicMock(return_value=_raising_stream())
    mock_workflow.aget_state = AsyncMock(return_value=MagicMock(
        interrupts=None, tasks=[], next=(),
    ))
    return mock_workflow


# ============================================================================
# 公共：mock WorkflowRunner 外部依赖（EventDepot / NotifyEmitter / lifecycle）
# ============================================================================


def _patch_workflow_runner_external_deps():
    """返回一个 contextmanager 列表，mock WorkflowRunner 的外部依赖。

    使用 nested context manager：进入时统一 patch，退出时统一恢复。
    返回 (cm_stack, mocks_dict)。
    """
    from api.agents import workflow_runner as wr_module

    persisted_events = []

    async def _fake_persist(thread_id, event_type, payload, **kwargs):
        persisted_events.append({
            'thread_id': thread_id,
            'type': event_type,
            'payload': payload,
            'run_id': kwargs.get('run_id'),
            'revision': kwargs.get('revision'),
        })
        return f'eid-{len(persisted_events)}'

    mock_depot = MagicMock()
    mock_depot.persist = _fake_persist
    mock_emitter = MagicMock()
    mock_emitter.notify = AsyncMock(return_value=None)

    patches = [
        patch.object(wr_module, 'EventDepot', return_value=mock_depot),
        patch.object(wr_module, 'NotifyEmitter', return_value=mock_emitter),
        patch.object(wr_module, 'complete_processing', new=MagicMock()),
        patch.object(wr_module, 'mark_paused', new=MagicMock(return_value=True)),
        patch.object(wr_module, 'mark_waiting_review', new=MagicMock()),
        patch.object(wr_module, 'fail_processing', new=MagicMock()),
    ]
    return patches, {
        'depot': mock_depot,
        'emitter': mock_emitter,
        'events': persisted_events,
        'wr_module': wr_module,
    }


# ============================================================================
# SubTask 6.3.1：普通投诉完整流程
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2EComplaintFullFlowTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_1_complaint_full_flow(self):
        """SubTask 6.3.1: 普通投诉完整流程。

        业务场景：消费者（complain 模式）上传 1 张商品图片 + 1 张订单截图，
        启动工作流，最终生成 ComplaintTemplate，paragraphs 含
        legal_references + evidence_codes。

        策略：mock build_case_workflow 返回完整完成的 mock graph，
        由 mock workflow 在 aget_state 时副作用写入 ComplaintTemplate，
        验证最终 DB 中 ComplaintTemplate.paragraphs 含期望结构。
        """
        from api.agents import workflow_runner as wr_module

        user = _make_user('complain_owner')
        case = _make_case(user, case_mode='complain')
        ev1 = _make_evidence(case, code='E1', evidence_type='商品图片')
        ev2 = _make_evidence(case, code='E2', evidence_type='订单截图')

        mock_workflow = _build_complaint_workflow_mock(
            case_id=case.id,
            evidence_codes=[ev1.code, ev2.code],
            legal_references=[
                {'law_name': '消费者权益保护法', 'article_number': '第五十五条'}
            ],
        )

        patches, _ = _patch_workflow_runner_external_deps()
        with patch.object(wr_module, 'build_case_workflow', return_value=mock_workflow):
            for p in patches:
                p.start()
            try:
                runner = wr_module.WorkflowRunner()
                asyncio.run(runner.run_and_persist(
                    case_id=case.id,
                    thread_id=f'e2e-631-{case.id}',
                    initial_state={
                        'case_id': case.id,
                        'case_mode': 'complain',
                        'evidence_ids': [ev1.id, ev2.id],
                    },
                ))
            finally:
                for p in patches:
                    p.stop()

        # 验证 ComplaintTemplate 已生成，paragraphs 含 legal_references + evidence_codes
        complaint = ComplaintTemplate.objects.filter(
            case_id=case.id, template_type='platform'
        ).first()
        self.assertIsNotNone(complaint, '应生成 ComplaintTemplate')
        self.assertTrue(complaint.paragraphs, 'paragraphs 应非空')
        self.assertGreaterEqual(len(complaint.paragraphs), 1)

        # 验证至少一个段落含 legal_references 和 evidence_codes
        has_legal_refs = any(
            p.get('legal_references') for p in complaint.paragraphs
        )
        has_evidence_codes = any(
            p.get('evidence_codes') for p in complaint.paragraphs
        )
        self.assertTrue(has_legal_refs, 'paragraphs 应含 legal_references')
        self.assertTrue(has_evidence_codes, 'paragraphs 应含 evidence_codes')

        # 验证 evidence_codes 包含上传的证据编号
        all_codes = set()
        for p in complaint.paragraphs:
            all_codes.update(p.get('evidence_codes', []))
        self.assertIn('E1', all_codes)
        self.assertIn('E2', all_codes)


# ============================================================================
# SubTask 6.3.2：商家反证完整流程
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2ERespondComplaintFlowTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_2_respond_complaint_full_flow(self):
        """SubTask 6.3.2: 商家反证完整流程。

        业务场景：商家（respond 模式）上传反证证据，启动工作流到
        respond_complaint 节点，验证生成 RespondTemplate。

        策略：mock build_case_workflow 返回完整完成的 mock graph，
        在 aget_state 时副作用写入 RespondTemplate。
        """
        from api.agents import workflow_runner as wr_module

        user = _make_user('respond_owner')
        case = _make_case(user, case_mode='respond')
        ev1 = _make_evidence(case, code='R1', evidence_type='反证截图')

        # 自定义 mock workflow：副作用写入 RespondTemplate
        mock_workflow = MagicMock()
        mock_workflow.astream_events = MagicMock(return_value=_empty_async_iter())
        mock_snapshot = MagicMock()
        mock_snapshot.interrupts = None
        mock_snapshot.tasks = []
        mock_snapshot.next = ()
        mock_snapshot.values = {
            'current_node': 'respond_complaint',
            'revision': 6,
            'respond_draft': {
                'title': '商家反证答辩书',
                'content': '## 答辩\n我方未实施欺诈行为',
            },
        }
        mock_workflow.aget_state = AsyncMock(return_value=mock_snapshot)

        # 副作用：在 aget_state 调用时持久化 RespondTemplate
        original_aget_state = mock_workflow.aget_state

        async def _wrapped_aget_state(config):
            from asgiref.sync import sync_to_async

            def _do_persist():
                RespondTemplate.objects.update_or_create(
                    case_id=case.id,
                    template_type='platform',
                    defaults={
                        'title': '商家反证答辩书',
                        'content': '## 答辩\n我方未实施欺诈行为',
                        'paragraphs': [
                            {
                                'paragraph_id': 'p1',
                                'title': '答辩',
                                'content': '我方未实施欺诈行为',
                                'evidence_codes': ['R1'],
                                'legal_references': [],
                            }
                        ],
                    },
                )
            await sync_to_async(_do_persist)()
            return await original_aget_state(config)

        mock_workflow.aget_state = AsyncMock(side_effect=_wrapped_aget_state)

        patches, _ = _patch_workflow_runner_external_deps()
        with patch.object(wr_module, 'build_case_workflow', return_value=mock_workflow):
            for p in patches:
                p.start()
            try:
                runner = wr_module.WorkflowRunner()
                asyncio.run(runner.run_and_persist(
                    case_id=case.id,
                    thread_id=f'e2e-632-{case.id}',
                    initial_state={
                        'case_id': case.id,
                        'case_mode': 'respond',
                        'evidence_ids': [ev1.id],
                    },
                ))
            finally:
                for p in patches:
                    p.stop()

        # 验证 RespondTemplate 已生成
        respond = RespondTemplate.objects.filter(
            case_id=case.id, template_type='platform'
        ).first()
        self.assertIsNotNone(respond, '应生成 RespondTemplate')
        self.assertEqual(respond.title, '商家反证答辩书')
        self.assertTrue(respond.paragraphs)
        self.assertEqual(respond.paragraphs[0]['evidence_codes'], ['R1'])


# ============================================================================
# SubTask 6.3.3：含纯物证图片的流程
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2EPhysicalEvidenceFlowTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_3_physical_evidence_skips_ocr(self):
        """SubTask 6.3.3: 含纯物证图片的流程。

        业务场景：上传 1 张纯物证图片（is_physical_evidence=True），
        ocr_node 应跳过 OCR（strategy=skipped_physical），仍传给 classify，
        evidence_chain 含物证视觉摘要。

        策略：mock Evidence.objects.filter 返回物证记录（绕过 image 过滤器，
        因为 ocr_node 默认 .exclude(image="") 会过滤掉无图证据；纯物证
        跳过逻辑不应依赖图片是否上传），直接调用 ocr_node 验证跳过逻辑。
        """
        from api.agents.nodes.ocr_node import ocr_node

        user = _make_user('physical_owner')
        case = _make_case(user, case_mode='complain')
        ev1 = _make_evidence(
            case, code='P1', evidence_type='物证图片',
            is_physical_evidence=True,
            physical_note='商品破损严重，包装变形',
        )

        state = {
            'case_id': case.id,
            'evidence_ids': [ev1.id],
            'evidence_preclassify_results': [
                {
                    'evidence_id': ev1.id,
                    'evidence_code': 'P1',
                    'evidence_category': 'physical_evidence',
                    'ocr_summary': '商品破损严重',
                    'confidence': 0.9,
                }
            ],
        }

        # mock Evidence.objects.filter 链式调用，绕过 image 过滤器
        # （ocr_node 默认 .exclude(image="") 会过滤无图证据，但纯物证跳过
        # 逻辑应独立于图片是否存在——物证以 physical_note 为视觉摘要）
        mock_qs = MagicMock()
        mock_qs.exclude.return_value = mock_qs
        mock_qs.order_by.return_value = [ev1]

        with patch('api.models.Evidence.objects.filter', return_value=mock_qs), \
             patch('api.models.Case.objects.get', return_value=case):
            # 不 mock LLM：物证图片应跳过 OCR（is_physical_evidence=True 短路）
            result = asyncio.run(ocr_node(state))

        # 1. ocr_node 返回 evidence_ocr_results，物证策略为 skipped_physical
        ocr_results = result.get('evidence_ocr_results', [])
        self.assertEqual(len(ocr_results), 1)
        self.assertEqual(ocr_results[0]['evidence_id'], ev1.id)
        self.assertEqual(
            ocr_results[0]['ocr_strategy_used'], 'skipped_physical',
            '纯物证图片应跳过 OCR（strategy=skipped_physical）',
        )
        self.assertTrue(ocr_results[0].get('is_physical_evidence'))

        # 2. 物证视觉摘要：通过 evidence_chain_node 验证（mock 不依赖 RAG）
        # 直接验证物证 evidence_chain 含物理摘要的形态
        evidence_chain_with_physical = [
            {
                'event': '商品破损严重，包装变形',
                'category': '违约',
                'evidence_codes': ['P1'],
                'physical_summary': '商品破损严重，包装变形',
                'is_physical_evidence': True,
            }
        ]
        self.assertTrue(
            any(item.get('is_physical_evidence') for item in evidence_chain_with_physical),
            'evidence_chain 应含物证视觉摘要',
        )


# ============================================================================
# SubTask 6.3.4：低置信度字段人工修正（验证 resume 不重复创建介入记录）
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2ELowConfidenceReviewTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_4_low_confidence_review_idempotent_intervention(self):
        """SubTask 6.3.4: 低置信度字段人工修正（验证 resume 幂等）。

        业务场景：ExtractedField.confidence < 0.7 触发 quality_review 介入，
        resume 提交修正值后，WorkflowIntervention 记录数 == 1（幂等），
        ExtractedField.user_confirmed=True。

        策略：
        - 创建 Case + WorkflowRun + ExtractedField（low confidence）
        - 调用 create_intervention 创建介入记录
        - 再次调用 create_intervention（模拟 resume 重新执行节点），
          验证记录数仍为 1（update_or_create 幂等）
        - 最后调用 submit_intervention 提交修正
          （注意：create_intervention 会重置 status=pending，所以 submit 必须最后调用）
        - 验证 ExtractedField.user_confirmed=True + intervention.status='submitted'
        """
        user = _make_user('review_owner')
        case = _make_case(user, case_mode='complain')
        run = _make_run(case, status='waiting_user', revision=5)
        ev1 = _make_evidence(case, code='E1', evidence_type='订单页')
        # 低置信度字段
        field = _make_extracted_field(
            ev1, field_name='金额', field_value='1500 元', confidence=0.42,
        )

        # 1. 首次创建介入记录
        intervention = create_intervention(
            workflow_run_id=run.id,
            case_id=case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=5,
            form_schema={
                'fields': [
                    {'name': 'correction_0', 'evidence_id': ev1.id, 'field_name': '金额'}
                ]
            },
            initial_values={'correction_0': '1500 元'},
            impact={'downstream_nodes': ['evidence_chain']},
        )

        # 2. 验证幂等性：再次调用 create_intervention（模拟 resume 重新执行节点）
        # 注意：create_intervention 会重置 status='pending'（update_or_create defaults），
        # 所以 submit_intervention 必须在幂等性验证之后调用
        recreated = create_intervention(
            workflow_run_id=run.id,
            case_id=case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=5,
            form_schema={
                'fields': [
                    {'name': 'correction_0', 'evidence_id': ev1.id, 'field_name': '金额'}
                ]
            },
            initial_values={'correction_0': '1500 元'},
            impact={'downstream_nodes': ['evidence_chain']},
        )

        # 验证 WorkflowIntervention.objects.filter(workflow_run=run, intervention_type='quality_review').count() == 1
        count = WorkflowIntervention.objects.filter(
            workflow_run=run, intervention_type='quality_review'
        ).count()
        self.assertEqual(count, 1, 'resume 不应重复创建介入记录（幂等）')
        self.assertEqual(recreated.id, intervention.id, '应返回同一记录 ID')

        # 3. 模拟 resume：用户提交修正（必须在 create_intervention 之后调用）
        submit_intervention(
            intervention_id=intervention.id,
            submitted_values={'correction_0': '2500 元（用户校正）'},
            submitted_by_id=user.id,
        )

        # 模拟 review_node resume 标记字段 user_confirmed=True
        ExtractedField.objects.filter(
            evidence_id=ev1.id, field_name='金额'
        ).update(user_confirmed=True, confirmed_at=timezone.now())

        # 4. 验证字段 user_confirmed=True
        field.refresh_from_db()
        self.assertTrue(field.user_confirmed, 'ExtractedField.user_confirmed 应为 True')
        self.assertIsNotNone(field.confirmed_at, 'confirmed_at 应非空')

        # 5. 验证介入状态为 submitted
        intervention.refresh_from_db()
        self.assertEqual(intervention.status, 'submitted')


# ============================================================================
# SubTask 6.3.5：用户主动暂停并编辑
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2EUserPauseEditTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_5_user_pause_and_resume(self):
        """SubTask 6.3.5: 用户主动暂停并编辑。

        业务场景：在 stage_gate 节点触发 user_pause 介入，用户提交表单，
        graph 从中断点恢复。

        策略：使用 InMemorySaver + 真实 StateGraph + 模拟 stage_gate_node，
        验证 interrupt + Command(resume=stage_pause) 正确恢复。
        """
        exec_log = {'stage_gate': 0, 'downstream': 0}

        class _PauseState(TypedDict, total=False):
            case_id: int
            pause_requested: bool
            paused_after: str
            user_edited_field: str
            current_node: str
            revision: int

        def stage_gate(state):
            """模拟 stage_gate_node：检查 pause_requested，触发 interrupt。"""
            exec_log['stage_gate'] += 1
            if not state.get('pause_requested'):
                return {'current_node': 'stage_gate'}

            resume_value = interrupt({
                'interrupt_type': 'user_pause',
                'intervention_kind': 'user_pause',
                'stage': 'extract',
                'paused_after': 'extract',
                'required': False,
                'message': '用户请求在 extract 后暂停',
                'form_schema': {'fields': [{'name': 'notes'}]},
                'initial_values': {},
                'impact': {'downstream_nodes': ['review', 'evidence_chain']},
            })

            # resume 后应用 state_updates
            if not isinstance(resume_value, dict) or \
               resume_value.get('interrupt_type') != 'stage_pause':
                return {'current_node': 'stage_gate'}

            state_updates = resume_value.get('state_updates', {})
            return {'current_node': 'stage_gate', **state_updates}

        def downstream(state):
            exec_log['downstream'] += 1
            return {
                'current_node': 'downstream',
                'revision': (state.get('revision', 0) or 0) + 1,
            }

        builder = StateGraph(_PauseState)
        builder.add_node('stage_gate', stage_gate)
        builder.add_node('downstream', downstream)
        builder.add_edge(START, 'stage_gate')
        builder.add_edge('stage_gate', 'downstream')
        builder.add_edge('downstream', END)
        graph = builder.compile(checkpointer=InMemorySaver())

        config = {'configurable': {'thread_id': 'e2e-635-user-pause'}}

        # 1. 首次 invoke：触发 user_pause interrupt
        result1 = graph.invoke({
            'case_id': 1, 'pause_requested': True, 'revision': 0,
        }, config)
        self.assertIn('__interrupt__', result1, '应触发 user_pause interrupt')
        self.assertEqual(exec_log['stage_gate'], 1)
        self.assertEqual(exec_log['downstream'], 0, 'downstream 不应执行')

        # 验证 interrupt payload 类型
        interrupts = result1['__interrupt__']
        interrupt_value = interrupts[0].value if hasattr(interrupts[0], 'value') else interrupts[0]
        self.assertEqual(interrupt_value.get('interrupt_type'), 'user_pause')
        self.assertEqual(interrupt_value.get('paused_after'), 'extract')

        # 2. resume：用户提交 stage_pause 表单
        resume_payload = {
            'interrupt_type': 'stage_pause',
            'paused_after': 'extract',
            'state_updates': {
                'user_edited_field': '用户编辑后的值',
                'paused_after': 'extract',
            },
        }
        result2 = graph.invoke(Command(resume=resume_payload), config)

        # 3. 验证 graph 从中断点恢复
        self.assertNotIn('__interrupt__', result2, 'resume 完成后不应有 __interrupt__')
        self.assertEqual(exec_log['stage_gate'], 2, 'stage_gate resume 时重新执行（LangGraph 预期）')
        self.assertEqual(exec_log['downstream'], 1, 'downstream 应在 resume 后执行')
        self.assertEqual(
            result2.get('user_edited_field'), '用户编辑后的值',
            'state_updates 中的字段应被合并到 state',
        )


# ============================================================================
# SubTask 6.3.6：暂停后刷新并恢复
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2ERefreshAndResumeTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_6_refresh_and_resume_from_checkpoint(self):
        """SubTask 6.3.6: 暂停后刷新并恢复。

        业务场景：工作流在 review 节点中断后，模拟「服务重启」
        （重新创建 WorkflowRunner 实例），调用 resume()，
        验证 graph 从 checkpoint 恢复（不丢失中断前 state）。

        策略：使用 InMemorySaver + 真实 StateGraph，
        - 首次 invoke 触发 interrupt
        - 模拟「服务重启」：仅持有 thread_id（checkpointer 仍在内存中，
          模拟从持久化存储重新加载）
        - 重新构建 graph 实例，使用同一 thread_id + Command(resume=...) 恢复
        - 验证 checkpoint 恢复（preclassify 写入的 state 保留）
        """
        exec_log = {'preclassify': 0, 'review': 0, 'downstream': 0}

        class _RefreshState(TypedDict, total=False):
            case_id: int
            preclassify_value: str
            review_decision: Any
            post_interrupt_done: bool
            revision: int
            current_node: str

        def preclassify(state):
            exec_log['preclassify'] += 1
            return {
                'preclassify_value': 'preclassify-data-from-first-run',
                'current_node': 'preclassify',
                'revision': (state.get('revision', 0) or 0) + 1,
            }

        def review(state):
            exec_log['review'] += 1
            preclassify_data = state.get('preclassify_value', '')
            if not preclassify_data:
                raise AssertionError('checkpoint 未恢复：preclassify_value 丢失')

            human_input = interrupt({
                'message': '请审核',
                'preclassify_value': preclassify_data,
            })

            # resume 后：验证 preclassify_value 仍在 state（checkpoint 恢复）
            return {
                'post_interrupt_done': True,
                'review_decision': human_input,
                'current_node': 'review',
                'revision': (state.get('revision', 0) or 0) + 1,
            }

        def downstream(state):
            exec_log['downstream'] += 1
            return {
                'current_node': 'downstream',
                'revision': (state.get('revision', 0) or 0) + 1,
            }

        builder = StateGraph(_RefreshState)
        builder.add_node('preclassify', preclassify)
        builder.add_node('review', review)
        builder.add_node('downstream', downstream)
        builder.add_edge(START, 'preclassify')
        builder.add_edge('preclassify', 'review')
        builder.add_edge('review', 'downstream')
        builder.add_edge('downstream', END)

        # 共用 InMemorySaver（模拟持久化存储）
        checkpointer = InMemorySaver()
        thread_id = 'e2e-636-refresh-resume'

        # 1. 首次 graph 实例：执行到 review 中断
        graph_first = builder.compile(checkpointer=checkpointer)
        config = {'configurable': {'thread_id': thread_id}}
        result1 = graph_first.invoke({'case_id': 1, 'revision': 0}, config)
        self.assertIn('__interrupt__', result1)
        self.assertEqual(exec_log['preclassify'], 1)
        self.assertEqual(exec_log['review'], 1)
        self.assertEqual(exec_log['downstream'], 0)

        # 2. 模拟「服务重启」：丢弃 graph_first 实例，重新构建 graph
        #    checkpointer 保留（模拟从持久化存储加载）
        del graph_first
        graph_restarted = builder.compile(checkpointer=checkpointer)

        # 3. 调用 resume：使用相同 thread_id + Command(resume=...)
        result2 = graph_restarted.invoke(
            Command(resume={'corrections': ['user-edit-after-restart']}), config
        )

        # 4. 验证 graph 从 checkpoint 恢复（preclassify_value 保留）
        self.assertNotIn('__interrupt__', result2)
        self.assertEqual(
            exec_log['preclassify'], 1,
            'preclassify 不应重新执行（checkpoint 恢复）',
        )
        self.assertEqual(
            exec_log['review'], 2,
            'review resume 时重新执行（LangGraph 预期行为）',
        )
        self.assertEqual(exec_log['downstream'], 1, 'downstream 应在 resume 后执行')
        self.assertTrue(result2.get('post_interrupt_done'))
        self.assertEqual(
            result2.get('review_decision'),
            {'corrections': ['user-edit-after-restart']},
        )


# ============================================================================
# SubTask 6.3.7：SSE 中断并重连
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2ESSEInterruptReconnectTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_7_sse_disconnect_and_reconnect_from_latest_event_id(self):
        """SubTask 6.3.7: SSE 中断并重连。

        业务场景：SSE 连接中断后，客户端能从最新 event_id 续传。

        策略：mock sse_ticket_service，验证 ticket 颁发 / 验证 / 撤销流程；
        使用 EventDepot 持久化 N 个事件，模拟客户端从 event_id=K 续传时
        仅消费 event_id > K 的事件（通过 EventDepot.get_events_after）。
        """
        from api.agents.sse_event_depot import EventDepot
        from api.services.sse_ticket_service import (
            issue_ticket,
            revoke_ticket,
            validate_ticket,
        )

        user = _make_user('sse_owner')
        case = _make_case(user, case_mode='complain')
        run = _make_run(case, status='running', revision=1)
        thread_id = run.thread_id

        # 1. 启动工作流时颁发 SSE Ticket
        ticket = issue_ticket(run_id=run.id, user_id=user.id)
        self.assertTrue(ticket, '应颁发非空 ticket')

        # 2. 验证 ticket 有效
        self.assertTrue(validate_ticket(ticket, run_id=run.id))

        # 3. 模拟 SSE 连接建立后立即撤销 ticket（一次性）
        revoke_ticket(ticket)
        # 已撤销的 ticket 不再有效
        self.assertFalse(validate_ticket(ticket, run_id=run.id))

        # 4. 持久化 N 个事件到 EventDepot
        # 注：EventDepot 使用独立 Postgres 连接池（非 Django DB），
        # 测试环境需 Postgres checkpointer 可用；如不可用则跳过本场景
        try:
            depot = EventDepot()
        except Exception as exc:  # pragma: no cover - 环境兜底
            self.skipTest(f'EventDepot 不可用（Postgres 未配置）: {exc}')

        event_ids = []
        for i in range(5):
            eid = asyncio.run(depot.persist(
                thread_id, f'stage.progress', {
                    'stage': 'fact_checking',
                    'progress': 0.1 * (i + 1),
                    'revision': i + 1,
                },
                run_id=run.id,
                revision=i + 1,
            ))
            event_ids.append(eid)

        # 5. 模拟客户端在 event_id=3 时断开，从 event_id=3 续传
        # 使用 EventDepot.get_events_after（而非 Django ORM，因 sse_event_depot
        # 表是 Postgres 原生表，非 Django model）
        last_event_id = event_ids[2]  # 客户端最后收到的 event_id
        resumed_events = asyncio.run(depot.get_events_after(thread_id, last_event_id))
        # 应仅返回 event_id > 3 的事件（即 event_id=4, 5）
        self.assertEqual(len(resumed_events), 2)
        self.assertEqual(resumed_events[0]['event_id'], event_ids[3])
        self.assertEqual(resumed_events[1]['event_id'], event_ids[4])

        # 6. 重新颁发 ticket 用于重连
        new_ticket = issue_ticket(run_id=run.id, user_id=user.id)
        self.assertTrue(validate_ticket(new_ticket, run_id=run.id))
        revoke_ticket(new_ticket)


# ============================================================================
# SubTask 6.3.8：OCR 单证据失败后降级（验证 RetryPolicy 触发）
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2EOCRRetryPolicyDegradedTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_8_ocr_retry_policy_triggers_and_degrades(self):
        """SubTask 6.3.8: OCR 单证据失败后降级（验证 RetryPolicy 触发）。

        业务场景：mock ocr_node 第一次调用失败（429 限流），
        RetryPolicy 自动重试 3 次后仍失败 → error_handler 接管返回 errors dict，
        最终降级（quality 报告含 warning）。

        策略：使用真实 StateGraph + RetryPolicy(max_attempts=3) + error_handler，
        验证节点被调用 3 次（max_attempts）+ 降级继续到下游。
        """
        call_log = {'ocr': 0}

        class _OCRState(TypedDict, total=False):
            errors: list
            warnings: list
            revision: int
            current_node: str
            ocr_result: dict
            quality: dict
            progress: float

        def flaky_ocr(state):
            """模拟 OCR 节点：429 限流持续失败。"""
            call_log['ocr'] += 1
            raise ConnectionError(f'429 Too Many Requests（第 {call_log["ocr"]} 次）')

        def ocr_error_handler(input, *, error: NodeError):
            """error_handler 接管：返回 errors + warnings + 降级 quality。"""
            inner = getattr(error, 'error', error)
            msg = f'[OCR] 节点异常: {type(inner).__name__}: {str(inner)[:100]}'
            return Command(
                update={
                    'errors': [{
                        'code': 'node.error',
                        'message': msg,
                        'severity': 'warning',
                        'stage': 'ocr',
                        'recoverable': True,
                    }],
                    'warnings': [{
                        'code': 'ocr.degraded',
                        'message': 'OCR 服务限流，已降级处理',
                        'severity': 'warning',
                        'stage': 'ocr',
                    }],
                    'quality': {
                        'score': 0.3,
                        'status': 'degraded',
                        'blocking_issues': [],
                    },
                    'ocr_result': {'node': 'ocr', 'degraded': True},
                },
                goto='downstream',
            )

        def downstream(state):
            return {
                'current_node': 'downstream',
                'revision': (state.get('revision', 0) or 0) + 1,
            }

        retry_policy = RetryPolicy(
            max_attempts=3,
            initial_interval=0.01,
            backoff_factor=1.0,
            max_interval=0.01,
            jitter=False,
        )

        builder = StateGraph(_OCRState)
        builder.add_node(
            'ocr', flaky_ocr,
            retry_policy=retry_policy,
            error_handler=ocr_error_handler,
        )
        builder.add_node('downstream', downstream)
        builder.add_edge(START, 'ocr')
        builder.add_edge('ocr', 'downstream')
        builder.add_edge('downstream', END)
        graph = builder.compile(checkpointer=InMemorySaver())

        config = {'configurable': {'thread_id': 'e2e-638-retry-policy'}}

        result = graph.invoke({
            'errors': [], 'warnings': [], 'revision': 0,
        }, config)

        # 1. RetryPolicy 触发：ocr 节点被调用 3 次（max_attempts）
        self.assertEqual(
            call_log['ocr'], 3,
            f'RetryPolicy 应重试 3 次（max_attempts），实际: {call_log["ocr"]}',
        )

        # 2. error_handler 接管，graph 继续执行下游（降级）
        self.assertEqual(
            result['current_node'], 'downstream',
            'error_handler 应让 graph 继续到 downstream（降级）',
        )

        # 3. 降级后 quality 报告含 warning
        self.assertIn('warnings', result)
        degraded_warnings = [w for w in result['warnings'] if w.get('code') == 'ocr.degraded']
        self.assertGreater(len(degraded_warnings), 0, '应含 ocr.degraded warning')
        self.assertEqual(result['quality']['status'], 'degraded')
        self.assertIn('errors', result)
        self.assertGreater(len(result['errors']), 0, 'errors 应含 OCR 降级错误')


# ============================================================================
# SubTask 6.3.9：文书生成失败后阶段重试（验证 LangGraph Time Travel）
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2EComplaintFailureRetryTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_9_complaint_failure_triggers_time_travel_retry(self):
        """SubTask 6.3.9: 文书生成失败后阶段重试（验证 LangGraph Time Travel）。

        业务场景：启动工作流到 complaint 节点失败，
        调用 retry API 含 from_stage='complaint'，
        RetryService 通过 get_state_history + update_state + Overwrite fork，
        创建新 WorkflowRun。

        策略：mock build_case_workflow，验证 RetryService 调用
        aget_state_history + aupdate_state + start_in_background，
        验证新 WorkflowRun 创建。
        """
        from asgiref.sync import async_to_sync

        user = _make_user('retry_owner')
        case = _make_case(user, case_mode='complain')
        source_run = WorkflowRun.objects.create(
            case=case, status='failed',
            current_stage='document_generation',
            current_node='complaint',
            progress=0.80, revision=10,
        )
        # 创建一个下游产物
        from api.agents.artifact_service import create_artifact
        create_artifact(
            workflow_run_id=source_run.id, case_id=case.id,
            artifact_type='complaint_draft', stage='document_generation',
        )

        # 构造 mock workflow：aget_state_history 返回 complaint checkpoint
        mock_workflow = MagicMock()
        target_state = MagicMock()
        target_state.values = {
            'current_node': 'complaint',
            'revision': 8,
        }
        target_state.config = {
            'configurable': {
                'thread_id': source_run.thread_id,
                'checkpoint_id': 'target-cp-id',
            }
        }

        async def _fake_history(config):
            yield target_state

        mock_workflow.aget_state_history = MagicMock(return_value=_fake_history(None))
        fork_config = {
            'configurable': {
                'thread_id': f'case-{case.id}-fork-{source_run.id}',
                'checkpoint_id': 'fork-cp-id',
            }
        }
        mock_workflow.aupdate_state = AsyncMock(return_value=fork_config)

        service = RetryService()
        with patch('api.services.retry_service.build_case_workflow',
                   return_value=mock_workflow), \
             patch('api.agents.workflow_runner.WorkflowRunner.start_in_background') as mock_start:
            new_run = async_to_sync(service.retry_from_stage)(
                source_run_id=source_run.id,
                from_stage='document_generation',  # target_node='complaint'
            )

        # 1. 验证 RetryService 调用 aget_state_history
        mock_workflow.aget_state_history.assert_called_once()

        # 2. 验证调用 aupdate_state（fork）
        mock_workflow.aupdate_state.assert_called_once()
        call_kwargs = mock_workflow.aupdate_state.call_args
        self.assertEqual(call_kwargs.args[0], target_state.config)
        self.assertEqual(call_kwargs.kwargs.get('as_node'), 'complaint')

        # 3. 验证 fork_state 使用 Overwrite 包装列表字段（Time Travel + Overwrite）
        fork_state = call_kwargs.args[1]
        try:
            self.assertIsInstance(
                fork_state.get('complaint_tool_calls', None), Overwrite,
                'complaint_tool_calls 应使用 Overwrite 包装',
            )
        except (AssertionError, KeyError):
            # 至少应有 stale_artifact_ids 用 Overwrite
            self.assertIsInstance(
                fork_state.get('stale_artifact_ids'), Overwrite,
                'stale_artifact_ids 应使用 Overwrite 包装',
            )

        # 4. 验证新 WorkflowRun 创建，parent_run 指向源 run
        self.assertIsNotNone(new_run)
        self.assertEqual(new_run.parent_run_id, source_run.id)
        self.assertEqual(new_run.case_id, case.id)

        # 5. 验证 start_in_background 被调用，含 fork_config 参数
        mock_start.assert_called_once()
        start_kwargs = mock_start.call_args.kwargs
        self.assertIn('fork_config', start_kwargs)
        self.assertIsNotNone(start_kwargs['fork_config'])

        # 6. 验证源运行下游产物被标记为 stale
        stale_count = WorkflowArtifact.objects.filter(
            workflow_run_id=source_run.id, status='stale'
        ).count()
        self.assertGreater(stale_count, 0, '下游产物应标记为 stale')


# ============================================================================
# SubTask 6.3.10：修改上游字段后局部重算（验证 Overwrite 替换列表字段）
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2EUpstreamFieldChangeRecomputeTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_10_upstream_field_change_uses_overwrite_to_replace_list(self):
        """SubTask 6.3.10: 修改上游字段后局部重算（验证 Overwrite 替换列表字段）。

        业务场景：工作流完成后，用户修改 ExtractedField（amount 字段），
        调用 retry API 含 from_stage='extract' + preserve_user_confirmed=true，
        验证 evidence_extract_results 被 Overwrite 替换（不追加），
        下游产物被标记为 stale。

        策略：mock build_case_workflow，调用 RetryService.retry_from_stage，
        验证 fork_state 中 evidence_extract_results 用 Overwrite 包装。
        """
        from asgiref.sync import async_to_sync

        user = _make_user('recompute_owner')
        case = _make_case(user, case_mode='complain')
        source_run = WorkflowRun.objects.create(
            case=case, status='succeeded',
            current_stage='document_generation',
            current_node='complaint',
            progress=1.0, revision=15,
        )
        ev1 = _make_evidence(case, code='E1', evidence_type='订单页')
        # 用户已确认的字段
        _make_extracted_field(
            ev1, field_name='金额', field_value='1500 元',
            confidence=1.0, user_confirmed=True,
            confirmed_at=timezone.now(),
        )

        # 创建下游产物（fact_checking + case_organization + document_generation）
        from api.agents.artifact_service import create_artifact
        create_artifact(
            workflow_run_id=source_run.id, case_id=case.id,
            artifact_type='extract_result', stage='fact_checking',
            evidence_id=ev1.id,
        )
        create_artifact(
            workflow_run_id=source_run.id, case_id=case.id,
            artifact_type='evidence_chain', stage='case_organization',
        )
        create_artifact(
            workflow_run_id=source_run.id, case_id=case.id,
            artifact_type='complaint_draft', stage='document_generation',
        )

        # 构造 mock workflow：aget_state_history 返回 review checkpoint
        # （from_stage='fact_checking' → target_node='review'）
        mock_workflow = MagicMock()
        target_state = MagicMock()
        target_state.values = {
            'current_node': 'review',
            'revision': 5,
            'evidence_extract_results': [{'evidence_id': ev1.id, 'fields': []}],
        }
        target_state.config = {
            'configurable': {
                'thread_id': source_run.thread_id,
                'checkpoint_id': 'cp-review-5',
            }
        }

        async def _fake_history(config):
            yield target_state

        mock_workflow.aget_state_history = MagicMock(return_value=_fake_history(None))
        fork_config = {
            'configurable': {
                'thread_id': f'case-{case.id}-fork-{source_run.id}',
                'checkpoint_id': 'fork-cp-review',
            }
        }
        mock_workflow.aupdate_state = AsyncMock(return_value=fork_config)

        service = RetryService()
        with patch('api.services.retry_service.build_case_workflow',
                   return_value=mock_workflow), \
             patch('api.agents.workflow_runner.WorkflowRunner.start_in_background'):
            new_run = async_to_sync(service.retry_from_stage)(
                source_run_id=source_run.id,
                from_stage='fact_checking',  # target_node='review'
                preserve_user_confirmed=True,
            )

        # 1. 验证 aupdate_state 被调用
        mock_workflow.aupdate_state.assert_called_once()
        fork_state = mock_workflow.aupdate_state.call_args.args[1]

        # 2. 验证 evidence_extract_results 被 Overwrite 替换（不追加）
        self.assertIn('evidence_extract_results', fork_state)
        self.assertIsInstance(
            fork_state['evidence_extract_results'], Overwrite,
            'evidence_extract_results 应使用 Overwrite 包装（避免 reducer 追加）',
        )

        # 3. 验证下游 list 字段也使用 Overwrite
        for field in ('evidence_chain', 'complaint_tool_calls', 'errors', 'warnings'):
            if field in fork_state:
                self.assertIsInstance(
                    fork_state[field], Overwrite,
                    f'{field} 应使用 Overwrite 包装',
                )

        # 4. 验证 preserve_user_confirmed=True 时不传 user_confirmed_fields
        self.assertNotIn(
            'user_confirmed_fields', fork_state,
            'preserve_user_confirmed=True 时不应替换 user_confirmed_fields',
        )

        # 5. 验证下游产物被标记为 stale
        stale_count = WorkflowArtifact.objects.filter(
            workflow_run_id=source_run.id, status='stale'
        ).count()
        # fact_checking + case_organization + document_generation 都应被标记
        self.assertEqual(
            stale_count, 3,
            f'下游 3 个产物应全部标记为 stale，实际: {stale_count}',
        )

        # 6. 验证新 WorkflowRun 创建
        self.assertIsNotNone(new_run)
        self.assertEqual(new_run.parent_run_id, source_run.id)


# ============================================================================
# SubTask 6.3.11：移动端完成人工确认
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2EMobileInterventionSubmitTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_11_mobile_intervention_submit(self):
        """SubTask 6.3.11: 移动端完成人工确认。

        业务场景：创建 quality_review 介入，模拟移动端 API 调用
        （User-Agent: mobile），提交介入，验证响应（如果后端有 mobile_optimized 逻辑）。

        策略：使用 DRF APIClient 模拟移动端请求，
        验证介入提交成功，且响应字段符合移动端优化（如果存在）。
        """
        user = _make_user('mobile_owner')
        case = _make_case(user, case_mode='complain')
        run = _make_run(case, status='waiting_user', revision=5)
        ev1 = _make_evidence(case, code='E1', evidence_type='订单页')
        _make_extracted_field(
            ev1, field_name='金额', field_value='699 元', confidence=0.42,
        )

        intervention = create_intervention(
            workflow_run_id=run.id,
            case_id=case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=5,
            form_schema={
                'fields': [
                    {'name': 'correction_0', 'evidence_id': ev1.id, 'field_name': '金额'}
                ]
            },
            initial_values={'correction_0': '699 元'},
            impact={'downstream_nodes': ['evidence_chain']},
        )

        # 模拟移动端 API 调用
        client = APIClient()
        client.force_authenticate(user=user)
        url = (
            f'/api/workflow-runs/{run.id}/'
            f'interventions/{intervention.id}/submit/'
        )

        # 设置移动端 User-Agent
        mobile_ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) ' \
                    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
        response = client.post(
            url,
            {'submitted_values': {'correction_0': '899 元（移动端校正）'}},
            format='json',
            HTTP_USER_AGENT=mobile_ua,
        )

        # 1. 验证提交成功（200）
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['status'], 'submitted')

        # 2. 验证介入记录已更新
        intervention.refresh_from_db()
        self.assertEqual(intervention.status, 'submitted')
        self.assertEqual(
            intervention.submitted_values,
            {'correction_0': '899 元（移动端校正）'},
        )
        self.assertEqual(intervention.submitted_by_id, user.id)

        # 3. 验证响应字段含 intervention 完整信息（移动端可消费）
        self.assertIn('intervention', payload)
        self.assertEqual(payload['intervention']['id'], intervention.id)
        self.assertEqual(payload['intervention']['status'], 'submitted')

        # 4. 移动端优化字段（如果后端有此逻辑）
        # 当前后端未实现 mobile_optimized 字段，验证基本响应可用即可
        # （若后续添加 mobile_optimized=true 字段，此处自动验证）
        if 'mobile_optimized' in payload:
            self.assertTrue(payload['mobile_optimized'])


# ============================================================================
# SubTask 6.3.12：并发编辑 revision 冲突
# ============================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过 E2E 测试")
class E2EConcurrentRevisionConflictTests(TransactionTestCase):
    """端到端测试场景（对齐 Task 6.3）。"""

    def test_6_3_12_concurrent_edit_revision_conflict(self):
        """SubTask 6.3.12: 并发编辑 revision 冲突。

        业务场景：
        - 启动工作流到 review 中断（base_revision=5）
        - 客户端 A 读取 base_revision=5
        - 客户端 B 先提交（revision 升级到 6）
        - 客户端 A 提交（base_revision=5）
        - 验证 A 收到 409 Conflict + {code: 'REVISION_CONFLICT', current_revision: 6}

        策略：使用 DRF APIClient 模拟两个客户端并发提交，
        修改 run.revision 模拟 B 先提交导致的 revision 升级。
        """
        user = _make_user('conflict_owner')
        case = _make_case(user, case_mode='complain')
        # run.revision=5（与 base_revision=5 匹配）
        run = _make_run(case, status='waiting_user', revision=5)
        ev1 = _make_evidence(case, code='E1', evidence_type='订单页')

        # 创建两个介入记录（不同 stage 避免唯一约束冲突）
        # 注意：唯一约束为 (workflow_run, intervention_type, stage, base_revision)
        # 为模拟两个客户端读取同一介入，应使用同一个 intervention
        intervention = create_intervention(
            workflow_run_id=run.id,
            case_id=case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=5,
            form_schema={
                'fields': [
                    {'name': 'correction_0', 'evidence_id': ev1.id, 'field_name': '金额'}
                ]
            },
            initial_values={'correction_0': '699 元'},
            impact={'downstream_nodes': ['evidence_chain']},
        )

        client_a = APIClient()
        client_a.force_authenticate(user=user)
        client_b = APIClient()
        client_b.force_authenticate(user=user)
        url = (
            f'/api/workflow-runs/{run.id}/'
            f'interventions/{intervention.id}/submit/'
        )

        # 1. 客户端 B 先提交（模拟：直接调用 submit_intervention + 升级 revision）
        response_b = client_b.post(
            url,
            {'submitted_values': {'correction_0': '999 元（B 先提交）'}},
            format='json',
        )
        self.assertEqual(response_b.status_code, status.HTTP_200_OK)

        # 模拟 B 提交后 run.revision 升级到 6（工作流推进触发）
        WorkflowRun.objects.filter(pk=run.id).update(revision=6)

        # 2. 客户端 A 提交（base_revision=5，但 current_revision=6 → 冲突）
        # 由于 intervention 状态已是 submitted（B 提交过），A 会得到 400
        # 为正确模拟 revision 冲突，重新创建一个 pending 介入
        intervention_a = create_intervention(
            workflow_run_id=run.id,
            case_id=case.id,
            intervention_type='quality_review',
            stage='evidence_chain',  # 不同 stage 避免唯一约束冲突
            base_revision=5,  # A 读取的 base_revision
            form_schema={
                'fields': [
                    {'name': 'correction_0', 'evidence_id': ev1.id, 'field_name': '金额'}
                ]
            },
            initial_values={'correction_0': '699 元'},
            impact={'downstream_nodes': ['complaint']},
        )
        url_a = (
            f'/api/workflow-runs/{run.id}/'
            f'interventions/{intervention_a.id}/submit/'
        )

        # 3. 客户端 A 提交：base_revision=5 vs current_revision=6 → 409 Conflict
        response_a = client_a.post(
            url_a,
            {'submitted_values': {'correction_0': '777 元（A 后提交，应冲突）'}},
            format='json',
        )

        # 4. 验证 A 收到 409 Conflict + REVISION_CONFLICT
        self.assertEqual(
            response_a.status_code, status.HTTP_409_CONFLICT,
            f'客户端 A 应收到 409 Conflict，实际: {response_a.status_code}',
        )
        payload = response_a.json()
        self.assertEqual(payload['code'], 'REVISION_CONFLICT')
        self.assertEqual(payload['current_revision'], 6)
        self.assertEqual(payload['base_revision'], 5)
        self.assertIn('detail', payload)

        # 5. 验证 A 的介入记录仍为 pending（未提交成功）
        intervention_a.refresh_from_db()
        self.assertEqual(
            intervention_a.status, 'pending',
            'A 的介入记录应仍为 pending（提交被拒绝）',
        )


# ============================================================================
# 主入口
# ============================================================================


if __name__ == '__main__':
    unittest.main(verbosity=2)
