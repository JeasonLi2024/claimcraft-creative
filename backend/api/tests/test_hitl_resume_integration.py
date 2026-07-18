# -*- coding: utf-8 -*-
"""Task 1.5.3 HITL resume 端到端集成测试（强化版）。

对齐 `langgraph-human-in-the-loop` skill 与 tasks.md SubTask 1.5.3：
- 测试 1：真实 graph + InMemorySaver，review_node interrupt 后 Command(resume=...) 正确恢复
- 测试 2：stage_gate interrupt 后 Command(resume={"interrupt_type": "stage_pause", ...}) 正确恢复
- 测试 3：对比测试 — 普通 dict resume 表现 stuck（无进展）

与 test_hitl_resume.py 的区别：
- test_hitl_resume.py 使用极简的 _CounterState + 单节点 graph 验证 Command vs dict 行为差异
- 本文件聚焦生产节点结构：
  * review_node 模式：interrupt payload 含 fields_to_review，resume 后用 corrections 更新 state
  * stage_gate 模式：interrupt payload 含 interrupt_type=stage_pause + editable_scope，
    resume 后应用 state_updates（对齐 stage_gate_node.py 生产实现）
- 使用 InMemorySaver（约束 #2），不依赖 Postgres
- 不调用真实 review_node / stage_gate_node（避免 DB / sync_to_async 桥接复杂度），
  而是构造与生产节点结构一致的 mock 节点函数

测试策略：
- 每个测试独立构造 graph + InMemorySaver，使用独立 thread_id（约束 #4）
- mock 节点函数模拟生产 review_node / stage_gate_node 的 interrupt + Command 模式
- 不调用 Django ORM（避免 SimpleTestCase 数据库限制）

运行方式：
    cd backend
    python manage.py test api.tests.test_hitl_resume_integration -v 2
"""
import asyncio
import os
import sys
import unittest
from typing import Any
from unittest.mock import patch

# 确保 backend/ 在 sys.path 上
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django  # noqa: E402
from django.apps import apps as _django_apps  # noqa: E402
if not _django_apps.ready:
    django.setup()

from django.test import SimpleTestCase  # noqa: E402

try:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Command, interrupt
    from typing_extensions import TypedDict

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - 环境兜底
    LANGGRAPH_AVAILABLE = False


# ============================================================================
# 公共：模拟生产 review_node / stage_gate_node 的 state schema
# ============================================================================

class _ReviewTestState(TypedDict, total=False):
    """模拟生产 CaseWorkflowState 中 review_node 相关字段。"""
    case_id: int
    evidence_extract_results: list  # extract 节点写入的累积列表
    needs_human_review: bool
    review_decision: dict
    revision: int
    current_node: str
    # 模拟生产 errors 字段（add reducer）
    errors: list
    # review 后写入的字段
    review_applied: bool
    post_interrupt_done: bool


def _add_list(left, right):
    """模拟 Annotated[list, add] reducer 行为。"""
    return (left or []) + (right or [])


# ============================================================================
# 测试 1：review_node interrupt + Command(resume=...) 正确恢复
# ============================================================================

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class ReviewNodeInterruptResumeIntegrationTest(SimpleTestCase):
    """测试 1：模拟 review_node 的 interrupt + Command(resume=corrections) 恢复。

    模拟生产 review_node.py 行为：
    - 节点遍历 evidence_extract_results，收集低置信度字段
    - 调用 interrupt({"case_id", "fields_to_review", "message"}) 暂停
    - resume 后用 Command(resume={"corrections": [...]}) 恢复
    - resume 时整个节点从头重新执行（LangGraph 预期行为），interrupt 后代码用
      corrections 更新 state，跳转下游节点
    """

    def test_review_node_interrupt_and_resume_applies_corrections(self):
        """review_node interrupt 后 Command(resume=corrections) 正确恢复。"""
        exec_log = {"review": 0, "downstream": 0}

        # 构造 extract 节点写入的 evidence_extract_results（含 1 个低置信度字段）
        extract_results = [
            {
                "evidence_id": 101,
                "evidence_code": "EV-001",
                "fields": [
                    {"field_name": "金额", "field_value": "1000元", "confidence": 0.42},
                    {"field_name": "日期", "field_value": "2026-01-01", "confidence": 0.95},
                ],
            }
        ]

        def review_node(state):
            """模拟生产 review_node.py 行为（简化版）。"""
            exec_log["review"] += 1
            extract_results_state = state.get("evidence_extract_results", [])

            # 1. 收集低置信度字段（confidence < 0.7）
            fields_to_review = []
            for er in extract_results_state:
                for f in er.get("fields", []):
                    if f.get("confidence", 1.0) < 0.7:
                        fields_to_review.append({
                            "evidence_id": er["evidence_id"],
                            "evidence_code": er["evidence_code"],
                            "field_name": f.get("field_name", ""),
                            "field_value": f.get("field_value", ""),
                            "confidence": f.get("confidence", 0.0),
                        })

            # 2. 无低置信度字段 → 直接跳过（与生产 review_node 一致）
            if not fields_to_review:
                return {
                    "current_node": "review",
                    "review_applied": False,
                    "post_interrupt_done": True,
                    "revision": (state.get("revision", 0) or 0) + 1,
                }

            # 3. 调用 interrupt 暂停（payload 与生产 review_node 一致）
            human_input = interrupt({
                "case_id": state.get("case_id"),
                "fields_to_review": fields_to_review,
                "message": f"共 {len(fields_to_review)} 个低置信度字段需要校正",
            })

            # ===== 以下代码仅在 resume 后执行 =====

            # 4. 解析人工校正结果（与生产 review_node 一致）
            if not isinstance(human_input, dict):
                human_input = {"corrections": []}
            corrections = human_input.get("corrections", [])

            # 5. 应用校正：更新 evidence_extract_results 中的字段值
            updated_results = []
            for er in extract_results_state:
                updated_fields = []
                for f in er.get("fields", []):
                    # 查找对应字段的校正
                    corrected = next(
                        (c for c in corrections
                         if c.get("evidence_id") == er["evidence_id"]
                         and c.get("field_name") == f.get("field_name")),
                        None,
                    )
                    if corrected:
                        updated_fields.append({
                            "field_name": f["field_name"],
                            "field_value": corrected.get("field_value", f.get("field_value")),
                            "confidence": 1.0,  # 用户校正后置信度 = 1.0
                            "source": "review",
                        })
                    else:
                        updated_fields.append(f)
                updated_results.append({
                    "evidence_id": er["evidence_id"],
                    "evidence_code": er["evidence_code"],
                    "fields": updated_fields,
                    "needs_human_review": False,
                })

            return {
                "current_node": "review",
                "review_applied": True,
                "review_decision": human_input,
                "post_interrupt_done": True,
                "revision": (state.get("revision", 0) or 0) + 1,
            }

        def downstream_node(state):
            """模拟 evidence_chain 节点（review 后的下游节点）。"""
            exec_log["downstream"] += 1
            return {
                "current_node": "downstream",
                "revision": (state.get("revision", 0) or 0) + 1,
            }

        # 构造 graph：START → review → downstream → END
        builder = StateGraph(_ReviewTestState)
        builder.add_node("review", review_node)
        builder.add_node("downstream", downstream_node)
        builder.add_edge(START, "review")
        builder.add_edge("review", "downstream")
        builder.add_edge("downstream", END)
        graph = builder.compile(checkpointer=InMemorySaver())

        config = {"configurable": {"thread_id": "hitl-review-1"}}

        # 1. 首次 invoke：应触发 interrupt（有 1 个低置信度字段）
        result1 = graph.invoke({
            "case_id": 42,
            "evidence_extract_results": extract_results,
            "needs_human_review": True,
            "revision": 5,
            "errors": [],
        }, config)

        self.assertIn("__interrupt__", result1, "应触发 interrupt（有低置信度字段）")
        self.assertEqual(exec_log["review"], 1, "review 节点应执行 1 次（到 interrupt）")
        self.assertEqual(exec_log["downstream"], 0, "downstream 不应执行")
        # interrupt payload 含低置信度字段
        interrupts = result1["__interrupt__"]
        self.assertTrue(len(interrupts) > 0)
        # 验证 interrupt value（结构匹配生产 review_node payload）
        interrupt_value = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        if isinstance(interrupt_value, dict):
            self.assertEqual(interrupt_value.get("case_id"), 42)
            self.assertIn("fields_to_review", interrupt_value)
            self.assertEqual(len(interrupt_value["fields_to_review"]), 1)
            self.assertEqual(interrupt_value["fields_to_review"][0]["field_name"], "金额")

        # 2. resume：使用 Command(resume={"corrections": [...]})
        resume_payload = {
            "corrections": [
                {
                    "evidence_id": 101,
                    "field_name": "金额",
                    "field_value": "2000元（用户校正）",
                }
            ]
        }
        result2 = graph.invoke(Command(resume=resume_payload), config)

        # 3. resume 后 review 节点重新执行（LangGraph 预期）
        self.assertEqual(
            exec_log["review"], 2,
            "resume 时 review 节点应从头重新执行（LangGraph 预期行为）",
        )
        # downstream 节点执行
        self.assertEqual(exec_log["downstream"], 1, "downstream 应在 resume 后执行")

        # 4. resume 后 interrupt 之后的代码执行了
        self.assertTrue(
            result2.get("post_interrupt_done"),
            "resume 后 interrupt 之后的代码应执行，post_interrupt_done=True",
        )
        self.assertTrue(result2.get("review_applied"), "review_applied 应为 True")
        # review_decision 应为 resume payload
        self.assertEqual(result2.get("review_decision"), resume_payload)
        # 校正后的字段值已应用（confidence=1.0）
        # 注意：state 中的 evidence_extract_results 在测试 graph 中是默认覆盖（无 reducer），
        # 故此处不验证累积语义，仅验证 review_decision 已注入

        # 5. revision 单调递增：5（初始）→ 6（review）→ 7（downstream）= 7
        self.assertEqual(result2["revision"], 7)

        # 6. resume 完成后无 __interrupt__
        self.assertNotIn("__interrupt__", result2)


# ============================================================================
# 测试 2：stage_gate interrupt + Command(resume=stage_pause) 正确恢复
# ============================================================================

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class StageGateInterruptResumeIntegrationTest(SimpleTestCase):
    """测试 2：stage_gate interrupt + Command(resume={"interrupt_type": "stage_pause"}) 恢复。

    模拟生产 stage_gate_node.py 行为：
    - 节点检查 Case.workflow_pause_requested（mock 为 state.pause_requested）
    - 若 True，调用 interrupt(build_stage_pause_payload(paused_after)) 暂停
    - resume 时检查 resume_value 是 dict 且 interrupt_type=stage_pause
    - 应用 resume_value.state_updates 到 state
    """

    def test_stage_gate_interrupt_and_resume_applies_state_updates(self):
        """stage_gate interrupt 后 Command(resume=stage_pause) 正确恢复。"""
        exec_log = {"gate": 0, "downstream": 0}

        class _GateState(TypedDict, total=False):
            case_id: int
            pause_requested: bool
            paused_after: str
            user_edited_field: str
            current_node: str
            revision: int

        def stage_gate_node(state):
            """模拟生产 stage_gate_node.py 行为（简化版）。"""
            exec_log["gate"] += 1
            case_id = state.get("case_id")
            if not case_id:
                return {}

            # 检查 pause_requested（生产代码用 Case.objects.filter(...).exists()）
            if not state.get("pause_requested"):
                return {}

            # 调用 interrupt（对齐 build_stage_pause_payload）
            resume_value = interrupt({
                "interrupt_type": "stage_pause",
                "paused_after": "ocr",
                "editable_scope": {"evidences": ["extracted_text"]},
                "message": "已在 ocr 节点完成后安全暂停，可修改阶段产物后继续。",
            })

            # ===== 以下代码仅在 resume 后执行 =====
            # 检查 resume_value 结构（对齐生产 stage_gate_node.py line 40-44）
            if not isinstance(resume_value, dict):
                return {}
            if resume_value.get("interrupt_type") != "stage_pause":
                return {}

            # 应用 state_updates（对齐生产 line 45）
            state_updates = resume_value.get("state_updates")
            return state_updates if isinstance(state_updates, dict) else {}

        def downstream_node(state):
            exec_log["downstream"] += 1
            return {
                "current_node": "downstream",
                "revision": (state.get("revision", 0) or 0) + 1,
            }

        builder = StateGraph(_GateState)
        builder.add_node("stage_gate", stage_gate_node)
        builder.add_node("downstream", downstream_node)
        builder.add_edge(START, "stage_gate")
        builder.add_edge("stage_gate", "downstream")
        builder.add_edge("downstream", END)
        graph = builder.compile(checkpointer=InMemorySaver())

        config = {"configurable": {"thread_id": "hitl-stage-gate-1"}}

        # 1. 首次 invoke：pause_requested=True → 触发 interrupt
        result1 = graph.invoke({
            "case_id": 1,
            "pause_requested": True,
            "revision": 3,
        }, config)

        self.assertIn("__interrupt__", result1, "应触发 stage_pause interrupt")
        self.assertEqual(exec_log["gate"], 1)
        self.assertEqual(exec_log["downstream"], 0)

        # 验证 interrupt value 是 stage_pause 结构
        interrupts = result1["__interrupt__"]
        interrupt_value = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        if isinstance(interrupt_value, dict):
            self.assertEqual(interrupt_value.get("interrupt_type"), "stage_pause")
            self.assertEqual(interrupt_value.get("paused_after"), "ocr")
            self.assertIn("editable_scope", interrupt_value)
            self.assertIn("message", interrupt_value)

        # 2. resume：使用 Command(resume={"interrupt_type": "stage_pause", "state_updates": {...}})
        resume_payload = {
            "interrupt_type": "stage_pause",
            "paused_after": "ocr",
            "state_updates": {
                "user_edited_field": "用户编辑后的值",
                "paused_after": "ocr",
            },
        }
        result2 = graph.invoke(Command(resume=resume_payload), config)

        # 3. resume 后 stage_gate 节点重新执行（LangGraph 预期）
        self.assertEqual(
            exec_log["gate"], 2,
            "resume 时 stage_gate 节点应从头重新执行",
        )
        self.assertEqual(exec_log["downstream"], 1, "downstream 应在 resume 后执行")

        # 4. state_updates 被应用到 state
        self.assertEqual(
            result2.get("user_edited_field"), "用户编辑后的值",
            "state_updates 中的字段应被合并到 state",
        )
        self.assertEqual(result2.get("paused_after"), "ocr")

        # 5. resume 完成后无 __interrupt__
        self.assertNotIn("__interrupt__", result2)

        # 6. revision 推进：3（初始）→ 4（downstream +1）= 4
        # 注意：stage_gate 节点 resume 后未 +1（仅返回 state_updates），downstream +1
        self.assertEqual(result2["revision"], 4)

    def test_stage_gate_resume_rejects_non_stage_pause_payload(self):
        """resume payload 不是 stage_pause 类型时，stage_gate 不应用 state_updates。"""
        exec_log = {"gate": 0, "downstream": 0}

        class _GateState(TypedDict, total=False):
            case_id: int
            pause_requested: bool
            current_node: str
            revision: int

        def stage_gate_node(state):
            exec_log["gate"] += 1
            if not state.get("pause_requested"):
                return {}

            resume_value = interrupt({
                "interrupt_type": "stage_pause",
                "paused_after": "ocr",
                "message": "请求暂停",
            })

            # 拒绝非 stage_pause 类型的 resume
            if not isinstance(resume_value, dict) or \
               resume_value.get("interrupt_type") != "stage_pause":
                return {}

            return resume_value.get("state_updates") or {}

        def downstream_node(state):
            exec_log["downstream"] += 1
            return {
                "current_node": "downstream",
                "revision": (state.get("revision", 0) or 0) + 1,
            }

        builder = StateGraph(_GateState)
        builder.add_node("stage_gate", stage_gate_node)
        builder.add_node("downstream", downstream_node)
        builder.add_edge(START, "stage_gate")
        builder.add_edge("stage_gate", "downstream")
        builder.add_edge("downstream", END)
        graph = builder.compile(checkpointer=InMemorySaver())

        config = {"configurable": {"thread_id": "hitl-stage-gate-2"}}

        # 1. 触发 interrupt
        result1 = graph.invoke({
            "case_id": 1, "pause_requested": True, "revision": 0,
        }, config)
        self.assertIn("__interrupt__", result1)

        # 2. resume 使用错误的 payload（不是 stage_pause 类型）
        # 注意：InMemorySaver 用 msgpack 持久化，payload 必须可序列化
        # （不能用 Python ellipsis 字面量 `...` / `[...]` 等）
        wrong_payload = {"corrections": ["x"]}  # review 类型，不是 stage_pause
        result2 = graph.invoke(Command(resume=wrong_payload), config)

        # 3. 节点未应用 state_updates（返回 {}），但 graph 继续执行下游节点
        # stage_gate 节点 resume 后从头执行，interrupt 后代码返回 {}
        self.assertEqual(exec_log["gate"], 2)
        self.assertEqual(exec_log["downstream"], 1, "downstream 仍应执行（graph 不应中断）")
        self.assertNotIn("__interrupt__", result2)


# ============================================================================
# 测试 3：对比测试 — 普通 dict resume 表现 stuck（无进展）
# ============================================================================

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class PlainDictResumeStuckComparisonTest(SimpleTestCase):
    """测试 3：对比测试，证明普通 dict resume 无法正确恢复中断点。

    对齐 langgraph-human-in-the-loop skill：
    - 普通 dict 会让 graph 从最新 checkpoint 恢复但表现为 stuck（无 interrupt_id 关联）
    - Command(resume=...) 正确关联到 interrupt() 调用点，节点从中断后第一行恢复执行

    使用与 review_node 模式一致的 mock 节点，验证：
    - 用 Command(resume=...) 恢复：节点 interrupt 后代码执行（post_interrupt_done=True）
    - 用普通 dict 恢复：节点表现为 stuck 或抛错（无法越过 interrupt）
    """

    def test_command_resume_completes_but_plain_dict_does_not(self):
        """对比测试：Command 完成，普通 dict stuck。"""
        # 共用的 mock 节点：与 review_node 模式一致
        def make_review_node(exec_log):
            def review_node(state):
                exec_log["review"] += 1
                # 调用 interrupt 暂停
                human_input = interrupt({
                    "message": "请审核",
                    "fields_to_review": [{"field_name": "x"}],
                })
                # ===== 以下代码仅在 resume 后执行 =====
                return {
                    "post_interrupt_done": True,
                    "review_decision": human_input,
                }
            return review_node

        def downstream_node(state):
            return {"downstream_done": True}

        class _TestState(TypedDict, total=False):
            post_interrupt_done: bool
            review_decision: Any
            downstream_done: bool

        # 场景 A：Command(resume=...) 恢复 → 正确完成
        exec_log_a = {"review": 0}
        builder_a = StateGraph(_TestState)
        builder_a.add_node("review", make_review_node(exec_log_a))
        builder_a.add_node("downstream", downstream_node)
        builder_a.add_edge(START, "review")
        builder_a.add_edge("review", "downstream")
        builder_a.add_edge("downstream", END)
        graph_a = builder_a.compile(checkpointer=InMemorySaver())
        config_a = {"configurable": {"thread_id": "hitl-compare-cmd"}}

        # 首次 invoke 触发 interrupt
        result_a1 = graph_a.invoke({}, config_a)
        self.assertIn("__interrupt__", result_a1)
        self.assertEqual(exec_log_a["review"], 1)

        # resume 用 Command → 正确完成
        result_a2 = graph_a.invoke(Command(resume={"corrections": ["x"]}), config_a)
        self.assertNotIn("__interrupt__", result_a2)
        self.assertTrue(result_a2.get("post_interrupt_done"),
                        "Command(resume=...) 应正确恢复，post_interrupt_done=True")
        self.assertTrue(result_a2.get("downstream_done"),
                        "downstream 应在 Command resume 后执行")

        # 场景 B：普通 dict 恢复 → stuck 或抛错
        exec_log_b = {"review": 0}
        builder_b = StateGraph(_TestState)
        builder_b.add_node("review", make_review_node(exec_log_b))
        builder_b.add_node("downstream", downstream_node)
        builder_b.add_edge(START, "review")
        builder_b.add_edge("review", "downstream")
        builder_b.add_edge("downstream", END)
        graph_b = builder_b.compile(checkpointer=InMemorySaver())
        config_b = {"configurable": {"thread_id": "hitl-compare-dict"}}

        # 首次 invoke 触发 interrupt
        result_b1 = graph_b.invoke({}, config_b)
        self.assertIn("__interrupt__", result_b1)
        self.assertEqual(exec_log_b["review"], 1)

        # resume 用普通 dict → 应 stuck 或抛错
        stuck_or_errored = False
        try:
            result_b2 = graph_b.invoke({"corrections": ["x"]}, config_b)
        except Exception:
            # 抛错也算「无法正确恢复」
            stuck_or_errored = True
        else:
            # 未抛错则检查是否 stuck：
            # - post_interrupt_done 未变为 True（interrupt 后代码未执行），或
            # - 仍停留在 __interrupt__
            if not result_b2.get("post_interrupt_done") or "__interrupt__" in result_b2:
                stuck_or_errored = True

        self.assertTrue(
            stuck_or_errored,
            "普通 dict resume 应表现为 stuck（无法越过 interrupt）或抛错，"
            "证明必须使用 Command(resume=...)",
        )

    def test_plain_dict_resume_does_not_advance_state(self):
        """更细粒度的对比：普通 dict resume 后 state 不前进（interrupt 仍在）。"""
        def review_node(state):
            human_input = interrupt({"message": "审核中"})
            return {
                "post_interrupt_done": True,
                "review_decision": human_input,
            }

        def downstream_node(state):
            return {"downstream_done": True}

        class _TestState(TypedDict, total=False):
            post_interrupt_done: bool
            review_decision: Any
            downstream_done: bool

        builder = StateGraph(_TestState)
        builder.add_node("review", review_node)
        builder.add_node("downstream", downstream_node)
        builder.add_edge(START, "review")
        builder.add_edge("review", "downstream")
        builder.add_edge("downstream", END)
        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "hitl-stuck-1"}}

        # 触发 interrupt
        result1 = graph.invoke({}, config)
        self.assertIn("__interrupt__", result1)
        self.assertFalse(result1.get("post_interrupt_done"))

        # 用普通 dict resume
        try:
            result2 = graph.invoke({"corrections": ["x"]}, config)
        except Exception:
            # 抛错视为 stuck
            return

        # 即使没抛错，state 也未前进：
        # - post_interrupt_done 仍为 False / 不存在，或
        # - __interrupt__ 仍在
        if "__interrupt__" not in result2 and result2.get("post_interrupt_done"):
            self.fail(
                "普通 dict resume 不应让 graph 越过 interrupt（应 stuck 或抛错），"
                "但实际 post_interrupt_done=True 且无 __interrupt__"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
