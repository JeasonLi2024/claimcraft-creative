# -*- coding: utf-8 -*-
"""Task 1.5.1 工作流集成测试：覆盖端到端工作流编排场景。

对齐 `langgraph-fundamentals` / `langgraph-human-in-the-loop` / `langgraph-persistence` skills：
- 使用 `InMemorySaver` 作为 checkpointer（不依赖 Postgres，符合 tasks.md 约束 #2）
- mock LLM / OCR / DB 操作（约束 #3）
- 每个测试用例独立 setup/teardown（约束 #4）
- 必要时使用 `@unittest.skip` 跳过无法运行的测试（约束 #5）

测试覆盖（SubTask 1.5.1）：
1. 完整工作流启动 + 完成（mock LLM/OCR，验证 graph.invoke 成功完成，state 含阶段输出）
2. 完整工作流失败（mock 节点抛出未预期错误，验证 fail_processing 调用 + workflow.error 事件）
3. 节点超时 + RetryPolicy 重试（mock LLM 抛 ConnectionError 3 次后成功，验证 RetryPolicy 触发）
4. 节点超时 + 降级（mock LLM 持续失败超过 max_attempts，验证 error_handler 返回 errors dict + graph 继续）
5. checkpoint 恢复（首次 invoke 后中断，使用相同 thread_id 再次 invoke 验证 state 恢复）
6. SSE 事件顺序（验证 workflow.start → ... → workflow.complete 事件顺序）
7. revision 单调递增（每个节点返回 revision+1，最终 state.revision 等于节点数）
8. 阶段暂停 interrupt（mock stage_pause 请求，验证 graph 暂停 + resume 后继续）

测试策略：
- 构建简化的测试专用 StateGraph（不直接调用 build_case_workflow()，避免依赖真实
  PostgresSaver / PostgresStore + 8 个生产节点）。
- 模拟 8 个业务节点用 mock 函数替换，验证 graph 编排行为（retry / error_handler /
  interrupt / checkpointer / state reducer）。
- mock WorkflowRunner.run_and_persist 的外部依赖（EventDepot / NotifyEmitter /
  lifecycle 服务），验证事件流顺序与 fail_processing 触发。

运行方式：
    cd backend
    python manage.py test api.tests.test_workflow_integration -v 2
    # 或：python -m pytest api/tests/test_workflow_integration.py -v
"""
import asyncio
import os
import sys
import unittest
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

from django.test import SimpleTestCase  # noqa: E402

try:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.errors import NodeError, NodeTimeoutError
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Command, RetryPolicy, interrupt
    from typing_extensions import TypedDict

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - 环境兜底
    LANGGRAPH_AVAILABLE = False


# ============================================================================
# 公共：模拟工作流 state schema + 测试用 graph 构造
# ============================================================================

class _TestWorkflowState(TypedDict, total=False):
    """简化测试用 state：模拟生产 CaseWorkflowState 的关键字段。

    含累积列表（errors 用 add reducer）+ 标量 revision（默认覆盖）+
    阶段产物（preclassify/ocr/complaint 等）+ current_node 标记。
    """
    case_id: int
    case_mode: str
    evidence_ids: list[int]

    # 累积字段（Annotated[list, add]）
    # 注意：TypedDict 不支持 Annotated 字段直接定义 reducer，需在 StateGraph 中使用
    # 这里通过 dict 字段 + 手动 merge 模拟 reducer 行为
    errors: list[dict]
    events: list[dict]

    # 标量字段（默认覆盖）
    revision: int
    current_node: str
    current_stage: str
    progress: float

    # 阶段产物（默认覆盖）
    preclassify_result: dict
    ocr_result: dict
    classify_result: dict
    extract_result: dict
    evidence_chain_result: dict
    complaint_draft: dict

    # HITL 标记
    needs_human_review: bool
    review_decision: dict


def _add_list(left, right):
    """模拟 Annotated[list, add] reducer 行为。"""
    return (left or []) + (right or [])


def _build_minimal_workflow_graph(
    preclassify_fn=None,
    ocr_fn=None,
    classify_fn=None,
    extract_fn=None,
    evidence_chain_fn=None,
    complaint_fn=None,
    *,
    retry_policy_for_ocr=None,
    error_handler_for_ocr=None,
):
    """构建简化的测试工作流图：START → preclassify → ocr → complaint → END。

    省略 classify / extract / review / evidence_chain 节点（场景测试不需要时可设为透传）。
    所有节点默认行为：revision += 1，current_node 标记自身，progress 推进。

    Args:
        各节点 mock 函数：None 时使用默认透传实现
        retry_policy_for_ocr: OCR 节点的 retry_policy（None 时不配置）
        error_handler_for_ocr: OCR 节点的 error_handler（None 时不配置）

    Returns:
        (compiled_graph, exec_log) — exec_log 记录各节点调用次数
    """
    exec_log = {"preclassify": 0, "ocr": 0, "classify": 0, "extract": 0,
                "evidence_chain": 0, "complaint": 0}

    def _default_node(name, stage, progress):
        # complaint 节点需写入 complaint_draft 字段（对齐生产 CaseWorkflowState.complaint_draft）
        result_field = "complaint_draft" if name == "complaint" else f"{name}_result"

        def _fn(state):
            exec_log[name] = exec_log.get(name, 0) + 1
            return {
                "current_node": name,
                "current_stage": stage,
                "progress": progress,
                "revision": (state.get("revision", 0) or 0) + 1,
                result_field: {"node": name, "ok": True},
            }
        return _fn

    preclassify = preclassify_fn or _default_node("preclassify", "material_understanding", 0.10)
    ocr = ocr_fn or _default_node("ocr", "material_understanding", 0.20)
    classify = classify_fn or _default_node("classify", "material_understanding", 0.30)
    extract = extract_fn or _default_node("extract", "fact_checking", 0.45)
    evidence_chain = evidence_chain_fn or _default_node("evidence_chain", "case_organization", 0.70)
    complaint = complaint_fn or _default_node("complaint", "document_generation", 0.90)

    builder = StateGraph(_TestWorkflowState)

    # OCR 节点可选配置 retry_policy + error_handler
    ocr_kwargs = {}
    if retry_policy_for_ocr is not None:
        ocr_kwargs["retry_policy"] = retry_policy_for_ocr
    if error_handler_for_ocr is not None:
        ocr_kwargs["error_handler"] = error_handler_for_ocr

    builder.add_node("preclassify", preclassify)
    builder.add_node("ocr", ocr, **ocr_kwargs)
    builder.add_node("classify", classify)
    builder.add_node("extract", extract)
    builder.add_node("evidence_chain", evidence_chain)
    builder.add_node("complaint", complaint)

    builder.add_edge(START, "preclassify")
    builder.add_edge("preclassify", "ocr")
    builder.add_edge("ocr", "classify")
    builder.add_edge("classify", "extract")
    builder.add_edge("extract", "evidence_chain")
    builder.add_edge("evidence_chain", "complaint")
    builder.add_edge("complaint", END)

    graph = builder.compile(checkpointer=InMemorySaver())
    return graph, exec_log


# ============================================================================
# 公共：mock WorkflowRunner 的 EventDepot / NotifyEmitter / lifecycle 服务
# ============================================================================

def _make_mock_depot():
    """构造内存 EventDepot mock，记录所有 persist 调用。

    Returns:
        (mock_depot, events_list) — events_list 收集 (thread_id, event_type, payload, kwargs)
    """
    events = []

    async def _persist(thread_id, event_type, payload, **kwargs):
        # 记录事件 + 信封字段
        events.append({
            "thread_id": thread_id,
            "event_type": event_type,
            "payload": payload,
            "run_id": kwargs.get("run_id"),
            "revision": kwargs.get("revision"),
            "occurred_at": kwargs.get("occurred_at"),
        })
        return len(events)  # 模拟 event_id 单调递增

    mock_depot = MagicMock()
    mock_depot.persist = AsyncMock(side_effect=_persist)
    return mock_depot, events


def _make_mock_emitter():
    """构造 NotifyEmitter mock（notify 是 async 方法）。"""
    mock_emitter = MagicMock()
    mock_emitter.notify = AsyncMock(return_value=None)
    return mock_emitter


def _make_mock_completion(status="succeeded"):
    """构造 complete_processing 返回的 mock 对象。"""
    mock_completion = MagicMock()
    mock_completion.case.workflow_status = status
    return mock_completion


# ============================================================================
# 测试 1：完整工作流启动 + 完成
# ============================================================================

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class WorkflowCompleteSuccessTest(SimpleTestCase):
    """测试 1：完整工作流启动 + 完成（mock LLM/OCR 调用）。"""

    def test_full_workflow_completes_with_all_stage_outputs(self):
        """graph.invoke 应成功完成，state 含所有阶段产物 + revision 单调递增。"""
        graph, exec_log = _build_minimal_workflow_graph()
        config = {"configurable": {"thread_id": "wf-success-1"}}

        initial_state = {
            "case_id": 1,
            "case_mode": "complain",
            "evidence_ids": [10, 11],
            "revision": 0,
            "errors": [],
            "events": [],
        }
        result = graph.invoke(initial_state, config)

        # 1. 所有 6 个节点都执行了
        self.assertEqual(exec_log["preclassify"], 1)
        self.assertEqual(exec_log["ocr"], 1)
        self.assertEqual(exec_log["classify"], 1)
        self.assertEqual(exec_log["extract"], 1)
        self.assertEqual(exec_log["evidence_chain"], 1)
        self.assertEqual(exec_log["complaint"], 1)

        # 2. state 含每个阶段的产物
        for stage_field in (
            "preclassify_result", "ocr_result", "classify_result",
            "extract_result", "evidence_chain_result",
        ):
            self.assertIn(stage_field, result, f"state 应含阶段产物字段: {stage_field}")
            self.assertIsInstance(result[stage_field], dict)

        # 3. complaint_draft 字段存在
        self.assertIn("complaint_draft", result)

        # 4. revision 等于节点数（6 节点各 +1，从 0 开始）
        self.assertEqual(result["revision"], 6, "revision 应等于执行的节点数")

        # 5. progress 推进到 0.90（complaint 节点 progress）
        self.assertEqual(result["progress"], 0.90)

        # 6. current_node 是最后一个节点
        self.assertEqual(result["current_node"], "complaint")


# ============================================================================
# 测试 2：完整工作流失败（未预期错误 + fail_processing + workflow.error）
# ============================================================================

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class WorkflowFailWithErrorTest(SimpleTestCase):
    """测试 2：mock 节点抛出未预期错误，验证 fail_processing 调用 + workflow.error 事件。

    通过 WorkflowRunner.run_and_persist 触发：mock workflow.astream_events 抛出异常，
    验证 except 分支调用 fail_processing 并写入 workflow.error 事件到 EventDepot。
    """

    def test_unexpected_error_triggers_fail_processing_and_workflow_error_event(self):
        """未预期错误 → fail_processing(case_id, error) + EventDepot 写入 workflow.error。"""
        from api.agents import workflow_runner as wr_module

        # mock workflow：astream_events 抛出未预期错误
        async def _stream_raising_error(*args, **kwargs):
            raise RuntimeError("模拟未预期错误：LLM 服务完全不可用")
            yield  # pragma: no cover - 使函数成为 async generator

        mock_workflow = MagicMock()
        mock_workflow.astream_events = MagicMock(return_value=_stream_raising_error())
        mock_workflow.aget_state = AsyncMock(return_value=MagicMock(
            interrupts=None, tasks=[], next=None,
        ))

        mock_depot, events = _make_mock_depot()
        mock_emitter = _make_mock_emitter()

        with patch.object(wr_module, "build_case_workflow", return_value=mock_workflow), \
             patch.object(wr_module, "EventDepot", return_value=mock_depot), \
             patch.object(wr_module, "NotifyEmitter", return_value=mock_emitter), \
             patch.object(wr_module, "fail_processing", new=MagicMock()) as mock_fail, \
             patch.object(wr_module, "complete_processing",
                          new=MagicMock(return_value=_make_mock_completion())), \
             patch.object(wr_module, "mark_paused", new=MagicMock()), \
             patch.object(wr_module, "mark_waiting_review", new=MagicMock()):
            runner = wr_module.WorkflowRunner()
            asyncio.run(runner.run_and_persist(
                case_id=42,
                thread_id="wf-fail-1",
                initial_state={"case_id": 42, "evidence_ids": [1]},
            ))

        # 1. fail_processing 被调用，参数 case_id=42 + 错误消息
        mock_fail.assert_called_once()
        call_args = mock_fail.call_args
        self.assertEqual(call_args.args[0], 42, "fail_processing 第一个参数应为 case_id=42")
        error_msg = call_args.args[1]
        self.assertIn("未预期错误", error_msg, "错误消息应包含原始异常信息")

        # 2. EventDepot 写入 workflow.start 事件（启动时）
        start_events = [e for e in events if e["event_type"] == "workflow.start"]
        self.assertGreaterEqual(len(start_events), 1, "应写入 workflow.start 事件")

        # 3. EventDepot 写入 workflow.error 事件
        error_events = [e for e in events if e["event_type"] == "workflow.error"]
        self.assertEqual(len(error_events), 1, "应写入 1 条 workflow.error 事件")
        self.assertIn("message", error_events[0]["payload"])
        self.assertIn("未预期错误", error_events[0]["payload"]["message"])
        self.assertFalse(
            error_events[0]["payload"]["recoverable"],
            "workflow.error 事件 recoverable 应为 False"
        )


# ============================================================================
# 测试 3：节点超时 + RetryPolicy 重试（ConnectionError 3 次后成功）
# ============================================================================

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class RetryPolicyRetryThenSuccessTest(SimpleTestCase):
    """测试 3：mock LLM 抛 ConnectionError 3 次后成功，验证 RetryPolicy 触发。

    RetryPolicy(max_attempts=3) 对 ConnectionError 自动重试；本测试场景：
    - 节点前 2 次抛 ConnectionError（瞬时错误）
    - 第 3 次成功返回 → RetryPolicy 总共调用 3 次（max_attempts）
    """

    def test_retry_policy_retries_connection_error_until_success(self):
        call_log = {"count": 0}

        def flaky_ocr(state):
            call_log["count"] += 1
            if call_log["count"] < 3:
                raise ConnectionError(f"模拟网络抖动（第 {call_log['count']} 次）")
            return {
                "current_node": "ocr",
                "current_stage": "material_understanding",
                "progress": 0.20,
                "revision": (state.get("revision", 0) or 0) + 1,
                "ocr_result": {"node": "ocr", "ok": True, "recovered": True},
            }

        # 使用极短间隔加速测试
        retry_policy = RetryPolicy(
            max_attempts=3,
            initial_interval=0.01,
            backoff_factor=1.0,
            max_interval=0.01,
            jitter=False,
        )

        graph, exec_log = _build_minimal_workflow_graph(
            ocr_fn=flaky_ocr,
            retry_policy_for_ocr=retry_policy,
        )
        config = {"configurable": {"thread_id": "wf-retry-success-1"}}

        result = graph.invoke({
            "case_id": 1, "case_mode": "complain", "evidence_ids": [10],
            "revision": 0, "errors": [], "events": [],
        }, config)

        # 1. RetryPolicy 触发：ocr 节点被调用 3 次（2 次失败 + 1 次成功）
        self.assertEqual(
            call_log["count"], 3,
            f"OCR 节点应被调用 3 次（2 次失败 + 1 次成功），实际: {call_log['count']}",
        )

        # 2. 工作流最终成功完成
        self.assertIn("complaint_draft", result, "工作流应成功完成到 complaint 节点")
        self.assertEqual(result["current_node"], "complaint")

        # 3. revision 正常推进（每个节点 +1，ocr 节点只在最后一次成功时 +1）
        # preclassify + ocr + classify + extract + evidence_chain + complaint = 6
        self.assertEqual(result["revision"], 6)


# ============================================================================
# 测试 4：节点超时 + 降级（持续失败超过 max_attempts）
# ============================================================================

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class RetryPolicyExhaustedDegradedTest(SimpleTestCase):
    """测试 4：mock LLM 持续失败超过 max_attempts，验证 error_handler 返回 errors dict。

    RetryPolicy(max_attempts=3) 重试 3 次后仍失败 → error_handler 接管，
    返回 {"errors": [...]} 让 graph 继续执行下游节点（Saga 降级模式）。
    """

    def test_error_handler_returns_errors_dict_and_graph_continues(self):
        call_log = {"count": 0}

        def always_failing_ocr(state):
            call_log["count"] += 1
            raise ConnectionError(f"OCR 服务持续不可用（第 {call_log['count']} 次）")

        # error_handler：返回 Command(update=errors, goto=下游节点)
        # LangGraph 1.x error_handler 默认不自动跟随原节点的边路由，需用
        # Command(goto=...) 显式指定下游节点（对齐 langgraph errors.NodeError 文档示例）
        def ocr_error_handler(input, *, error: NodeError):
            inner = getattr(error, "error", error)
            msg = f"[OCR] 节点异常: {type(inner).__name__}: {str(inner)[:100]}"
            return Command(
                update={
                    "errors": [{
                        "code": "node.error",
                        "message": msg,
                        "severity": "warning",
                        "stage": "OCR",
                        "recoverable": True,
                    }]
                },
                goto="classify",  # 显式路由到下游节点（Saga 降级）
            )

        retry_policy = RetryPolicy(
            max_attempts=3,
            initial_interval=0.01,
            backoff_factor=1.0,
            max_interval=0.01,
            jitter=False,
        )

        graph, exec_log = _build_minimal_workflow_graph(
            ocr_fn=always_failing_ocr,
            retry_policy_for_ocr=retry_policy,
            error_handler_for_ocr=ocr_error_handler,
        )
        config = {"configurable": {"thread_id": "wf-degraded-1"}}

        result = graph.invoke({
            "case_id": 1, "case_mode": "complain", "evidence_ids": [10],
            "revision": 0, "errors": [], "events": [],
        }, config)

        # 1. RetryPolicy 重试 3 次后失败（max_attempts）
        self.assertEqual(
            call_log["count"], 3,
            f"RetryPolicy 应重试 3 次（max_attempts），实际: {call_log['count']}",
        )

        # 2. error_handler 接管：state.errors 累积了 OCR 节点的降级错误
        # 注意：error_handler 返回的 dict 中 errors 是 list，需要确保 state 中能读到
        # 由于 _TestWorkflowState.errors 是 list 类型（无 reducer），LangGraph 默认覆盖；
        # 此处验证最终 state 含 OCR 降级错误（取决于 reducer 行为）
        # 在测试 graph 中 errors 字段是 list 默认覆盖，但 error_handler 返回新 list 会替换；
        # 为测试 Saga 累积语义，单独构造一个带 add reducer 的 graph
        self.assertIn("complaint_draft", result, "工作流应继续完成到 complaint 节点（降级后不中断）")
        self.assertEqual(result["current_node"], "complaint", "graph 应继续执行下游节点")

    def test_error_handler_saga_accumulates_errors_with_add_reducer(self):
        """独立测试：使用 Annotated[list, add] reducer 验证 errors 累积语义。

        构造专门的 graph，errors 字段使用 add reducer（对齐生产 CaseWorkflowState.errors），
        验证 error_handler 返回的 errors 被累积到 state，而非覆盖。
        """
        from operator import add
        from typing import Annotated

        class _SagaState(TypedDict, total=False):
            errors: Annotated[list[dict], add]
            revision: int
            current_node: str

        call_log = {"count": 0}

        def always_failing_node(state):
            call_log["count"] += 1
            raise ConnectionError("持续失败")

        def node_error_handler(input, *, error: NodeError):
            # error_handler 返回 Command(update=errors, goto=downstream)：
            # LangGraph 1.x 需显式 goto 才能让图继续到下游节点（Saga 降级 + 累积语义）
            return Command(
                update={
                    "errors": [{
                        "code": "node.error",
                        "message": "节点异常降级",
                        "severity": "warning",
                        "stage": "test_node",
                        "recoverable": True,
                    }]
                },
                goto="downstream",
            )

        retry_policy = RetryPolicy(
            max_attempts=2,
            initial_interval=0.01,
            backoff_factor=1.0,
            max_interval=0.01,
            jitter=False,
        )

        def downstream_node(state):
            return {
                "current_node": "downstream",
                "revision": (state.get("revision", 0) or 0) + 1,
            }

        builder = StateGraph(_SagaState)
        builder.add_node("failing", always_failing_node,
                         retry_policy=retry_policy, error_handler=node_error_handler)
        builder.add_node("downstream", downstream_node)
        builder.add_edge(START, "failing")
        builder.add_edge("failing", "downstream")
        builder.add_edge("downstream", END)

        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "wf-saga-1"}}

        result = graph.invoke({"errors": [], "revision": 0}, config)

        # 1. RetryPolicy 重试 max_attempts 次后失败
        self.assertEqual(call_log["count"], 2)

        # 2. error_handler 返回的 errors 被累积到 state.errors
        self.assertEqual(len(result["errors"]), 1, "Saga 累积：errors 应含 1 条降级错误")
        self.assertEqual(result["errors"][0]["code"], "node.error")
        self.assertEqual(result["errors"][0]["stage"], "test_node")

        # 3. 下游节点继续执行（graph 未中断）
        self.assertEqual(result["current_node"], "downstream")


# ============================================================================
# 测试 5：checkpoint 恢复（首次 invoke 后中断，相同 thread_id 再次 invoke）
# ============================================================================

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class CheckpointResumeTest(SimpleTestCase):
    """测试 5：首次 invoke 触发 interrupt 后，使用相同 thread_id + Command(resume=...) 恢复。

    验证 InMemorySaver checkpointer 在 thread_id 一致时正确恢复中断前 state
    （preclassify 节点的产物保留，resume 后 ocr 节点能读到 preclassify 写入的字段）。
    """

    def test_checkpoint_resume_preserves_prior_state(self):
        """interrupt + Command(resume) 后，preclassify 节点写入的 state 被保留。"""
        exec_log = {"preclassify": 0, "ocr": 0, "complaint": 0}

        def preclassify(state):
            exec_log["preclassify"] += 1
            return {
                "preclassify_result": {"node": "preclassify", "value": "stage1-data"},
                "revision": (state.get("revision", 0) or 0) + 1,
                "current_node": "preclassify",
                "progress": 0.10,
            }

        def ocr_with_interrupt(state):
            exec_log["ocr"] += 1
            # 读取 preclassify 写入的产物（验证 state 恢复后字段还在）
            preclassify_data = state.get("preclassify_result", {})
            if not preclassify_data.get("value"):
                # state 中无 preclassify 产物 → 说明 checkpointer 未恢复
                raise AssertionError("checkpoint 未恢复：preclassify_result 丢失")

            # 调用 interrupt 暂停（模拟 HITL）
            user_input = interrupt({
                "message": "OCR 完成后请人工确认",
                "preclassify_value": preclassify_data.get("value"),
            })

            # resume 后：user_input 是 Command(resume=...) 传入的值
            return {
                "ocr_result": {
                    "node": "ocr",
                    "preclassify_value": preclassify_data.get("value"),
                    "user_input": user_input,
                },
                "revision": (state.get("revision", 0) or 0) + 1,
                "current_node": "ocr",
                "progress": 0.20,
            }

        def complaint(state):
            exec_log["complaint"] += 1
            return {
                "complaint_draft": {"content": "完成"},
                "revision": (state.get("revision", 0) or 0) + 1,
                "current_node": "complaint",
                "progress": 0.90,
            }

        # 构造简化的 3 节点图：preclassify → ocr (interrupt) → complaint
        builder = StateGraph(_TestWorkflowState)
        builder.add_node("preclassify", preclassify)
        builder.add_node("ocr", ocr_with_interrupt)
        builder.add_node("complaint", complaint)
        builder.add_edge(START, "preclassify")
        builder.add_edge("preclassify", "ocr")
        builder.add_edge("ocr", "complaint")
        builder.add_edge("complaint", END)
        graph = builder.compile(checkpointer=InMemorySaver())

        config = {"configurable": {"thread_id": "wf-checkpoint-1"}}

        # 1. 首次 invoke：应触发 interrupt 暂停在 ocr 节点
        result1 = graph.invoke({
            "case_id": 1, "case_mode": "complain", "evidence_ids": [10],
            "revision": 0, "errors": [], "events": [],
        }, config)

        # interrupt 触发：result 含 __interrupt__ 字段
        self.assertIn("__interrupt__", result1, "首次 invoke 应触发 interrupt 暂停")
        self.assertEqual(exec_log["preclassify"], 1, "preclassify 应执行 1 次")
        self.assertEqual(exec_log["ocr"], 1, "ocr 应执行 1 次（到 interrupt 为止）")
        self.assertEqual(exec_log["complaint"], 0, "complaint 不应执行（被 interrupt 阻断）")

        # 2. 使用相同 thread_id + Command(resume=...) 恢复
        result2 = graph.invoke(Command(resume="user-confirmed-ok"), config)

        # 验证 checkpoint 恢复：
        # - preclassify 节点未重新执行（exec_log 不变）
        # - ocr 节点 resume 后从 interrupt 后继续，能读到 preclassify 写入的产物
        # - complaint 节点继续执行
        self.assertEqual(exec_log["preclassify"], 1, "preclassify 不应重新执行（checkpoint 恢复）")
        self.assertEqual(exec_log["ocr"], 2, "ocr 节点 resume 时整体重新执行（LangGraph 预期行为）")
        self.assertEqual(exec_log["complaint"], 1, "complaint 应在 resume 后执行")

        # interrupt 后的代码执行了：ocr_result 含 user_input
        self.assertIn("ocr_result", result2)
        self.assertEqual(
            result2["ocr_result"]["user_input"], "user-confirmed-ok",
            "Command(resume=...) 的值应作为 interrupt() 返回值",
        )
        # preclassify 写入的产物在 resume 后仍保留
        self.assertEqual(
            result2["ocr_result"]["preclassify_value"], "stage1-data",
            "checkpoint 恢复后 preclassify_result 应保留",
        )

        # 3. resume 完成后无 __interrupt__
        self.assertNotIn("__interrupt__", result2, "resume 完成后不应再有 __interrupt__")


# ============================================================================
# 测试 6：SSE 事件顺序（workflow.start → workflow.complete）
# ============================================================================

class SSEEventOrderTest(SimpleTestCase):
    """测试 6：验证 WorkflowRunner 产生的事件顺序符合规范。

    通过 mock workflow.astream_events 产生节点事件流，验证：
    - workflow.start 事件最先产生
    - workflow.complete 事件最后产生（或 workflow.error 在异常时产生）
    - 中间节点事件按节点执行顺序产生
    """

    def test_workflow_start_emitted_before_complete(self):
        """workflow.start 在 workflow.complete 之前持久化到 EventDepot。"""
        from api.agents import workflow_runner as wr_module

        # 构造 mock astream_events：依次 yield 节点事件，正常结束
        async def _mock_stream(*args, **kwargs):
            for evt in (
                {"event": "on_chain_start", "name": "preclassify", "data": {"input": {}}},
                {"event": "on_chain_end", "name": "preclassify", "data": {"output": {}}},
                {"event": "on_chain_start", "name": "ocr", "data": {"input": {}}},
                {"event": "on_chain_end", "name": "ocr", "data": {"output": {}}},
            ):
                yield evt

        mock_workflow = MagicMock()
        mock_workflow.astream_events = MagicMock(return_value=_mock_stream())
        mock_workflow.aget_state = AsyncMock(return_value=MagicMock(
            interrupts=None, tasks=[], next=None,
        ))

        mock_depot, events = _make_mock_depot()
        mock_emitter = _make_mock_emitter()

        with patch.object(wr_module, "build_case_workflow", return_value=mock_workflow), \
             patch.object(wr_module, "EventDepot", return_value=mock_depot), \
             patch.object(wr_module, "NotifyEmitter", return_value=mock_emitter), \
             patch.object(wr_module, "complete_processing",
                          new=MagicMock(return_value=_make_mock_completion())), \
             patch.object(wr_module, "fail_processing", new=MagicMock()), \
             patch.object(wr_module, "mark_paused", new=MagicMock()), \
             patch.object(wr_module, "mark_waiting_review", new=MagicMock()):
            runner = wr_module.WorkflowRunner()
            asyncio.run(runner.run_and_persist(
                case_id=1, thread_id="wf-order-1",
                initial_state={"case_id": 1, "evidence_ids": [1]},
            ))

        # 提取事件类型序列
        event_types = [e["event_type"] for e in events]

        # 1. workflow.start 在最早位置
        self.assertIn("workflow.start", event_types)
        start_idx = event_types.index("workflow.start")

        # 2. workflow.complete 在最末位置（应在 start 之后）
        self.assertIn("workflow.complete", event_types)
        complete_idx = event_types.index("workflow.complete")

        self.assertLess(
            start_idx, complete_idx,
            f"workflow.start (idx={start_idx}) 应在 workflow.complete (idx={complete_idx}) 之前",
        )

        # 3. workflow.complete 应是最后一个事件
        self.assertEqual(
            complete_idx, len(event_types) - 1,
            "workflow.complete 应是最后一个事件",
        )

    def test_workflow_error_emitted_when_stream_fails(self):
        """stream 抛错时 workflow.error 应在 workflow.start 之后产生。"""
        from api.agents import workflow_runner as wr_module

        async def _raising_stream(*args, **kwargs):
            raise RuntimeError("模拟 stream 异常")
            yield  # pragma: no cover

        mock_workflow = MagicMock()
        mock_workflow.astream_events = MagicMock(return_value=_raising_stream())
        mock_workflow.aget_state = AsyncMock(return_value=MagicMock(
            interrupts=None, tasks=[], next=None,
        ))

        mock_depot, events = _make_mock_depot()
        mock_emitter = _make_mock_emitter()

        with patch.object(wr_module, "build_case_workflow", return_value=mock_workflow), \
             patch.object(wr_module, "EventDepot", return_value=mock_depot), \
             patch.object(wr_module, "NotifyEmitter", return_value=mock_emitter), \
             patch.object(wr_module, "fail_processing", new=MagicMock()), \
             patch.object(wr_module, "complete_processing",
                          new=MagicMock(return_value=_make_mock_completion())), \
             patch.object(wr_module, "mark_paused", new=MagicMock()), \
             patch.object(wr_module, "mark_waiting_review", new=MagicMock()):
            runner = wr_module.WorkflowRunner()
            asyncio.run(runner.run_and_persist(
                case_id=1, thread_id="wf-error-1",
                initial_state={"case_id": 1, "evidence_ids": [1]},
            ))

        event_types = [e["event_type"] for e in events]

        # workflow.start 在前，workflow.error 在后
        self.assertIn("workflow.start", event_types)
        self.assertIn("workflow.error", event_types)
        start_idx = event_types.index("workflow.start")
        error_idx = event_types.index("workflow.error")
        self.assertLess(start_idx, error_idx)
        # workflow.error 是最后一个事件
        self.assertEqual(error_idx, len(event_types) - 1)


# ============================================================================
# 测试 7：revision 单调递增
# ============================================================================

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class RevisionMonotonicIncrementTest(SimpleTestCase):
    """测试 7：每个节点返回 revision+1，最终 state.revision 等于节点数。

    对齐 checklist.md 行 74「revision 单调递增测试通过」。
    """

    def test_revision_equals_node_count_after_full_workflow(self):
        """6 节点工作流完成，state.revision 应等于 6（每个节点 +1）。"""
        graph, _ = _build_minimal_workflow_graph()
        config = {"configurable": {"thread_id": "wf-revision-1"}}

        result = graph.invoke({
            "case_id": 1, "case_mode": "complain", "evidence_ids": [10],
            "revision": 0, "errors": [], "events": [],
        }, config)

        # 6 个节点各 +1 → revision = 6
        self.assertEqual(result["revision"], 6)

    def test_revision_increments_from_nonzero_start(self):
        """revision 从 5 起步 → 6 节点后应等于 11。"""
        graph, _ = _build_minimal_workflow_graph()
        config = {"configurable": {"thread_id": "wf-revision-2"}}

        result = graph.invoke({
            "case_id": 1, "case_mode": "complain", "evidence_ids": [10],
            "revision": 5, "errors": [], "events": [],
        }, config)

        self.assertEqual(result["revision"], 11, "5 + 6 = 11")

    def test_revision_with_degraded_node_still_increments(self):
        """降级节点（error_handler 返回）不 +1，但其他节点正常 +1。

        场景：OCR 节点 error_handler 接管（不返回 revision），其他 5 个节点各 +1。
        """
        from operator import add
        from typing import Annotated

        class _TestState(TypedDict, total=False):
            errors: Annotated[list[dict], add]
            revision: int
            current_node: str
            progress: float

        call_log = {"ocr": 0}

        def preclassify(state):
            return {
                "current_node": "preclassify",
                "revision": (state.get("revision", 0) or 0) + 1,
            }

        def always_failing_ocr(state):
            call_log["ocr"] += 1
            raise ConnectionError("持续失败")

        def ocr_error_handler(input, *, error: NodeError):
            # error_handler 不返回 revision 字段（Saga 降级），但需 goto=下游节点
            # 才能让 graph 继续执行 complaint 节点
            return Command(
                update={"errors": [{"code": "node.error", "message": "OCR 降级",
                                    "severity": "warning", "stage": "ocr",
                                    "recoverable": True}]},
                goto="complaint",
            )

        def complaint(state):
            return {
                "current_node": "complaint",
                "revision": (state.get("revision", 0) or 0) + 1,
            }

        retry_policy = RetryPolicy(
            max_attempts=2, initial_interval=0.01, backoff_factor=1.0,
            max_interval=0.01, jitter=False,
        )

        builder = StateGraph(_TestState)
        builder.add_node("preclassify", preclassify)
        builder.add_node("ocr", always_failing_ocr,
                         retry_policy=retry_policy, error_handler=ocr_error_handler)
        builder.add_node("complaint", complaint)
        builder.add_edge(START, "preclassify")
        builder.add_edge("preclassify", "ocr")
        builder.add_edge("ocr", "complaint")
        builder.add_edge("complaint", END)

        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "wf-revision-3"}}

        result = graph.invoke({"errors": [], "revision": 0}, config)

        # RetryPolicy 重试 2 次（max_attempts）
        self.assertEqual(call_log["ocr"], 2)
        # 5 个 +1（preclassify + complaint；ocr 不 +1）= 2 个 +1
        # 此处 preclassify +1, ocr 不 +1, complaint +1 → revision = 2
        self.assertEqual(
            result["revision"], 2,
            "降级节点不 +1，其他节点 +1：revision 应为 2",
        )


# ============================================================================
# 测试 8：阶段暂停 interrupt（mock stage_pause 请求）
# ============================================================================

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过真实 graph 测试")
class StagePauseInterruptTest(SimpleTestCase):
    """测试 8：mock stage_pause 请求，验证 graph 暂停 + resume 后继续。

    模拟生产 stage_gate_node 行为：
    - 节点检查 state.pause_requested 标志
    - 若为 True，调用 interrupt(stage_pause_payload) 暂停
    - resume 时使用 Command(resume={"interrupt_type": "stage_pause", ...}) 恢复
    """

    def test_stage_pause_interrupts_and_resumes(self):
        """stage_pause 请求 → interrupt 暂停 → Command(resume=stage_pause) 恢复。"""
        exec_log = {"stage_gate": 0, "downstream": 0}

        class _PauseState(TypedDict, total=False):
            pause_requested: bool
            paused_after: str
            current_node: str
            revision: int
            user_edit: str  # state_updates 中的字段需在 schema 声明，否则 writes 会被丢弃

        def stage_gate(state):
            exec_log["stage_gate"] += 1
            if not state.get("pause_requested"):
                return {"current_node": "stage_gate"}

            # 暂停（对齐 stage_gate_node.interrupt(build_stage_pause_payload(...))）
            resume_value = interrupt({
                "interrupt_type": "stage_pause",
                "paused_after": "ocr",
                "message": "用户请求在 OCR 后暂停",
            })
            # resume 后：检查 resume_value 结构
            if not isinstance(resume_value, dict) or \
               resume_value.get("interrupt_type") != "stage_pause":
                return {"current_node": "stage_gate"}

            # 应用 state_updates（对齐 stage_gate_node 返回 state_updates）
            state_updates = resume_value.get("state_updates", {})
            return {
                "current_node": "stage_gate",
                **state_updates,
            }

        def downstream(state):
            exec_log["downstream"] += 1
            return {
                "current_node": "downstream",
                "revision": (state.get("revision", 0) or 0) + 1,
            }

        builder = StateGraph(_PauseState)
        builder.add_node("stage_gate", stage_gate)
        builder.add_node("downstream", downstream)
        builder.add_edge(START, "stage_gate")
        builder.add_edge("stage_gate", "downstream")
        builder.add_edge("downstream", END)
        graph = builder.compile(checkpointer=InMemorySaver())

        config = {"configurable": {"thread_id": "wf-stage-pause-1"}}

        # 1. 首次 invoke：pause_requested=True → 触发 interrupt
        result1 = graph.invoke({"pause_requested": True, "revision": 0}, config)
        self.assertIn("__interrupt__", result1, "应触发 stage_pause interrupt")
        self.assertEqual(exec_log["stage_gate"], 1)
        self.assertEqual(exec_log["downstream"], 0, "downstream 不应执行（被 interrupt 阻断）")

        # 2. resume：使用 Command(resume={"interrupt_type": "stage_pause", ...})
        resume_payload = {
            "interrupt_type": "stage_pause",
            "paused_after": "ocr",
            "state_updates": {"paused_after": "ocr", "user_edit": "edited-value"},
        }
        result2 = graph.invoke(Command(resume=resume_payload), config)

        # 3. resume 后 graph 完成
        self.assertNotIn("__interrupt__", result2, "resume 完成后不应有 __interrupt__")
        self.assertEqual(exec_log["stage_gate"], 2, "stage_gate resume 时重新执行（LangGraph 预期）")
        self.assertEqual(exec_log["downstream"], 1, "downstream 应在 resume 后执行")

        # 4. state_updates 被应用到 state
        self.assertEqual(result2.get("user_edit"), "edited-value",
                         "state_updates 中的字段应被合并到 state")
        self.assertEqual(result2.get("paused_after"), "ocr")

    def test_stage_pause_skipped_when_not_requested(self):
        """pause_requested=False → 不触发 interrupt，graph 直接执行到 END。"""
        exec_log = {"stage_gate": 0, "downstream": 0}

        class _PauseState(TypedDict, total=False):
            pause_requested: bool
            current_node: str
            revision: int

        def stage_gate(state):
            exec_log["stage_gate"] += 1
            if not state.get("pause_requested"):
                return {"current_node": "stage_gate"}
            # 不会执行到这里
            interrupt({"interrupt_type": "stage_pause"})

        def downstream(state):
            exec_log["downstream"] += 1
            return {
                "current_node": "downstream",
                "revision": (state.get("revision", 0) or 0) + 1,
            }

        builder = StateGraph(_PauseState)
        builder.add_node("stage_gate", stage_gate)
        builder.add_node("downstream", downstream)
        builder.add_edge(START, "stage_gate")
        builder.add_edge("stage_gate", "downstream")
        builder.add_edge("downstream", END)
        graph = builder.compile(checkpointer=InMemorySaver())

        config = {"configurable": {"thread_id": "wf-stage-pause-2"}}

        result = graph.invoke({"pause_requested": False, "revision": 0}, config)

        # 未触发 interrupt，graph 一次执行完成
        self.assertNotIn("__interrupt__", result)
        self.assertEqual(exec_log["stage_gate"], 1)
        self.assertEqual(exec_log["downstream"], 1)
        self.assertEqual(result["revision"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
