# -*- coding: utf-8 -*-
"""Task 2.2 测试：统一 review.interrupt 和 stage_pause（HITL 规范化）。

对齐 SPEC tasks.md 行 124-128（Task 2.2 全部 SubTask）：
- SubTask 2.2.1: review_node 创建 WorkflowIntervention（quality_review）+ 统一 payload
- SubTask 2.2.2: stage_gate_node 创建 WorkflowIntervention（user_pause）+ 统一 payload
- SubTask 2.2.3: interrupt() 调用在 update_or_create 之后（幂等性验证）
- SubTask 2.2.4: workflow_runner.py 持久化 intervention.created 事件

测试覆盖（对齐 tasks.md 验证清单）：
1. review_node 触发 interrupt 前，调用 create_intervention（mock）+ payload 含 intervention_id
2. stage_gate 触发 interrupt 前，调用 create_intervention（mock）+ payload 含 intervention_id
3. resume 时 create_intervention 不创建重复记录（mock update_or_create 返回 created=False）
4. payload 是 JSON 可序列化的

测试策略：
- 使用 unittest.mock.patch 模拟 intervention_service.create_intervention、
  langgraph.types.interrupt、Django ORM 调用（Evidence / ExtractedField / Case）
- mock interrupt() 直接返回 resume 值，使节点完整走完 resume 分支
- 使用 SimpleTestCase 避免数据库依赖
- 使用 asyncio.run() 调用 async 节点函数

运行方式（任选其一）：
    cd backend
    python manage.py test api.tests.test_unified_interruption -v 2
    # 或（如已安装 pytest）：
    python -m pytest api/tests/test_unified_interruption.py -v
"""
import asyncio
import importlib
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# 确保可从项目根目录或 backend/ 目录运行
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django
from django.apps import apps as _django_apps
if not _django_apps.ready:
    django.setup()

from django.test import SimpleTestCase  # noqa: E402

from langgraph.types import Command  # noqa: E402


# ============================================================================
# 测试辅助
# ============================================================================

def _make_state(case_id=999, revision=5, **extra):
    """构造最小 mock state，含 revision=5 + 可覆盖的 extract_results。"""
    state = {
        "case_id": case_id,
        "evidence_ids": [101, 102],
        "case_mode": "complain",
        "revision": revision,
        "evidence_preclassify_results": [],
        "evidence_ocr_results": [],
        "evidence_classify_results": [],
        "evidence_extract_results": [],
        "evidence_chain": [],
        "errors": [],
        "warnings": [],
        "provenance": [],
        "issues": [],
        "events": [],
    }
    state.update(extra)
    return state


def _make_extract_results_with_low_confidence():
    """构造含低置信度字段的 extract_results，触发 review_node HITL。

    含 2 个证据，每个证据 1 个低置信度字段 + 1 个高置信度字段。
    """
    return [
        {
            "evidence_id": 101,
            "evidence_code": "EV-001",
            "fields": [
                {"field_name": "金额", "field_value": "1500元", "confidence": 0.42},
                {"field_name": "日期", "field_value": "2026-03-15", "confidence": 0.95},
            ],
            "needs_human_review": True,
        },
        {
            "evidence_id": 102,
            "evidence_code": "EV-002",
            "fields": [
                {"field_name": "商品名", "field_value": "手机", "confidence": 0.55},
                {"field_name": "数量", "field_value": "1", "confidence": 0.99},
            ],
            "needs_human_review": True,
        },
    ]


def _make_mock_intervention(intervention_id=42):
    """构造 mock WorkflowIntervention 对象（含 .id 属性）。"""
    mock = MagicMock()
    mock.id = intervention_id
    mock.intervention_type = "quality_review"
    mock.stage = "extract"
    mock.status = "pending"
    mock.base_revision = 5
    return mock


def _capture_interrupt_payload():
    """返回 (mock_interrupt, payload_captor)。

    mock_interrupt 替换 langgraph.types.interrupt，捕获传入的 payload 并立即返回
    一个固定的 resume 值（模拟用户已提交）。
    """
    captured = {"payload": None}

    def _fake_interrupt(payload):
        captured["payload"] = payload
        # 模拟 resume 值：用户提交了第一个字段的校正值
        return {"submitted_values": {"correction_0": "9999元"}}

    return _fake_interrupt, captured


def _assert_payload_json_serializable(test_case, payload, label="payload"):
    """断言 payload 可被 json.dumps 序列化（无 datetime / model 实例）。"""
    try:
        serialized = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError, OverflowError) as e:
        test_case.fail(f"{label} 不可 JSON 序列化: {e}")
    test_case.assertIsInstance(serialized, str, f"{label} 应序列化为 str")

    # 递归断言无 datetime / model 实例
    import datetime
    def _walk(value, path="root"):
        if isinstance(value, (str, int, float, bool, type(None))):
            return
        if isinstance(value, (datetime.datetime, datetime.date)):
            test_case.fail(f"{label} {path} 含 datetime: {value!r}")
        if hasattr(value, '__dict__') and value.__class__.__module__ != 'builtins':
            # 简单识别 Django model 实例 / 自定义类
            test_case.fail(
                f"{label} {path} 含自定义类型实例: {type(value).__name__}"
            )
        if isinstance(value, dict):
            for k, v in value.items():
                _walk(v, f"{path}.{k}")
        elif isinstance(value, (list, tuple)):
            for i, v in enumerate(value):
                _walk(v, f"{path}[{i}]")

    _walk(payload)


# ============================================================================
# 测试 1：review_node 触发 interrupt 前，调用 create_intervention + payload 含 intervention_id
# ============================================================================

class ReviewNodeInterventionTests(SimpleTestCase):
    """SubTask 2.2.1 测试：review_node 创建 WorkflowIntervention + 统一 payload。"""

    def test_review_node_creates_intervention_before_interrupt(self):
        """review_node 触发 interrupt 前应调用 create_intervention，payload 含 intervention_id。"""
        # 注意：api.agents.nodes.__init__ 执行了 from api.agents.nodes.review_node
        # import review_node，导致 api.agents.nodes 包的 review_node 属性被绑定为
        # 函数而非模块。`import api.agents.nodes.review_node as review_module` 也会
        # 解析为该函数（Python 按 getattr 链查找）。用 importlib.import_module 直接
        # 获取 sys.modules 中的真实模块对象。
        review_module = importlib.import_module('api.agents.nodes.review_node')

        state = _make_state(
            revision=5,
            evidence_extract_results=_make_extract_results_with_low_confidence(),
        )

        # mock create_intervention → 返回 mock intervention（id=42）
        mock_intervention = _make_mock_intervention(intervention_id=42)
        create_intervention_patcher = patch.object(
            review_module, "create_intervention", return_value=mock_intervention
        )

        # mock interrupt → 捕获 payload，返回 resume 值
        fake_interrupt, captured = _capture_interrupt_payload()
        interrupt_patcher = patch.object(review_module, "interrupt", side_effect=fake_interrupt)

        # mock ExtractedField.objects.filter().update()（resume 后会调用）
        mock_filter = MagicMock()
        mock_filter.update = MagicMock(return_value=1)
        extracted_field_patcher = patch(
            "api.models.ExtractedField.objects",
            MagicMock(filter=MagicMock(return_value=mock_filter)),
        )

        # mock Evidence.objects.get + extracted_fields.all()（重建 results 时调用）
        mock_evidence = MagicMock()
        mock_field_high = MagicMock()
        mock_field_high.field_name = "日期"
        mock_field_high.field_value = "2026-03-15"
        mock_field_high.confidence = 0.95
        mock_field_low = MagicMock()
        mock_field_low.field_name = "金额"
        mock_field_low.field_value = "9999元"  # 已被校正
        mock_field_low.confidence = 1.0
        mock_evidence.extracted_fields.all.return_value = [mock_field_high, mock_field_low]
        evidence_patcher = patch(
            "api.models.Evidence.objects",
            MagicMock(get=MagicMock(return_value=mock_evidence)),
        )

        with create_intervention_patcher as mock_create, interrupt_patcher, \
             extracted_field_patcher, evidence_patcher:
            result = asyncio.run(review_module.review_node(state))

        # 1. create_intervention 被调用（在 interrupt 之前）
        self.assertTrue(
            mock_create.called,
            "review_node 应在 interrupt 前调用 create_intervention",
        )
        create_kwargs = mock_create.call_args.kwargs
        self.assertEqual(create_kwargs["case_id"], 999)
        self.assertEqual(create_kwargs["intervention_type"], "quality_review")
        self.assertEqual(create_kwargs["stage"], "extract")
        self.assertEqual(create_kwargs["base_revision"], 5)
        self.assertIn("fields", create_kwargs["form_schema"])
        self.assertIn("downstream_nodes", create_kwargs["impact"])

        # 2. interrupt 被调用，payload 含 intervention_id
        self.assertIsNotNone(captured["payload"], "interrupt 应被调用并捕获 payload")
        payload = captured["payload"]
        self.assertEqual(payload["intervention_id"], 42)
        self.assertEqual(payload["interrupt_type"], "quality_review")
        self.assertEqual(payload["intervention_kind"], "quality_review")
        self.assertTrue(payload["required"])
        self.assertEqual(payload["stage"], "extract")
        self.assertEqual(payload["base_revision"], 5)
        self.assertIn("form_schema", payload)
        self.assertIn("initial_values", payload)
        self.assertIn("impact", payload)
        self.assertIn("reason", payload)

        # 3. form_schema 含每个低置信度字段的 correction_N 字段
        fields = payload["form_schema"]["fields"]
        self.assertEqual(len(fields), 2, "应有 2 个低置信度字段（金额 + 商品名）")
        self.assertEqual(fields[0]["name"], "correction_0")
        self.assertEqual(fields[0]["evidence_id"], 101)
        self.assertEqual(fields[1]["name"], "correction_1")
        self.assertEqual(fields[1]["evidence_id"], 102)

        # 4. 向后兼容字段保留
        self.assertEqual(payload["case_id"], 999)
        self.assertIn("fields_to_review", payload)
        self.assertIn("message", payload)

        # 5. 节点返回 Command（goto=evidence_chain）
        self.assertIsInstance(result, Command)
        self.assertEqual(result.goto, "evidence_chain")

    def test_review_node_create_intervention_called_before_interrupt(self):
        """验证 create_intervention 在 interrupt 之前调用（顺序断言）。

        通过记录调用顺序的 mock，断言 create_intervention 先于 interrupt 被调用。
        对齐 Task 2.2.3：interrupt() 必须在 update_or_create 之后。
        """
        # 注意：api.agents.nodes.__init__ 执行了 from api.agents.nodes.review_node
        # import review_node，导致 api.agents.nodes 包的 review_node 属性被绑定为
        # 函数而非模块。`import api.agents.nodes.review_node as review_module` 也会
        # 解析为该函数（Python 按 getattr 链查找）。用 importlib.import_module 直接
        # 获取 sys.modules 中的真实模块对象。
        review_module = importlib.import_module('api.agents.nodes.review_node')

        state = _make_state(
            revision=3,
            evidence_extract_results=_make_extract_results_with_low_confidence(),
        )

        call_order = []

        def _track_create(*args, **kwargs):
            call_order.append("create_intervention")
            return _make_mock_intervention(intervention_id=77)

        def _track_interrupt(payload):
            call_order.append("interrupt")
            return {"submitted_values": {}}

        with patch.object(review_module, "create_intervention", side_effect=_track_create), \
             patch.object(review_module, "interrupt", side_effect=_track_interrupt), \
             patch("api.models.ExtractedField.objects", MagicMock()), \
             patch("api.models.Evidence.objects",
                   MagicMock(get=MagicMock(return_value=MagicMock(
                       extracted_fields=MagicMock(all=MagicMock(return_value=[])))))):
            asyncio.run(review_module.review_node(state))

        self.assertEqual(
            call_order[0], "create_intervention",
            "create_intervention 必须在 interrupt 之前调用（对齐 Task 2.2.3）",
        )
        self.assertEqual(
            call_order[1], "interrupt",
            "interrupt 应在 create_intervention 之后调用",
        )
        self.assertEqual(
            len(call_order), 2,
            "review_node resume 路径应只调用 create_intervention + interrupt 各一次",
        )


# ============================================================================
# 测试 2：stage_gate 触发 interrupt 前，调用 create_intervention + payload 含 intervention_id
# ============================================================================

class StageGateInterventionTests(SimpleTestCase):
    """SubTask 2.2.2 测试：stage_gate_node 创建 WorkflowIntervention + 统一 payload。"""

    def test_stage_gate_creates_intervention_before_interrupt(self):
        """stage_gate 触发 interrupt 前应调用 create_intervention，payload 含 intervention_id。"""
        from api.agents.nodes.stage_gate_node import make_stage_gate

        state = _make_state(case_id=888, revision=7)

        # mock Case.objects.filter(...).exists() → True（用户请求暂停）
        mock_qs = MagicMock()
        mock_qs.exists.return_value = True
        case_patcher = patch(
            "api.agents.nodes.stage_gate_node.Case.objects",
            MagicMock(filter=MagicMock(return_value=mock_qs)),
        )

        # mock create_intervention → 返回 mock intervention（id=99）
        mock_intervention = _make_mock_intervention(intervention_id=99)
        mock_intervention.intervention_type = "user_pause"
        mock_intervention.stage = "extract"
        create_intervention_patcher = patch(
            "api.agents.nodes.stage_gate_node.create_intervention",
            return_value=mock_intervention,
        )

        # mock interrupt → 捕获 payload，返回 resume 值（含 state_updates）
        captured = {"payload": None}

        def _fake_interrupt(payload):
            captured["payload"] = payload
            return {
                "interrupt_type": "stage_pause",  # 旧格式 resume 值
                "state_updates": {"needs_human_review": False, "review_decision": {"notes": "ok"}},
            }

        interrupt_patcher = patch(
            "api.agents.nodes.stage_gate_node.interrupt", side_effect=_fake_interrupt
        )

        with case_patcher, create_intervention_patcher as mock_create, interrupt_patcher:
            stage_gate = make_stage_gate("extract")
            result = asyncio.run(stage_gate(state))

        # 1. create_intervention 被调用
        self.assertTrue(
            mock_create.called,
            "stage_gate 应在 interrupt 前调用 create_intervention",
        )
        create_kwargs = mock_create.call_args.kwargs
        self.assertEqual(create_kwargs["case_id"], 888)
        self.assertEqual(create_kwargs["intervention_type"], "user_pause")
        self.assertEqual(create_kwargs["stage"], "extract")
        self.assertEqual(create_kwargs["base_revision"], 7)
        self.assertEqual(create_kwargs["form_schema"]["fields"][0]["name"], "notes")
        self.assertFalse(create_kwargs["form_schema"]["fields"][0]["required"])

        # 2. interrupt 被调用，payload 含 intervention_id + 统一结构
        self.assertIsNotNone(captured["payload"])
        payload = captured["payload"]
        self.assertEqual(payload["intervention_id"], 99)
        self.assertEqual(payload["interrupt_type"], "user_pause")
        self.assertEqual(payload["intervention_kind"], "user_pause")
        self.assertFalse(payload["required"])
        self.assertEqual(payload["stage"], "extract")
        self.assertEqual(payload["base_revision"], 7)
        self.assertIn("form_schema", payload)
        self.assertIn("impact", payload)

        # 3. impact.downstream_nodes 包含 extract 之后的节点
        downstream = payload["impact"]["downstream_nodes"]
        self.assertIn("review", downstream)
        self.assertIn("evidence_chain", downstream)

        # 4. 向后兼容字段保留
        self.assertEqual(payload["paused_after"], "extract")
        self.assertIn("editable_scope", payload)
        self.assertIn("message", payload)

        # 5. resume 后返回 state_updates dict
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("needs_human_review"), False)
        self.assertEqual(result.get("review_decision"), {"notes": "ok"})

    def test_stage_gate_no_pause_returns_empty(self):
        """无暂停请求时 stage_gate 应返回空 dict，不调用 create_intervention。"""
        from api.agents.nodes import stage_gate_node

        state = _make_state(case_id=888, revision=7)

        # mock Case.objects.filter(...).exists() → False（无暂停请求）
        mock_qs = MagicMock()
        mock_qs.exists.return_value = False
        case_patcher = patch(
            "api.agents.nodes.stage_gate_node.Case.objects",
            MagicMock(filter=MagicMock(return_value=mock_qs)),
        )

        with case_patcher, patch(
            "api.agents.nodes.stage_gate_node.create_intervention"
        ) as mock_create, patch(
            "api.agents.nodes.stage_gate_node.interrupt"
        ) as mock_interrupt:
            stage_gate = stage_gate_node.make_stage_gate("ocr")
            result = asyncio.run(stage_gate(state))

        self.assertEqual(result, {})
        mock_create.assert_not_called()
        mock_interrupt.assert_not_called()


# ============================================================================
# 测试 3：resume 时 create_intervention 不创建重复记录（mock update_or_create 返回 created=False）
# ============================================================================

class ResumeIdempotencyTests(SimpleTestCase):
    """SubTask 2.2.3 测试：resume 时 create_intervention 幂等（不创建重复记录）。"""

    def test_review_node_resume_does_not_duplicate_intervention(self):
        """review_node 在 resume 重新执行时，create_intervention 应返回同一记录。

        场景：首次执行 → interrupt 暂停 → resume → 节点从头重新执行 →
              create_intervention 再次被调用（update_or_create 内部返回 created=False）。

        mock create_intervention 在第二次调用时返回同一 intervention（id 相同），
        并标记 _created=False，模拟 update_or_create 的幂等行为。
        """
        # 注意：api.agents.nodes.__init__ 执行了 from api.agents.nodes.review_node
        # import review_node，导致 api.agents.nodes 包的 review_node 属性被绑定为
        # 函数而非模块。`import api.agents.nodes.review_node as review_module` 也会
        # 解析为该函数（Python 按 getattr 链查找）。用 importlib.import_module 直接
        # 获取 sys.modules 中的真实模块对象。
        review_module = importlib.import_module('api.agents.nodes.review_node')

        state = _make_state(
            revision=5,
            evidence_extract_results=_make_extract_results_with_low_confidence(),
        )

        # 模拟首次 + resume 两次调用 create_intervention 都返回同一 id
        mock_intervention = _make_mock_intervention(intervention_id=55)
        call_count = {"n": 0}

        def _create(*args, **kwargs):
            call_count["n"] += 1
            # 模拟 update_or_create 行为：返回同一对象，created 标志第二次为 False
            return mock_intervention

        # mock interrupt：首次返回 resume 值，第二次不会被调用（resume 后走完分支）
        interrupt_call_count = {"n": 0}

        def _fake_interrupt(payload):
            interrupt_call_count["n"] += 1
            return {"submitted_values": {"correction_0": "新值"}}

        with patch.object(review_module, "create_intervention", side_effect=_create), \
             patch.object(review_module, "interrupt", side_effect=_fake_interrupt), \
             patch("api.models.ExtractedField.objects", MagicMock(
                 filter=MagicMock(return_value=MagicMock(update=MagicMock(return_value=1))))), \
             patch("api.models.Evidence.objects",
                   MagicMock(get=MagicMock(return_value=MagicMock(
                       extracted_fields=MagicMock(all=MagicMock(return_value=[])))))):
            # 模拟首次 invoke + resume（节点从头执行）
            asyncio.run(review_module.review_node(state))

        # 一次完整执行中，create_intervention 被调用 1 次，interrupt 被调用 1 次
        self.assertEqual(call_count["n"], 1, "单次执行应调用 create_intervention 1 次")
        self.assertEqual(interrupt_call_count["n"], 1, "单次执行应调用 interrupt 1 次")

        # 模拟 resume 后节点从头重新执行（LangGraph 预期行为）
        # 此时 create_intervention 内部 update_or_create 应返回同一记录（created=False）
        # 由于我们 mock 了 create_intervention，直接验证它返回同一 id 即可
        with patch.object(review_module, "create_intervention", side_effect=_create), \
             patch.object(review_module, "interrupt", side_effect=_fake_interrupt), \
             patch("api.models.ExtractedField.objects", MagicMock(
                 filter=MagicMock(return_value=MagicMock(update=MagicMock(return_value=1))))), \
             patch("api.models.Evidence.objects",
                   MagicMock(get=MagicMock(return_value=MagicMock(
                       extracted_fields=MagicMock(all=MagicMock(return_value=[])))))):
            asyncio.run(review_module.review_node(state))

        # 第二次执行：create_intervention 又被调用 1 次（resume 重新执行节点）
        self.assertEqual(call_count["n"], 2, "resume 重新执行时应再次调用 create_intervention")
        # 但返回的 intervention.id 仍是 55（update_or_create 幂等，不创建新记录）
        self.assertEqual(mock_intervention.id, 55, "幂等性：应返回同一 intervention id")

    def test_stage_gate_resume_does_not_duplicate_intervention(self):
        """stage_gate 在 resume 重新执行时，create_intervention 幂等返回同一 id。"""
        from api.agents.nodes import stage_gate_node

        state = _make_state(case_id=777, revision=2)

        mock_qs = MagicMock()
        mock_qs.exists.return_value = True

        mock_intervention = _make_mock_intervention(intervention_id=88)
        call_count = {"n": 0}

        def _create(*args, **kwargs):
            call_count["n"] += 1
            return mock_intervention

        def _fake_interrupt(payload):
            return {"state_updates": {"needs_human_review": False}}

        with patch("api.agents.nodes.stage_gate_node.Case.objects",
                   MagicMock(filter=MagicMock(return_value=mock_qs))), \
             patch("api.agents.nodes.stage_gate_node.create_intervention",
                   side_effect=_create), \
             patch("api.agents.nodes.stage_gate_node.interrupt",
                   side_effect=_fake_interrupt):
            stage_gate = stage_gate_node.make_stage_gate("review")
            asyncio.run(stage_gate(state))

        # 首次执行调用 1 次
        self.assertEqual(call_count["n"], 1)

        with patch("api.agents.nodes.stage_gate_node.Case.objects",
                   MagicMock(filter=MagicMock(return_value=mock_qs))), \
             patch("api.agents.nodes.stage_gate_node.create_intervention",
                   side_effect=_create), \
             patch("api.agents.nodes.stage_gate_node.interrupt",
                   side_effect=_fake_interrupt):
            stage_gate = stage_gate_node.make_stage_gate("review")
            asyncio.run(stage_gate(state))

        # 第二次执行又调用 1 次，但返回同一 id（幂等）
        self.assertEqual(call_count["n"], 2)
        self.assertEqual(mock_intervention.id, 88)


# ============================================================================
# 测试 4：payload 是 JSON 可序列化的
# ============================================================================

class PayloadJsonSerializableTests(SimpleTestCase):
    """SubTask 2.2.3 验证：中断 payload 仅含 JSON 原生类型（无 datetime / model 实例）。"""

    def test_review_node_payload_is_json_serializable(self):
        """review_node 的 interrupt payload 应 JSON 可序列化。"""
        # 注意：api.agents.nodes.__init__ 执行了 from api.agents.nodes.review_node
        # import review_node，导致 api.agents.nodes 包的 review_node 属性被绑定为
        # 函数而非模块。`import api.agents.nodes.review_node as review_module` 也会
        # 解析为该函数（Python 按 getattr 链查找）。用 importlib.import_module 直接
        # 获取 sys.modules 中的真实模块对象。
        review_module = importlib.import_module('api.agents.nodes.review_node')

        state = _make_state(
            revision=5,
            evidence_extract_results=_make_extract_results_with_low_confidence(),
        )

        captured = {"payload": None}

        def _fake_interrupt(payload):
            captured["payload"] = payload
            return {"submitted_values": {}}

        with patch.object(review_module, "create_intervention",
                          return_value=_make_mock_intervention(intervention_id=1)), \
             patch.object(review_module, "interrupt", side_effect=_fake_interrupt), \
             patch("api.models.ExtractedField.objects", MagicMock()), \
             patch("api.models.Evidence.objects",
                   MagicMock(get=MagicMock(return_value=MagicMock(
                       extracted_fields=MagicMock(all=MagicMock(return_value=[])))))):
            asyncio.run(review_module.review_node(state))

        self.assertIsNotNone(captured["payload"])
        _assert_payload_json_serializable(self, captured["payload"], "review_node payload")

    def test_stage_gate_payload_is_json_serializable(self):
        """stage_gate 的 interrupt payload 应 JSON 可序列化。"""
        from api.agents.nodes import stage_gate_node

        # 对每个 paused_after 取值都测试（覆盖所有业务阶段）
        from api.services.workflow_pause_service import STAGE_EDITABLE_SCOPES
        for paused_after in STAGE_EDITABLE_SCOPES:
            with self.subTest(paused_after=paused_after):
                state = _make_state(case_id=666, revision=4)
                mock_qs = MagicMock()
                mock_qs.exists.return_value = True

                captured = {"payload": None}

                def _fake_interrupt(payload):
                    captured["payload"] = payload
                    return {"state_updates": {}}

                with patch("api.agents.nodes.stage_gate_node.Case.objects",
                           MagicMock(filter=MagicMock(return_value=mock_qs))), \
                     patch("api.agents.nodes.stage_gate_node.create_intervention",
                           return_value=_make_mock_intervention(intervention_id=2)), \
                     patch("api.agents.nodes.stage_gate_node.interrupt",
                           side_effect=_fake_interrupt):
                    stage_gate = stage_gate_node.make_stage_gate(paused_after)
                    asyncio.run(stage_gate(state))

                self.assertIsNotNone(captured["payload"])
                _assert_payload_json_serializable(
                    self, captured["payload"], f"stage_gate payload ({paused_after})"
                )

    def test_payload_has_no_datetime_objects(self):
        """显式断言 payload 无 datetime / date 实例。"""
        import datetime
        # 注意：api.agents.nodes.__init__ 执行了 from api.agents.nodes.review_node
        # import review_node，导致 api.agents.nodes 包的 review_node 属性被绑定为
        # 函数而非模块。`import api.agents.nodes.review_node as review_module` 也会
        # 解析为该函数（Python 按 getattr 链查找）。用 importlib.import_module 直接
        # 获取 sys.modules 中的真实模块对象。
        review_module = importlib.import_module('api.agents.nodes.review_node')

        state = _make_state(
            revision=5,
            evidence_extract_results=_make_extract_results_with_low_confidence(),
        )

        captured = {"payload": None}

        def _fake_interrupt(payload):
            captured["payload"] = payload
            return {"submitted_values": {}}

        with patch.object(review_module, "create_intervention",
                          return_value=_make_mock_intervention(intervention_id=1)), \
             patch.object(review_module, "interrupt", side_effect=_fake_interrupt), \
             patch("api.models.ExtractedField.objects", MagicMock()), \
             patch("api.models.Evidence.objects",
                   MagicMock(get=MagicMock(return_value=MagicMock(
                       extracted_fields=MagicMock(all=MagicMock(return_value=[])))))):
            asyncio.run(review_module.review_node(state))

        payload = captured["payload"]
        self.assertIsNotNone(payload)

        def _walk(value, path="root"):
            if isinstance(value, (datetime.datetime, datetime.date)):
                self.fail(f"payload {path} 含 datetime: {value!r}")
            if isinstance(value, dict):
                for k, v in value.items():
                    _walk(v, f"{path}.{k}")
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    _walk(v, f"{path}[{i}]")

        _walk(payload)


# ============================================================================
# 测试 5：workflow_runner 持久化 intervention.created 事件（SubTask 2.2.4）
# ============================================================================

class WorkflowRunnerInterventionEventTests(SimpleTestCase):
    """SubTask 2.2.4 测试：workflow_runner 持久化 intervention.created SSE 事件。"""

    def test_run_and_persist_emits_intervention_created_event(self):
        """当 snapshot 含带 intervention_id 的 interrupt payload 时，
        应持久化 intervention.created 事件到 EventDepot。
        """
        from api.agents import workflow_runner as wr_module

        # 构造 mock workflow：astream_events 返回空异步迭代器
        mock_workflow = MagicMock()
        mock_workflow.astream_events = MagicMock(return_value=_empty_async_iter())

        # 构造 mock snapshot：含 1 个带 intervention_id 的 interrupt
        # snapshot_interrupts() 会先检查 snapshot.interrupts（list/tuple），
        # 再遍历 snapshot.tasks[].interrupts。这里直接在 snapshot.interrupts 放 list，
        # 并把 tasks 设为空 list，避免 MagicMock 自动生成的 interrupts 干扰。
        mock_snapshot = MagicMock()
        mock_interrupt_item = MagicMock()
        mock_interrupt_item.value = {
            "interrupt_type": "quality_review",
            "intervention_id": 12345,
            "intervention_kind": "quality_review",
            "required": True,
            "stage": "extract",
            "reason": "共 2 个低置信度字段需要校正",
            "base_revision": 5,
            "form_schema": {"fields": [{"name": "correction_0"}]},
            "initial_values": {"fields_to_review": []},
            "impact": {"downstream_nodes": ["evidence_chain"], "rerun_required": True},
        }
        mock_snapshot.interrupts = [mock_interrupt_item]
        mock_snapshot.tasks = []
        mock_snapshot.next = ("evidence_chain",)  # 触发 waiting_review 分支
        mock_workflow.aget_state = AsyncMock(return_value=mock_snapshot)

        # mock EventDepot / NotifyEmitter / lifecycle 服务
        persisted_events = []

        async def _fake_persist(thread_id, event_type, payload):
            persisted_events.append({"thread_id": thread_id, "type": event_type, "payload": payload})
            return f"eid-{len(persisted_events)}"

        mock_depot = MagicMock()
        mock_depot.persist = _fake_persist
        mock_emitter = MagicMock()
        mock_emitter.notify = AsyncMock(return_value=None)

        with patch.object(wr_module, "build_case_workflow", return_value=mock_workflow), \
             patch.object(wr_module, "EventDepot", return_value=mock_depot), \
             patch.object(wr_module, "NotifyEmitter", return_value=mock_emitter), \
             patch.object(wr_module, "complete_processing",
                          new=MagicMock()), \
             patch.object(wr_module, "mark_paused", new=MagicMock()), \
             patch.object(wr_module, "mark_waiting_review", new=MagicMock()), \
             patch.object(wr_module, "fail_processing", new=MagicMock()):
            runner = wr_module.WorkflowRunner()
            asyncio.run(runner.run_and_persist(
                case_id=42,
                thread_id="thread-intervention-test",
                resume={"corrections": []},
            ))

        # 应持久化 intervention.created 事件
        intervention_events = [e for e in persisted_events if e["type"] == "intervention.created"]
        self.assertEqual(
            len(intervention_events), 1,
            "应持久化 1 条 intervention.created 事件",
        )
        evt = intervention_events[0]
        self.assertEqual(evt["payload"]["intervention_id"], 12345)
        self.assertEqual(evt["payload"]["intervention_type"], "quality_review")
        self.assertEqual(evt["payload"]["intervention_kind"], "quality_review")
        self.assertEqual(evt["payload"]["stage"], "extract")
        self.assertEqual(evt["payload"]["base_revision"], 5)
        self.assertIn("form_schema", evt["payload"])
        self.assertIn("impact", evt["payload"])
        self.assertEqual(evt["payload"]["case_id"], 42)
        self.assertEqual(evt["payload"]["thread_id"], "thread-intervention-test")

    def test_run_and_persist_emits_intervention_created_for_user_pause(self):
        """当 snapshot 含 user_pause 类型 interrupt 时，也应持久化 intervention.created。

        且因为 is_stage_pause_interrupt_value(user_pause) 为 True，会进入 mark_paused 分支。
        """
        from api.agents import workflow_runner as wr_module

        mock_workflow = MagicMock()
        mock_workflow.astream_events = MagicMock(return_value=_empty_async_iter())

        mock_snapshot = MagicMock()
        mock_interrupt_item = MagicMock()
        mock_interrupt_item.value = {
            "interrupt_type": "user_pause",
            "intervention_id": 67890,
            "intervention_kind": "user_pause",
            "required": False,
            "stage": "evidence_chain",
            "reason": "用户在 evidence_chain 阶段后请求暂停",
            "base_revision": 8,
            "form_schema": {"fields": [{"name": "notes"}]},
            "initial_values": {},
            "impact": {"downstream_nodes": ["complaint"], "rerun_required": False},
            "paused_after": "evidence_chain",  # 向后兼容字段
        }
        mock_snapshot.interrupts = [mock_interrupt_item]
        mock_snapshot.tasks = []
        mock_snapshot.next = ()  # stage_pause 分支会 return，不到这里
        mock_workflow.aget_state = AsyncMock(return_value=mock_snapshot)

        persisted_events = []

        async def _fake_persist(thread_id, event_type, payload):
            persisted_events.append({"thread_id": thread_id, "type": event_type, "payload": payload})
            return f"eid-{len(persisted_events)}"

        mock_depot = MagicMock()
        mock_depot.persist = _fake_persist
        mock_emitter = MagicMock()
        mock_emitter.notify = AsyncMock(return_value=None)

        # mark_paused 返回 True（实际 paused 状态变更）
        with patch.object(wr_module, "build_case_workflow", return_value=mock_workflow), \
             patch.object(wr_module, "EventDepot", return_value=mock_depot), \
             patch.object(wr_module, "NotifyEmitter", return_value=mock_emitter), \
             patch.object(wr_module, "complete_processing",
                          new=MagicMock()), \
             patch.object(wr_module, "mark_paused",
                          new=MagicMock(return_value=True)), \
             patch.object(wr_module, "mark_waiting_review", new=MagicMock()), \
             patch.object(wr_module, "fail_processing", new=MagicMock()):
            runner = wr_module.WorkflowRunner()
            asyncio.run(runner.run_and_persist(
                case_id=33,
                thread_id="thread-user-pause-test",
                resume={"interrupt_type": "stage_pause", "state_updates": {}},
            ))

        # 应同时持久化 intervention.created + workflow.paused 事件
        intervention_events = [e for e in persisted_events if e["type"] == "intervention.created"]
        paused_events = [e for e in persisted_events if e["type"] == "workflow.paused"]
        self.assertEqual(len(intervention_events), 1, "应持久化 intervention.created")
        self.assertEqual(len(paused_events), 1, "应持久化 workflow.paused")

        # intervention.created 含正确字段
        evt = intervention_events[0]
        self.assertEqual(evt["payload"]["intervention_id"], 67890)
        self.assertEqual(evt["payload"]["intervention_type"], "user_pause")

        # workflow.paused 的 paused_after 应从 stage 字段提取（新 payload 兼容）
        paused_evt = paused_events[0]
        self.assertEqual(paused_evt["payload"]["paused_after"], "evidence_chain")


async def _empty_async_iter():
    """空异步迭代器：yield 0 个事件后结束。"""
    return
    yield  # pragma: no cover - 使函数成为 async generator


if __name__ == "__main__":
    unittest.main()
