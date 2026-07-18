# -*- coding: utf-8 -*-
"""Task 4.2 测试：法律引用一致性校验 + 导出前质量门。

覆盖 6 种场景（对齐 SubTask 4.2.5）：
1. 法条引用存在 / 不存在（validate_legal_references 三级降级策略）
2. 金额一致 / 不一致（run_export_check 子检查）
3. 主体名称一致 / 不一致（run_export_check 子检查）
4. 必备要素完整性缺失（run_export_check 子检查）
5. 引用 stale 产物（run_export_check 子检查）
6. should_block_on_quality=True AND not valid 触发 interrupt()（complaint_node 集成）

测试策略：
- 全部测试使用 TransactionTestCase（sync_to_async 跨线程 SQLite 锁规避）
- 服务测试与节点集成测试统一基础类，避免 DB 事务与异步线程冲突
- mock LLM 调用（is_llm_available / chat_with_retry）+ mock RAG 检索
  （pre_retrieve_law_articles）+ mock 工具开关（is_tools_enabled=False）
- 法条校验测试通过 _reset_law_retriever_cache 强制走 DB 降级路径（不依赖 RAG）
- interrupt 测试 mock validate_legal_references 返回 invalid + mock langgraph.types.interrupt

运行方式：
    cd backend
    python manage.py test api.tests.test_document_quality_service -v 2
"""
import asyncio
from unittest.mock import AsyncMock, patch

from django.contrib.auth.models import User
from django.test import TransactionTestCase
from django.utils import timezone

from api.models import (
    Case,
    ComplaintTemplate,
    DocumentVersion,
    Evidence,
    ExtractedField,
    LawArticle,
    WorkflowArtifact,
    WorkflowIntervention,
    WorkflowRun,
)
from api.services.document_quality_service import (
    ExportCheckResult,
    ValidationResult,
    _reset_law_retriever_cache,
    run_export_check,
    validate_legal_references,
)
from api.services.document_version_service import create_document_version


# ============================================================================
# 辅助函数
# ============================================================================


def _make_case(user=None, **kwargs):
    """创建一个最小 Case。"""
    return Case.objects.create(
        title=kwargs.pop('title', '测试案件-质量门'),
        owner=user,
        **kwargs,
    )


def _make_run(case, **kwargs):
    """创建一个 WorkflowRun（thread_id 由 save() 自动生成）。"""
    defaults = {
        'status': 'running',
        'current_stage': 'document_generation',
        'current_node': 'complaint',
        'progress': 0.90,
        'revision': 1,
    }
    defaults.update(kwargs)
    return WorkflowRun.objects.create(case=case, **defaults)


def _make_evidence(case, code='E1', **kwargs):
    """创建一个 Evidence 记录。"""
    defaults = {
        'code': code,
        'evidence_type': '订单页',
        'description': f'{code} 证据描述',
        'source_time': timezone.now(),
    }
    defaults.update(kwargs)
    return Evidence.objects.create(case=case, **defaults)


def _make_doc(case, run, content='## 事实\n测试', paragraphs=None, **kwargs):
    """创建一个 DocumentVersion 记录。"""
    return create_document_version(
        case=case,
        workflow_run=run,
        document_type=kwargs.pop('document_type', 'complaint'),
        title=kwargs.pop('title', '测试文书'),
        content=content,
        paragraphs=paragraphs if paragraphs is not None else [],
        changelog=kwargs.pop('changelog', '测试'),
        created_by_type=kwargs.pop('created_by_type', 'ai'),
        workflow_version=kwargs.pop('workflow_version', 'v11'),
    )


def _make_node_state(case_id, **extra):
    """构造 complaint_node 测试用 state。"""
    state = {
        'case_id': case_id,
        'revision': 5,
        'workflow_version': 'v11',
        'evidence_preclassify_results': [],
        'evidence_ocr_results': [],
        'evidence_classify_results': [],
        'evidence_extract_results': [],
        'evidence_chain': [],
        'errors': [],
        'warnings': [],
        'provenance': [],
        'issues': [],
        'events': [],
        'artifacts': [],
    }
    state.update(extra)
    return state


# ============================================================================
# SubTask 4.2.5 场景 1：法条引用真实性校验
# ============================================================================


class LegalReferencesValidationTests(TransactionTestCase):
    """validate_legal_references 三级降级策略测试。

    测试策略：
    - 不启用 RAG（_reset_law_retriever_cache 强制重新初始化，测试环境无 RAG 配置）
    - DB 直查路径：LawArticle 表存在/不存在
    - 格式校验路径：law_name 非空 + article_number 符合「第X条」
    """

    def setUp(self):
        # 重置 LawRetriever 单例缓存（确保不使用 RAG，走 DB 降级路径）
        _reset_law_retriever_cache()
        # 在 LawArticle 表中预置一条真实法条
        LawArticle.objects.create(
            law_name='消费者权益保护法',
            article_number='第五十五条',
            content='经营者提供商品或者服务有欺诈行为的...',
            summary='欺诈行为退一赔三',
            category='consumer_protection',
            is_active=True,
        )

    def test_legal_reference_exists_in_db(self):
        """法条存在于 LawArticle 表 → 校验通过（valid=True）。"""
        paragraphs = [{
            'paragraph_id': 'p1',
            'legal_references': [
                {'law_name': '消费者权益保护法', 'article_number': '第五十五条'},
            ],
        }]
        result = asyncio.run(validate_legal_references(paragraphs))

        self.assertTrue(result.valid)
        self.assertEqual(result.total_refs, 1)
        self.assertEqual(result.valid_refs, 1)
        self.assertEqual(result.invalid_refs, [])

    def test_legal_reference_not_in_db_but_valid_format(self):
        """法条不在 LawArticle 表但格式合规 → 降级格式校验通过（valid=True）。"""
        paragraphs = [{
            'paragraph_id': 'p1',
            'legal_references': [
                # 不在 DB 但格式正确：「第X条」
                {'law_name': '某未录入法律', 'article_number': '第三条'},
            ],
        }]
        result = asyncio.run(validate_legal_references(paragraphs))

        # 格式校验通过 → valid=True
        self.assertTrue(result.valid)
        self.assertEqual(result.total_refs, 1)
        self.assertEqual(result.valid_refs, 1)

    def test_legal_reference_invalid_format(self):
        """法条不在 DB 且格式不合规 → valid=False，加入 invalid_refs。"""
        paragraphs = [{
            'paragraph_id': 'p1',
            'legal_references': [
                # 格式不合规：article_number 不是「第X条」格式
                {'law_name': '虚构法律', 'article_number': 'abc'},
            ],
        }]
        result = asyncio.run(validate_legal_references(paragraphs))

        self.assertFalse(result.valid)
        self.assertEqual(result.total_refs, 1)
        self.assertEqual(result.valid_refs, 0)
        self.assertEqual(len(result.invalid_refs), 1)
        self.assertEqual(result.invalid_refs[0]['law_name'], '虚构法律')
        self.assertEqual(result.invalid_refs[0]['paragraph_id'], 'p1')

    def test_legal_reference_empty_law_name(self):
        """law_name 为空 → valid=False。"""
        paragraphs = [{
            'paragraph_id': 'p1',
            'legal_references': [
                {'law_name': '', 'article_number': '第五条'},
            ],
        }]
        result = asyncio.run(validate_legal_references(paragraphs))

        self.assertFalse(result.valid)
        self.assertEqual(len(result.invalid_refs), 1)

    def test_validate_legal_references_no_refs_returns_valid(self):
        """段落无 legal_references → valid=True（空集视为通过）。"""
        paragraphs = [{'paragraph_id': 'p1', 'legal_references': []}]
        result = asyncio.run(validate_legal_references(paragraphs))

        self.assertTrue(result.valid)
        self.assertEqual(result.total_refs, 0)


# ============================================================================
# SubTask 4.2.5 场景 2：金额一致性检查
# ============================================================================


class ExportCheckAmountConsistencyTests(TransactionTestCase):
    """金额一致性检查测试。

    测试策略：
    - 创建 DocumentVersion + Evidence + ExtractedField(金额字段)
    - 文书正文中金额与抽取字段金额一致/不一致
    """

    def setUp(self):
        _reset_law_retriever_cache()
        self.user = User.objects.create_user(username='amt-owner', password='pass')
        self.case = _make_case(self.user)
        self.run = _make_run(self.case)
        self.evidence = _make_evidence(self.case, code='E1')

    def test_amount_consistent(self):
        """文书金额与抽取金额一致 → 无 AMOUNT_MISMATCH issue。"""
        doc = _make_doc(
            self.case, self.run,
            content='## 事实\n购买商品支付 2980 元\n\n## 诉求\n请求退款',
        )
        ExtractedField.objects.create(
            evidence=self.evidence,
            field_name='金额',
            field_value='2980 元',
            confidence=0.95,
        )

        result = asyncio.run(run_export_check(doc.id, run_id=self.run.id))

        amount_issues = [i for i in result.issues if i.code == 'AMOUNT_MISMATCH']
        self.assertEqual(amount_issues, [])

    def test_amount_inconsistent(self):
        """文书金额与抽取金额不一致 → AMOUNT_MISMATCH blocking issue + passed=False。"""
        doc = _make_doc(
            self.case, self.run,
            content='## 事实\n购买商品支付 2980 元',
        )
        # ExtractedField 含不同金额（5000 元，差异 > 1 元）
        ExtractedField.objects.create(
            evidence=self.evidence,
            field_name='金额',
            field_value='5000 元',
            confidence=0.95,
        )

        result = asyncio.run(run_export_check(doc.id, run_id=self.run.id))

        amount_issues = [i for i in result.issues if i.code == 'AMOUNT_MISMATCH']
        self.assertEqual(len(amount_issues), 1)
        self.assertEqual(amount_issues[0].severity, 'blocking')
        self.assertFalse(result.passed)

    def test_amount_wan_yuan_unit_consistent(self):
        """金额单位「万元」正确换算（1.5 万元 = 15000 元，差异 <= 1 元视为一致）。"""
        doc = _make_doc(
            self.case, self.run,
            content='## 事实\n交易金额 1.5 万元',
        )
        ExtractedField.objects.create(
            evidence=self.evidence,
            field_name='交易金额',
            field_value='15000 元',
            confidence=0.95,
        )

        result = asyncio.run(run_export_check(doc.id, run_id=self.run.id))

        amount_issues = [i for i in result.issues if i.code == 'AMOUNT_MISMATCH']
        self.assertEqual(amount_issues, [])


# ============================================================================
# SubTask 4.2.5 场景 3：主体名称一致性检查
# ============================================================================


class ExportCheckPartyConsistencyTests(TransactionTestCase):
    """主体名称一致性检查测试。"""

    def setUp(self):
        _reset_law_retriever_cache()
        self.user = User.objects.create_user(username='party-owner', password='pass')
        self.case = _make_case(self.user)
        self.run = _make_run(self.case)
        self.evidence = _make_evidence(self.case, code='E1')

    def test_party_consistent(self):
        """文书正文含主体名称 → 无 PARTY_MISMATCH issue。"""
        doc = _make_doc(
            self.case, self.run,
            content='## 事实\n投诉人在某商家购买商品',
        )
        ExtractedField.objects.create(
            evidence=self.evidence,
            field_name='商家名称',
            field_value='某商家',
            confidence=0.95,
        )

        result = asyncio.run(run_export_check(doc.id, run_id=self.run.id))

        party_issues = [i for i in result.issues if i.code == 'PARTY_MISMATCH']
        self.assertEqual(party_issues, [])

    def test_party_inconsistent(self):
        """文书正文未提及主体名称 → PARTY_MISMATCH warning issue。"""
        doc = _make_doc(
            self.case, self.run,
            content='## 事实\n投诉人购买商品',  # 未提及商家名称
        )
        ExtractedField.objects.create(
            evidence=self.evidence,
            field_name='商家名称',
            field_value='某商家',
            confidence=0.95,
        )

        result = asyncio.run(run_export_check(doc.id, run_id=self.run.id))

        party_issues = [i for i in result.issues if i.code == 'PARTY_MISMATCH']
        self.assertEqual(len(party_issues), 1)
        # 主体不一致是 warning（不阻塞导出）
        self.assertEqual(party_issues[0].severity, 'warning')


# ============================================================================
# SubTask 4.2.5 场景 4：必备要素完整性检查
# ============================================================================


class ExportCheckRequiredElementsTests(TransactionTestCase):
    """必备要素完整性检查测试（事实段 / 依据段 / 诉求段）。"""

    def setUp(self):
        _reset_law_retriever_cache()
        self.user = User.objects.create_user(username='elem-owner', password='pass')
        self.case = _make_case(self.user)
        self.run = _make_run(self.case)

    def test_missing_basis_element(self):
        """仅含事实段 + 诉求段，缺失依据段 → MISSING_ELEMENT blocking + missing_elements 含「依据段」。"""
        paragraphs = [
            {
                'paragraph_id': 'p1',
                'title': '事实与理由',
                'content': '## 事实与理由\n商家欺诈',
                'legal_references': [],
            },
            {
                'paragraph_id': 'p2',
                'title': '诉求',
                'content': '## 诉求\n请求退款',
                'legal_references': [],
            },
        ]
        content = '\n\n'.join(p['content'] for p in paragraphs)
        doc = _make_doc(self.case, self.run, content=content, paragraphs=paragraphs)

        result = asyncio.run(run_export_check(doc.id, run_id=self.run.id))

        # missing_elements 含「依据段」
        self.assertIn('依据段', result.missing_elements)
        # 应有 MISSING_ELEMENT blocking issue
        elem_issues = [i for i in result.issues if i.code == 'MISSING_ELEMENT']
        self.assertGreater(len(elem_issues), 0)
        self.assertEqual(elem_issues[0].severity, 'blocking')
        # 阻塞导出
        self.assertFalse(result.passed)

    def test_all_elements_present(self):
        """事实段 + 依据段 + 诉求段齐全 → 无 MISSING_ELEMENT issue。"""
        paragraphs = [
            {
                'paragraph_id': 'p1',
                'title': '事实与理由',
                'content': '## 事实\n商家欺诈',
                'legal_references': [],
            },
            {
                'paragraph_id': 'p2',
                'title': '法律依据',
                'content': '## 法律依据\n依据消费者权益保护法',
                'legal_references': [],
            },
            {
                'paragraph_id': 'p3',
                'title': '诉求',
                'content': '## 诉求\n请求退款',
                'legal_references': [],
            },
        ]
        content = '\n\n'.join(p['content'] for p in paragraphs)
        doc = _make_doc(self.case, self.run, content=content, paragraphs=paragraphs)

        result = asyncio.run(run_export_check(doc.id, run_id=self.run.id))

        elem_issues = [i for i in result.issues if i.code == 'MISSING_ELEMENT']
        self.assertEqual(elem_issues, [])
        self.assertEqual(result.missing_elements, [])


# ============================================================================
# SubTask 4.2.5 场景 5：stale 产物引用检查
# ============================================================================


class ExportCheckStaleArtifactTests(TransactionTestCase):
    """stale 产物引用检查测试。"""

    def setUp(self):
        _reset_law_retriever_cache()
        self.user = User.objects.create_user(username='stale-owner', password='pass')
        self.case = _make_case(self.user)
        self.run = _make_run(self.case)

    def test_stale_artifact_generates_warning(self):
        """case 下存在 status='stale' 的 WorkflowArtifact → STALE_ARTIFACT warning。"""
        doc = _make_doc(self.case, self.run, content='## 事实\n测试内容')
        WorkflowArtifact.objects.create(
            workflow_run=self.run,
            case=self.case,
            artifact_type='complaint_draft',
            stage='document_generation',
            status='stale',
            content={},
        )

        result = asyncio.run(run_export_check(doc.id, run_id=self.run.id))

        stale_issues = [i for i in result.issues if i.code == 'STALE_ARTIFACT']
        self.assertEqual(len(stale_issues), 1)
        # stale 产物是 warning（不阻塞导出，但提示用户）
        self.assertEqual(stale_issues[0].severity, 'warning')
        self.assertIn('artifact_id', stale_issues[0].details)

    def test_no_stale_artifact_when_status_current(self):
        """status='current' 的产物不触发 STALE_ARTIFACT issue。"""
        doc = _make_doc(self.case, self.run, content='## 事实\n测试内容')
        WorkflowArtifact.objects.create(
            workflow_run=self.run,
            case=self.case,
            artifact_type='complaint_draft',
            stage='document_generation',
            status='current',
            content={},
        )

        result = asyncio.run(run_export_check(doc.id, run_id=self.run.id))

        stale_issues = [i for i in result.issues if i.code == 'STALE_ARTIFACT']
        self.assertEqual(stale_issues, [])


# ============================================================================
# SubTask 4.2.5 场景 6：interrupt() 触发测试
# ============================================================================


class ComplaintNodeInterruptTests(TransactionTestCase):
    """complaint_node 在法条引用无效 + should_block_on_quality=True 时触发 interrupt。

    使用 TransactionTestCase 规避 sync_to_async 跨线程 SQLite 锁问题
    （详见 test_document_version.py 同名说明）。
    """

    def setUp(self):
        _reset_law_retriever_cache()
        self.user = User.objects.create_user(username='intr-owner', password='pass')
        self.case = _make_case(self.user)
        # 预创建 ComplaintTemplate 让 generate_complaint 骨架可命中（避免"材料尚未完整"）
        ComplaintTemplate.objects.create(
            case=self.case, template_type='platform',
            title='投诉书', content='## 当事人信息\n骨架内容\n\n## 诉求\n请求退款',
        )
        self.run = _make_run(self.case)

    def test_complaint_node_interrupts_when_legal_refs_invalid(self):
        """should_block_on_quality=True AND not valid → 调用 interrupt() + 创建 WorkflowIntervention。"""
        from api.agents.nodes.complaint_node import complaint_node

        rewritten_content = (
            '## 事实与理由\n商家欺诈，违反《虚构法律》第一条\n\n'
            '## 法律依据\n依据虚构法律\n\n'
            '## 诉求\n请求退款'
        )
        state = _make_node_state(self.case.id, workflow_run_id=self.run.id)

        # Mock validate_legal_references 返回 invalid 结果
        invalid_validation = ValidationResult(
            valid=False,
            invalid_refs=[{
                'paragraph_id': 'p1',
                'law_name': '虚构法律',
                'article_number': '第一条',
                'reason': 'LawArticle 表无此法条',
            }],
            total_refs=1,
            valid_refs=0,
        )

        with patch(
            'api.services.llm_service.is_llm_available',
            return_value=True,
        ), patch(
            'api.services.llm_service.chat_with_retry',
            return_value=rewritten_content,
        ), patch(
            'api.agents.tools.law_tools.is_tools_enabled',
            return_value=False,
        ), patch(
            'api.agents.tools.law_tools.pre_retrieve_law_articles',
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            'api.services.document_quality_service.validate_legal_references',
            new_callable=AsyncMock,
            return_value=invalid_validation,
        ), patch(
            'langgraph.types.interrupt',
        ) as mock_interrupt:
            asyncio.run(complaint_node(state))

        # 1. interrupt() 被调用
        self.assertTrue(mock_interrupt.called)
        call_args = mock_interrupt.call_args
        payload = call_args.args[0] if call_args.args else call_args.kwargs.get('value')

        # 2. payload 含必需字段（对齐 stage_gate_node 统一结构）
        self.assertEqual(payload['interrupt_type'], 'legal_confirmation')
        self.assertEqual(payload['intervention_kind'], 'legal_confirmation')
        self.assertEqual(payload['stage'], 'document_generation')
        self.assertEqual(payload['base_revision'], 5)
        self.assertTrue(payload['required'])
        self.assertIn('invalid_refs', payload)
        self.assertEqual(len(payload['invalid_refs']), 1)
        self.assertEqual(payload['invalid_refs'][0]['law_name'], '虚构法律')
        self.assertIn('form_schema', payload)
        self.assertIn('initial_values', payload)
        self.assertIn('impact', payload)

        # 3. WorkflowIntervention 记录已创建（legal_confirmation 类型，幂等）
        intervention = WorkflowIntervention.objects.filter(
            workflow_run_id=self.run.id,
            intervention_type='legal_confirmation',
            stage='document_generation',
            base_revision=5,
        ).first()
        self.assertIsNotNone(intervention)
        self.assertEqual(intervention.status, 'pending')

        # 4. payload 的 intervention_id 与 DB 记录 ID 一致
        self.assertEqual(payload['intervention_id'], intervention.id)

    def test_complaint_node_no_interrupt_when_legal_refs_valid(self):
        """法条引用有效 → 不调用 interrupt()。"""
        from api.agents.nodes.complaint_node import complaint_node

        # 预置真实法条（让 validate_legal_references 通过 DB 直查命中）
        LawArticle.objects.create(
            law_name='消费者权益保护法',
            article_number='第五十五条',
            content='经营者提供商品...',
            category='consumer_protection',
            is_active=True,
        )

        rewritten_content = (
            '## 事实与理由\n商家欺诈，违反《消费者权益保护法》第五十五条\n\n'
            '## 法律依据\n依据消费者权益保护法\n\n'
            '## 诉求\n请求退款'
        )
        state = _make_node_state(self.case.id, workflow_run_id=self.run.id)

        with patch(
            'api.services.llm_service.is_llm_available',
            return_value=True,
        ), patch(
            'api.services.llm_service.chat_with_retry',
            return_value=rewritten_content,
        ), patch(
            'api.agents.tools.law_tools.is_tools_enabled',
            return_value=False,
        ), patch(
            'api.agents.tools.law_tools.pre_retrieve_law_articles',
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            'langgraph.types.interrupt',
        ) as mock_interrupt:
            asyncio.run(complaint_node(state))

        # interrupt 未被调用
        self.assertFalse(mock_interrupt.called)


# ============================================================================
# 附加：run_export_check 整体集成测试
# ============================================================================


class RunExportCheckIntegrationTests(TransactionTestCase):
    """run_export_check 整体行为测试（checks_run 列表 + 文书不存在）。"""

    def setUp(self):
        _reset_law_retriever_cache()
        self.user = User.objects.create_user(username='intg-owner', password='pass')
        self.case = _make_case(self.user)
        self.run = _make_run(self.case)

    def test_export_check_returns_checks_run_list(self):
        """run_export_check 返回 checks_run 含 5 项检查名称。"""
        doc = _make_doc(self.case, self.run, content='测试内容')
        result = asyncio.run(run_export_check(doc.id, run_id=self.run.id))

        self.assertIsInstance(result, ExportCheckResult)
        self.assertIn('legal_references', result.checks_run)
        self.assertIn('amount_consistency', result.checks_run)
        self.assertIn('party_consistency', result.checks_run)
        self.assertIn('required_elements', result.checks_run)
        self.assertIn('stale_artifacts', result.checks_run)

    def test_export_check_document_not_found(self):
        """不存在的 document_id → passed=False + DOCUMENT_NOT_FOUND blocking。"""
        result = asyncio.run(run_export_check(999999, run_id=self.run.id))

        self.assertFalse(result.passed)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].code, 'DOCUMENT_NOT_FOUND')
        self.assertEqual(result.issues[0].severity, 'blocking')
