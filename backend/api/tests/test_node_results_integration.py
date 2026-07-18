# -*- coding: utf-8 -*-
"""Task 1.2 集成测试：验证 8 个节点统一返回 NodeResult 兼容结构。

对齐 SPEC（tasks.md 行 54-63）：每个节点的 partial update dict 必须含
`node_result / revision / current_stage / current_node / progress /
provenance / warnings / issues / events` 字段。

测试覆盖：
1. 每个节点返回的 partial update dict 含必需字段
2. revision 单调递增（mock state 含 revision=5，节点返回 revision=6）
3. node_result 字段是 dict，含 node / quality / metrics / data / warnings / errors / provenance 子键
4. quality 含 score / status / coverage；metrics 含 duration_ms
5. events 列表含 node.completed 事件
6. review_node 特殊处理：返回 Command(update=partial, goto="evidence_chain")，
   partial 中含 node_result 字段
7. 旧业务字段（evidence_preclassify_results / evidence_ocr_results /
   evidence_classify_results / evidence_extract_results / complaint_draft 等）
   保留在 partial 中（向后兼容）
8. errors 字段为 list[dict]（对齐 Task 0.1 BREAKING 变更）

测试策略：
- 使用 unittest.mock.patch 模拟 Django ORM 调用（Evidence / Case 等）
- 触发各节点的 early-exit / degraded 路径（无证据 / 案件不存在 / 无 OCR 结果 /
  无低置信度字段等），避免复杂的 LLM / OCR 业务逻辑 mocking
- 使用 asyncio.run() 调用 async 节点函数
- 使用 SimpleTestCase 避免数据库依赖

运行方式（任选其一）：
    cd backend
    python manage.py test api.tests.test_node_results_integration -v 2
    # 或（如已安装 pytest）：
    python -m pytest api/tests/test_node_results_integration.py -v
"""
import asyncio
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# 确保可从项目根目录或 backend/ 目录运行（backend/ 需在 sys.path 上以解析 claimcraft.settings）
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# 配置 Django（幂等：manage.py test 运行时 Django 已由 runner 配置，此处为 no-op；
# pytest / 独立运行时由本 shim 完成配置，使 from api.agents.* import ... 可用）
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django
from django.apps import apps as _django_apps
if not _django_apps.ready:
    django.setup()

from django.test import SimpleTestCase  # noqa: E402  (import 在 Django setup 之后)

from langgraph.types import Command  # noqa: E402

# 每个节点的 partial update dict 都应含这些键（Task 1.2 统一契约）
REQUIRED_PARTIAL_FIELDS = (
    "node_result",
    "revision",
    "current_stage",
    "current_node",
    "progress",
    "provenance",
    "warnings",
    "issues",
    "events",
)

# node_result 子结构必需键（NodeResult.model_dump() 后）
NODE_RESULT_KEYS = ("node", "data", "quality", "warnings", "errors", "provenance", "metrics")

# mock state 初始 revision（用于断言单调递增）
INITIAL_REVISION = 5
EXPECTED_REVISION = INITIAL_REVISION + 1  # 节点应返回 6


def _make_state(case_id=999, revision=INITIAL_REVISION, **extra):
    """构造最小 mock state，含 revision=5 用于单调递增断言。

    Args:
        case_id: 案件 ID（默认 999，避免与真实案件冲突）
        revision: 初始 revision（默认 5）
        **extra: 额外 state 字段（覆盖默认空列表）
    """
    state = {
        "case_id": case_id,
        "evidence_ids": [],
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


def _mock_empty_queryset():
    """Mock Django ORM 链式调用：filter().exclude().exclude().order_by() → 空可迭代。

    MagicMock 默认 __iter__ 返回 iter([])，故 list(qs) → []。
    链式方法（filter/exclude/order_by）默认返回新 MagicMock，同样可迭代为空。
    """
    qs = MagicMock()
    qs.exclude.return_value = qs
    qs.filter.return_value = qs
    qs.order_by.return_value = qs
    return qs


def _assert_node_result_contract(
    test_case,
    partial,
    expected_node,
    expected_stage,
    expected_progress=None,
):
    """断言 partial update dict 符合 Task 1.2 NodeResult 统一契约。

    Args:
        test_case: unittest.TestCase / SimpleTestCase 实例
        partial: 节点返回的 partial update dict
        expected_node: 期望的节点名（如 "preclassify"）
        expected_stage: 期望的业务阶段（如 "material_understanding"）
        expected_progress: 期望的 progress 值（可选，None 时不校验具体值）
    """
    # 1. 必需字段全部存在
    for field in REQUIRED_PARTIAL_FIELDS:
        test_case.assertIn(
            field, partial,
            f"节点 {expected_node} 返回的 partial update dict 缺少必需字段: {field}",
        )

    # 2. revision 单调递增（mock state revision=5 → 节点返回 revision=6）
    test_case.assertEqual(
        partial["revision"], EXPECTED_REVISION,
        f"节点 {expected_node} revision 应为 {EXPECTED_REVISION}（mock state revision={INITIAL_REVISION} + 1）",
    )

    # 3. current_node / current_stage 正确
    test_case.assertEqual(partial["current_node"], expected_node)
    test_case.assertEqual(partial["current_stage"], expected_stage)

    # 4. progress 在 [0, 1] 区间
    test_case.assertGreaterEqual(partial["progress"], 0.0)
    test_case.assertLessEqual(partial["progress"], 1.0)
    if expected_progress is not None:
        test_case.assertEqual(
            partial["progress"], expected_progress,
            f"节点 {expected_node} progress 应为 {expected_progress}",
        )

    # 5. node_result 是 dict，含 NodeResult.model_dump() 全部子键
    test_case.assertIsInstance(partial["node_result"], dict)
    for key in NODE_RESULT_KEYS:
        test_case.assertIn(
            key, partial["node_result"],
            f"节点 {expected_node} node_result 缺少子键: {key}",
        )

    # 6. node_result.node 等于节点名
    test_case.assertEqual(partial["node_result"]["node"], expected_node)

    # 7. quality 子结构存在 + 必需键
    quality = partial["node_result"]["quality"]
    test_case.assertIsInstance(quality, dict)
    test_case.assertIn("score", quality)
    test_case.assertIn("status", quality)
    test_case.assertIn("coverage", quality)
    test_case.assertIn(quality["status"], ("pass", "warn", "fail"))

    # 8. metrics 子结构存在 + duration_ms
    metrics = partial["node_result"]["metrics"]
    test_case.assertIsInstance(metrics, dict)
    test_case.assertIn("duration_ms", metrics)
    test_case.assertIsInstance(metrics["duration_ms"], int)
    test_case.assertGreaterEqual(metrics["duration_ms"], 0)

    # 9. events 列表含 node.completed 事件
    test_case.assertIsInstance(partial["events"], list)
    test_case.assertTrue(
        any(isinstance(e, dict) and e.get("event_type") == "node.completed" for e in partial["events"]),
        f"节点 {expected_node} events 应含 node.completed 事件",
    )

    # 10. issues 是 list
    test_case.assertIsInstance(partial["issues"], list)

    # 11. provenance / warnings 是 list
    test_case.assertIsInstance(partial["provenance"], list)
    test_case.assertIsInstance(partial["warnings"], list)

    # 12. node_result.errors 是 list[dict]（对齐 Task 0.1 BREAKING）
    errors = partial["node_result"]["errors"]
    test_case.assertIsInstance(errors, list)
    for err in errors:
        test_case.assertIsInstance(
            err, dict,
            f"节点 {expected_node} node_result.errors 元素应为 dict（对齐 Task 0.1 BREAKING），实际: {type(err)}",
        )


# ============================================================================
# SubTask 1.2.1: preclassify_node
# ============================================================================

class PreclassifyNodeContractTest(SimpleTestCase):
    """preclassify_node 返回 NodeResult 兼容结构（early-exit: 无证据图片路径）。"""

    def test_preclassify_returns_node_result_partial_update(self):
        from api.agents.nodes.preclassify_node import preclassify_node
        from api.models import Evidence

        state = _make_state(revision=INITIAL_REVISION)
        mock_qs = _mock_empty_queryset()

        with patch.object(Evidence.objects, 'filter', return_value=mock_qs):
            partial = asyncio.run(preclassify_node(state))

        _assert_node_result_contract(
            self, partial,
            expected_node="preclassify",
            expected_stage="material_understanding",
            expected_progress=0.10,
        )
        # 旧字段保留（向后兼容）
        self.assertIn("evidence_preclassify_results", partial)
        self.assertEqual(partial["evidence_preclassify_results"], [])
        # errors 是 list[dict]
        self.assertIn("errors", partial)
        for err in partial["errors"]:
            self.assertIsInstance(err, dict)


# ============================================================================
# SubTask 1.2.2: ocr_node
# ============================================================================

class OcrNodeContractTest(SimpleTestCase):
    """ocr_node 返回 NodeResult 兼容结构（early-exit: 无可识别证据图片）。"""

    def test_ocr_returns_node_result_partial_update(self):
        from api.agents.nodes.ocr_node import ocr_node
        from api.models import Evidence

        state = _make_state(revision=INITIAL_REVISION)
        mock_qs = _mock_empty_queryset()

        with patch.object(Evidence.objects, 'filter', return_value=mock_qs):
            partial = asyncio.run(ocr_node(state))

        _assert_node_result_contract(
            self, partial,
            expected_node="ocr",
            expected_stage="material_understanding",
            expected_progress=0.20,
        )
        # 旧字段保留
        self.assertIn("evidence_ocr_results", partial)
        self.assertEqual(partial["evidence_ocr_results"], [])


# ============================================================================
# SubTask 1.2.3: classify_node
# ============================================================================

class ClassifyNodeContractTest(SimpleTestCase):
    """classify_node 返回 NodeResult 兼容结构（degraded: 无预分类结果）。"""

    def test_classify_returns_node_result_partial_update_when_no_preclassify(self):
        from api.agents.nodes.classify_node import classify_node

        # 无预分类结果 → 降级路径，无需 LLM / DB 调用
        state = _make_state(
            revision=INITIAL_REVISION,
            evidence_preclassify_results=[],
            evidence_ocr_results=[],  # 也为空，避免降级路径构造结果时遍历
        )

        partial = asyncio.run(classify_node(state))

        _assert_node_result_contract(
            self, partial,
            expected_node="classify",
            expected_stage="material_understanding",
            expected_progress=0.30,
        )
        # 旧字段保留
        self.assertIn("evidence_classify_results", partial)
        self.assertEqual(partial["evidence_classify_results"], [])


# ============================================================================
# SubTask 1.2.4: extract_node
# ============================================================================

class ExtractNodeContractTest(SimpleTestCase):
    """extract_node 返回 NodeResult 兼容结构（early-exit: 无 OCR 结果）。"""

    def test_extract_returns_node_result_partial_update_when_no_ocr(self):
        from api.agents.nodes.extract_node import extract_node

        # 无 OCR 结果 → early-exit，无需 LLM / DB 调用
        state = _make_state(
            revision=INITIAL_REVISION,
            evidence_ocr_results=[],
        )

        partial = asyncio.run(extract_node(state))

        _assert_node_result_contract(
            self, partial,
            expected_node="extract",
            expected_stage="fact_checking",
            expected_progress=0.45,
        )
        # 旧字段保留
        self.assertIn("evidence_extract_results", partial)
        self.assertEqual(partial["evidence_extract_results"], [])
        self.assertIn("needs_human_review", partial)
        self.assertFalse(partial["needs_human_review"])


# ============================================================================
# SubTask 1.2.5: review_node（特殊处理：Command 包装）
# ============================================================================

class ReviewNodeContractTest(SimpleTestCase):
    """review_node 返回 Command(update=partial, goto=...)，partial 含 node_result。

    特殊处理（对齐 SPEC 行 59）：
    - review_node 不返回 dict，而是返回 Command 对象（goto="evidence_chain"）
    - 但 Command.update 内的 partial dict 仍需含全部 NodeResult 契约字段
    - early-exit 路径：无低置信度字段 → 跳过 HITL，直接返回 Command
    """

    def test_review_skip_hitl_returns_command_with_node_result(self):
        from api.agents.nodes.review_node import review_node

        # evidence_extract_results 为空 → 无低置信度字段 → 跳过 HITL
        state = _make_state(
            revision=INITIAL_REVISION,
            evidence_extract_results=[],
        )

        result = asyncio.run(review_node(state))

        # 必须返回 Command（特殊处理）
        self.assertIsInstance(
            result, Command,
            f"review_node 应返回 Command 对象（特殊处理），实际类型: {type(result)}",
        )

        # Command.update 含 node_result 等 NodeResult 契约字段
        partial = result.update
        self.assertIsInstance(partial, dict, "Command.update 应为 dict")

        _assert_node_result_contract(
            self, partial,
            expected_node="review",
            expected_stage="fact_checking",
            expected_progress=0.55,
        )

        # Command.goto 指向 evidence_chain
        self.assertEqual(result.goto, "evidence_chain")

    def test_review_skip_hitl_node_result_marks_skipped(self):
        """review_node 跳过 HITL 时 node_result.data 应含 skipped=True 标记。"""
        from api.agents.nodes.review_node import review_node

        state = _make_state(
            revision=INITIAL_REVISION,
            evidence_extract_results=[],
        )

        result = asyncio.run(review_node(state))
        partial = result.update

        # node_result.data 含 skipped=True
        self.assertTrue(partial["node_result"]["data"].get("skipped"))
        # quality.status 应为 pass（无低置信度字段 = 无需校正）
        self.assertEqual(partial["node_result"]["quality"]["status"], "pass")


# ============================================================================
# SubTask 1.2.6: evidence_chain_node
# ============================================================================

class EvidenceChainNodeContractTest(SimpleTestCase):
    """evidence_chain_node 返回 NodeResult 兼容结构（early-exit: 案件不存在）。"""

    def test_evidence_chain_returns_node_result_partial_update_when_case_missing(self):
        from api.agents.nodes.evidence_chain_node import evidence_chain_node
        from api.models import Case

        state = _make_state(revision=INITIAL_REVISION)

        # Case.objects.get 抛 DoesNotExist → early-exit
        with patch.object(Case.objects, 'get', side_effect=Case.DoesNotExist("case not found")):
            partial = asyncio.run(evidence_chain_node(state))

        _assert_node_result_contract(
            self, partial,
            expected_node="evidence_chain",
            expected_stage="case_organization",
            expected_progress=0.70,
        )
        # 旧字段保留（evidence_chain 节点返回 evidence_chain 空列表）
        self.assertIn("evidence_chain", partial)


# ============================================================================
# SubTask 1.2.7: complaint_node
# ============================================================================

class ComplaintNodeContractTest(SimpleTestCase):
    """complaint_node 返回 NodeResult 兼容结构（early-exit: 案件不存在）。"""

    def test_complaint_returns_node_result_partial_update_when_case_missing(self):
        from api.agents.nodes.complaint_node import complaint_node
        from api.models import Case

        state = _make_state(revision=INITIAL_REVISION)

        with patch.object(Case.objects, 'get', side_effect=Case.DoesNotExist("case not found")):
            partial = asyncio.run(complaint_node(state))

        _assert_node_result_contract(
            self, partial,
            expected_node="complaint",
            expected_stage="document_generation",
            expected_progress=0.90,
        )
        # 旧字段保留
        self.assertIn("complaint_draft", partial)
        self.assertIsNone(partial["complaint_draft"])


# ============================================================================
# SubTask 1.2.8: respond_complaint_node
# ============================================================================

class RespondComplaintNodeContractTest(SimpleTestCase):
    """respond_complaint_node 返回 NodeResult 兼容结构（early-exit: 案件不存在）。"""

    def test_respond_complaint_returns_node_result_partial_update_when_case_missing(self):
        from api.agents.nodes.respond_complaint_node import respond_complaint_node
        from api.models import Case

        state = _make_state(revision=INITIAL_REVISION)

        with patch.object(Case.objects, 'get', side_effect=Case.DoesNotExist("case not found")):
            partial = asyncio.run(respond_complaint_node(state))

        _assert_node_result_contract(
            self, partial,
            expected_node="respond_complaint",
            expected_stage="document_generation",
            expected_progress=0.90,
        )
        # 旧字段保留（与 complaint_node 一致，复用 complaint_draft 字段名）
        self.assertIn("complaint_draft", partial)
        self.assertIsNone(partial["complaint_draft"])


# ============================================================================
# SubTask 1.2.9: 节点返回 partial update dict，不 mutate 整个 state
# ============================================================================

class PartialUpdateNoMutationTest(SimpleTestCase):
    """验证节点返回的是 partial update dict（仅含 update 字段），不 mutate 整个 state。"""

    def test_preclassify_partial_does_not_include_unrelated_state_keys(self):
        """preclassify 返回的 partial 不应含 case_id / case_mode 等无关 state 字段。

        即节点仅返回 update 子集，LangGraph 负责 merge 到完整 state。
        """
        from api.agents.nodes.preclassify_node import preclassify_node
        from api.models import Evidence

        state = _make_state(revision=INITIAL_REVISION)
        mock_qs = _mock_empty_queryset()

        with patch.object(Evidence.objects, 'filter', return_value=mock_qs):
            partial = asyncio.run(preclassify_node(state))

        # 不应含原 state 的 case_id / case_mode（这些字段节点未变更，不应在 partial 中）
        self.assertNotIn("case_id", partial)
        self.assertNotIn("case_mode", partial)
        self.assertNotIn("evidence_ids", partial)

    def test_classify_partial_does_not_mutate_state_argument(self):
        """classify_node 不应直接修改传入的 state dict（应返回新 dict）。"""
        from api.agents.nodes.classify_node import classify_node

        state = _make_state(
            revision=INITIAL_REVISION,
            evidence_preclassify_results=[],
            evidence_ocr_results=[],
        )
        # 记录 state 原始键集合
        original_keys = set(state.keys())
        original_revision = state["revision"]

        partial = asyncio.run(classify_node(state))

        # state 参数未被 mutate（键集合不变、revision 不变）
        self.assertEqual(set(state.keys()), original_keys)
        self.assertEqual(state["revision"], original_revision)
        # partial 是新 dict（与 state 不是同一对象）
        self.assertIsNot(partial, state)


# ============================================================================
# 跨节点：revision 单调递增专项测试
# ============================================================================

class RevisionMonotonicIncrementTest(SimpleTestCase):
    """验证 revision 单调递增（对齐 checklist.md 行 74：revision 单调递增测试）。

    场景：mock state 含 revision=5，节点应返回 revision=6。
    多次构造不同 revision 的 state 验证递增规律。
    """

    def test_revision_increments_from_zero(self):
        """revision=0 → 节点返回 revision=1。"""
        from api.agents.nodes.classify_node import classify_node

        state = _make_state(
            revision=0,
            evidence_preclassify_results=[],
            evidence_ocr_results=[],
        )
        partial = asyncio.run(classify_node(state))
        self.assertEqual(partial["revision"], 1)

    def test_revision_increments_from_five(self):
        """revision=5 → 节点返回 revision=6。"""
        from api.agents.nodes.classify_node import classify_node

        state = _make_state(
            revision=5,
            evidence_preclassify_results=[],
            evidence_ocr_results=[],
        )
        partial = asyncio.run(classify_node(state))
        self.assertEqual(partial["revision"], 6)

    def test_revision_increments_from_large_value(self):
        """revision=999 → 节点返回 revision=1000。"""
        from api.agents.nodes.classify_node import classify_node

        state = _make_state(
            revision=999,
            evidence_preclassify_results=[],
            evidence_ocr_results=[],
        )
        partial = asyncio.run(classify_node(state))
        self.assertEqual(partial["revision"], 1000)

    def test_revision_increments_across_different_nodes(self):
        """多个节点都正确递增 revision（验证 helper 通用性）。"""
        from api.agents.nodes.classify_node import classify_node
        from api.agents.nodes.extract_node import extract_node
        from api.agents.nodes.review_node import review_node

        # classify
        state1 = _make_state(
            revision=10,
            evidence_preclassify_results=[],
            evidence_ocr_results=[],
        )
        partial1 = asyncio.run(classify_node(state1))
        self.assertEqual(partial1["revision"], 11)

        # extract
        state2 = _make_state(revision=42, evidence_ocr_results=[])
        partial2 = asyncio.run(extract_node(state2))
        self.assertEqual(partial2["revision"], 43)

        # review（特殊：Command.update）
        state3 = _make_state(revision=100, evidence_extract_results=[])
        cmd = asyncio.run(review_node(state3))
        self.assertEqual(cmd.update["revision"], 101)


# ============================================================================
# 辅助模块 node_result_builder 单元测试（确保 helper 行为正确）
# ============================================================================

class NodeResultBuilderHelperTest(SimpleTestCase):
    """node_result_builder 共享辅助模块行为测试。"""

    def test_convert_string_errors_to_dicts_returns_dict_list(self):
        """字符串错误列表应转换为 dict 列表（对齐 Task 0.1 BREAKING）。"""
        from api.agents.utils.node_result_builder import convert_string_errors_to_dicts

        errors = ["OCR 失败", "LLM 超时"]
        result = convert_string_errors_to_dicts(errors, stage="ocr")

        self.assertEqual(len(result), 2)
        for item in result:
            self.assertIsInstance(item, dict)
            self.assertIn("code", item)
            self.assertIn("message", item)
            self.assertIn("severity", item)
            self.assertIn("stage", item)
            self.assertEqual(item["stage"], "ocr")
            self.assertEqual(item["severity"], "warning")

    def test_convert_string_errors_filters_empty_strings(self):
        """空字符串错误应被过滤。"""
        from api.agents.utils.node_result_builder import convert_string_errors_to_dicts

        result = convert_string_errors_to_dicts(["", "实际错误", ""], stage="test")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["message"], "实际错误")

    def test_make_node_partial_update_increments_revision(self):
        """make_node_partial_update 应正确递增 revision。"""
        from api.agents.utils.node_result_builder import (
            build_node_result,
            make_node_partial_update,
        )
        from api.agents.schemas import QualityReport

        node_result = build_node_result(
            node_name="test_node",
            data={"foo": "bar"},
            quality=QualityReport(score=0.8, status="pass"),
            start_time=None,
        )
        state = {"revision": 7}
        partial = make_node_partial_update(
            node_name="test_node",
            stage="material_understanding",
            progress=0.15,
            state=state,
            node_result=node_result,
            legacy_fields={"my_legacy_field": "value"},
        )

        # revision 递增
        self.assertEqual(partial["revision"], 8)
        # 旧字段保留
        self.assertEqual(partial["my_legacy_field"], "value")
        # NodeResult 契约字段全部存在
        for field in REQUIRED_PARTIAL_FIELDS:
            self.assertIn(field, partial)
        # events 含 node.completed
        self.assertTrue(
            any(e.get("event_type") == "node.completed" for e in partial["events"])
        )

    def test_make_node_partial_update_defaults_revision_to_one_when_state_empty(self):
        """state 中无 revision 时，应默认 revision=0 + 1 = 1。"""
        from api.agents.utils.node_result_builder import (
            build_node_result,
            make_node_partial_update,
        )
        from api.agents.schemas import QualityReport

        node_result = build_node_result(
            node_name="test_node",
            data={},
            quality=QualityReport(score=0.5, status="warn"),
        )
        partial = make_node_partial_update(
            node_name="test_node",
            stage="fact_checking",
            progress=0.5,
            state={},  # 无 revision 键
            node_result=node_result,
            legacy_fields={},
        )
        self.assertEqual(partial["revision"], 1)


if __name__ == "__main__":
    unittest.main()
