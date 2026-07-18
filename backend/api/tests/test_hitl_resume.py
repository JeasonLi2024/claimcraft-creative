# -*- coding: utf-8 -*-
"""Task 0.2.5 集成测试：验证 HITL resume 使用 Command(resume=...) 正确恢复中断点。

对齐 `langgraph-human-in-the-loop` skill：
- interrupt(value) 暂停图执行，值出现在 result["__interrupt__"]
- Command(resume=value) 恢复，resume 值成为 interrupt() 的返回值
- 普通 dict 作为 invoke 输入会重启 graph 而非恢复中断点（错误模式）

测试策略：
- 测试 1 & 2 使用 InMemorySaver（无需 Postgres），构建含 interrupt() 的真实 graph，
  验证 Command(resume=...) 与普通 dict 的行为差异。
- 测试 3 使用 mock 验证 WorkflowRunner.run_and_persist 在 resume 非空时
  确实以 Command 实例（而非普通 dict）调用 workflow.astream_events。
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

try:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Command, interrupt
    from typing_extensions import TypedDict

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - 环境兜底
    LANGGRAPH_AVAILABLE = False


# ---------------------------------------------------------------------------
# 测试 1 & 2 共用的 graph 构造
# ---------------------------------------------------------------------------

class _CounterState(TypedDict, total=False):
    """简单 state：记录节点调用次数与 post-interrupt 完成标志。"""
    call_count: int
    done: bool
    approved: bool


def _make_interrupt_graph():
    """构建含 interrupt() 的简单 graph，用于测试 resume 行为。

    节点行为：
    - 进入节点时 call_count += 1（记录节点执行次数，验证 resume 时节点从头重新执行）
    - 调用 interrupt() 暂停
    - resume 后设置 done=True / approved=<resume 值>（验证 interrupt 后代码执行了）
    """
    # 用可变容器记录节点执行次数（避免依赖 state 持久化语义）
    exec_log = {"count": 0}

    def node(state: _CounterState) -> dict:
        # interrupt 前代码：resume 时会重新执行（LangGraph 预期行为）
        exec_log["count"] += 1
        current = state.get("call_count", 0)
        # 暂停并等待人工输入
        approved = interrupt({
            "exec_count": exec_log["count"],
            "message": "请审核是否批准",
        })
        # ===== 以下代码仅在 resume 后执行 =====
        return {
            "call_count": current + 1,
            "done": True,
            "approved": bool(approved),
        }

    graph = (
        StateGraph(_CounterState)
        .add_node("review", node)
        .add_edge(START, "review")
        .add_edge("review", END)
        .compile(checkpointer=InMemorySaver())
    )
    return graph, exec_log


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class CommandResumeIntegrationTests(unittest.TestCase):
    """测试 1 & 2：真实 LangGraph graph 的 resume 行为。"""

    def test_command_resume_restores_from_interrupt(self):
        """测试 1：Command(resume=...) 正确恢复中断点。

        断言：
        - 首次 invoke 后 result["__interrupt__"] 非空
        - resume 后节点从头重新执行（exec_count 增加，验证 LangGraph 预期行为）
        - interrupt 后的代码也执行了（done=True，approved=True）
        """
        graph, exec_log = _make_interrupt_graph()
        config = {"configurable": {"thread_id": "resume-test-1"}}

        # 首次启动：应触发 interrupt 暂停
        result = graph.invoke({"call_count": 0, "done": False, "approved": False}, config)
        self.assertIn("__interrupt__", result, "首次 invoke 应产生 __interrupt__")
        self.assertTrue(result["__interrupt__"], "__interrupt__ 不应为空")
        self.assertEqual(exec_log["count"], 1, "首次 invoke 节点应执行 1 次")

        # resume：使用 Command(resume=...)（正确模式）
        result = graph.invoke(Command(resume=True), config)

        # 节点从头重新执行（LangGraph 预期行为）：exec_count 应增加
        self.assertEqual(exec_log["count"], 2, "resume 时节点应从头重新执行（exec_count 增加）")
        # interrupt 后的代码执行了
        self.assertTrue(result.get("done"), "resume 后 interrupt 之后的代码应执行，done=True")
        self.assertTrue(result.get("approved"), "approved 应为 resume 传入的值 True")
        # graph 已完成，不再有 __interrupt__
        self.assertNotIn("__interrupt__", result, "resume 完成后不应再有 __interrupt__")

    def test_plain_dict_resume_is_stuck_or_errors(self):
        """测试 2：普通 dict resume（错误模式）无法正确恢复中断点。

        对比测试，证明 Command(resume=...) 的必要性。
        断言：用普通 dict resume 后，graph 要么抛错，要么表现为无法越过 interrupt
        （done 仍为 False / 仍停留在 __interrupt__），即 stuck。
        """
        graph, exec_log = _make_interrupt_graph()
        config = {"configurable": {"thread_id": "resume-test-2"}}

        # 首次启动：触发 interrupt
        graph.invoke({"call_count": 0, "done": False, "approved": False}, config)
        self.assertEqual(exec_log["count"], 1)

        # 错误模式：用普通 dict 而非 Command(resume=...) 恢复
        # 根据 skill：普通 dict 会让 graph 从最新 checkpoint 恢复但表现为 stuck
        # （无 interrupt_id 关联），或被当作新输入重启。
        stuck_or_errored = False
        try:
            result = graph.invoke({"approved": True}, config)
        except Exception:
            # 抛错也算「无法正确恢复」
            stuck_or_errored = True
        else:
            # 未抛错则检查是否 stuck：done 未变为 True，或仍停留在 __interrupt__
            if not result.get("done") or "__interrupt__" in result:
                stuck_or_errored = True

        self.assertTrue(
            stuck_or_errored,
            "普通 dict resume 应表现为 stuck（无法越过 interrupt）或抛错，"
            "证明必须使用 Command(resume=...)",
        )


# ---------------------------------------------------------------------------
# 测试 3：WorkflowRunner.run_and_persist 使用 Command(resume=...)
# ---------------------------------------------------------------------------

class WorkflowRunnerResumeUsesCommandTests(SimpleTestCase):
    """测试 3：验证 WorkflowRunner.run_and_persist 在 resume 非空时使用 Command 实例。

    通过 mock workflow.astream_events，断言第一个位置参数是 Command 实例而非 dict。
    不依赖真实 Postgres / DB。
    """

    def test_run_and_persist_uses_command_when_resume_provided(self):
        """resume 非空时，astream_events 第一个参数应为 Command 实例。"""
        from api.agents import workflow_runner as wr_module

        # 构造 mock workflow：astream_events 返回空异步迭代器，
        # aget_state 返回无 interrupt + next=None 的 snapshot（走完成路径）
        mock_workflow = MagicMock()
        mock_workflow.astream_events = MagicMock(return_value=_empty_async_iter())
        mock_snapshot = MagicMock()
        mock_snapshot.interrupts = None
        mock_snapshot.tasks = []
        mock_snapshot.next = None  # 无挂起节点 → 走 complete_processing 路径
        mock_workflow.aget_state = AsyncMock(return_value=mock_snapshot)

        # mock EventDepot / NotifyEmitter / lifecycle 服务
        mock_depot = MagicMock()
        mock_depot.persist = AsyncMock(return_value="eid-1")
        mock_emitter = MagicMock()
        mock_emitter.notify = AsyncMock(return_value=None)

        # complete_processing 返回的对象需含 case.workflow_status='succeeded'
        # 注意：lifecycle 服务是同步函数，run_and_persist 用 sync_to_async 包装，
        # 故此处用同步 MagicMock（非 AsyncMock），否则 sync_to_async 会抛
        # "can only be applied to sync functions"。
        mock_completion = MagicMock()
        mock_completion.case.workflow_status = "succeeded"

        with patch.object(wr_module, "build_case_workflow", return_value=mock_workflow), \
             patch.object(wr_module, "EventDepot", return_value=mock_depot), \
             patch.object(wr_module, "NotifyEmitter", return_value=mock_emitter), \
             patch.object(wr_module, "complete_processing",
                          new=MagicMock(return_value=mock_completion)), \
             patch.object(wr_module, "mark_paused", new=MagicMock()), \
             patch.object(wr_module, "mark_waiting_review", new=MagicMock()), \
             patch.object(wr_module, "fail_processing", new=MagicMock()):
            runner = wr_module.WorkflowRunner()
            resume_payload = {"corrections": [{"evidence_id": 1, "field_name": "x", "field_value": "y"}]}

            asyncio.run(runner.run_and_persist(
                case_id=1,
                thread_id="thread-cmd-test",
                resume=resume_payload,
            ))

        # 断言 astream_events 被调用，且第一个位置参数是 Command 实例（非 dict）
        mock_workflow.astream_events.assert_called_once()
        call_args = mock_workflow.astream_events.call_args
        first_arg = call_args.args[0]
        self.assertIsInstance(
            first_arg, Command,
            f"resume 时应传入 Command(resume=...) 而非普通 dict，实际类型: {type(first_arg)}"
        )
        # Command 的 resume 属性应等于传入的 resume_payload
        # Command 对象通过 .resume 访问 resume 值
        resume_value = getattr(first_arg, "resume", None)
        self.assertEqual(
            resume_value, resume_payload,
            "Command.resume 应等于传入的 resume_payload",
        )

    def test_run_and_persist_uses_plain_state_when_no_resume(self):
        """resume 为空（首次启动）时，astream_events 第一个参数应为普通 dict（initial_state）。"""
        from api.agents import workflow_runner as wr_module

        mock_workflow = MagicMock()
        mock_workflow.astream_events = MagicMock(return_value=_empty_async_iter())
        mock_snapshot = MagicMock()
        mock_snapshot.interrupts = None
        mock_snapshot.tasks = []
        mock_snapshot.next = None
        mock_workflow.aget_state = AsyncMock(return_value=mock_snapshot)

        mock_depot = MagicMock()
        mock_depot.persist = AsyncMock(return_value="eid-1")
        mock_emitter = MagicMock()
        mock_emitter.notify = AsyncMock(return_value=None)

        mock_completion = MagicMock()
        mock_completion.case.workflow_status = "succeeded"

        initial_state = {"case_id": 1, "evidence_ids": []}

        with patch.object(wr_module, "build_case_workflow", return_value=mock_workflow), \
             patch.object(wr_module, "EventDepot", return_value=mock_depot), \
             patch.object(wr_module, "NotifyEmitter", return_value=mock_emitter), \
             patch.object(wr_module, "complete_processing",
                          new=MagicMock(return_value=mock_completion)), \
             patch.object(wr_module, "mark_paused", new=MagicMock()), \
             patch.object(wr_module, "mark_waiting_review", new=MagicMock()), \
             patch.object(wr_module, "fail_processing", new=MagicMock()):
            runner = wr_module.WorkflowRunner()
            asyncio.run(runner.run_and_persist(
                case_id=1,
                thread_id="thread-noinit-test",
                initial_state=initial_state,
            ))

        mock_workflow.astream_events.assert_called_once()
        first_arg = mock_workflow.astream_events.call_args.args[0]
        self.assertNotIsInstance(
            first_arg, Command,
            "首次启动（无 resume）应传入普通 dict（initial_state），不应是 Command"
        )
        # Task 1.1.3：workflow_runner 在首次启动时会注入版本字段（workflow_version /
        # state_schema_version / policy_version / prompt_bundle_version）和 workflow_run_id
        # （Task 3.1），因此 first_arg 不再等于原始 initial_state，但应包含其所有键值
        for key, value in initial_state.items():
            self.assertIn(
                key, first_arg,
                f"first_arg 应包含原始 initial_state 的 '{key}' 字段"
            )
            self.assertEqual(
                first_arg[key], value,
                f"first_arg['{key}'] 应等于 initial_state['{key}']"
            )
        # 验证版本字段已注入
        for version_key in (
            "workflow_version",
            "state_schema_version",
            "policy_version",
            "prompt_bundle_version",
        ):
            self.assertIn(
                version_key, first_arg,
                f"Task 1.1.3：first_arg 应注入版本字段 '{version_key}'"
            )


async def _empty_async_iter():
    """空异步迭代器：yield 0 个事件后结束。"""
    return
    yield  # pragma: no cover - 使函数成为 async generator


if __name__ == "__main__":
    unittest.main()
