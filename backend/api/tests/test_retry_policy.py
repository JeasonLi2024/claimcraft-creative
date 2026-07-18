# -*- coding: utf-8 -*-
"""Task 0.4.5：LangGraph RetryPolicy 配置测试。

测试目标（对齐 SubTask 0.4.5）：
1. 验证 LLM 节点（preclassify / classify / extract / evidence_chain / complaint /
   respond_complaint）+ OCR 节点（ocr）的 `add_node` 调用包含 `retry_policy` 参数，
   且参数值为 `RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0,
   max_interval=10.0)`
2. 验证 HITL 节点（review / stage_gate_after_*）的 `add_node` 调用 **不包含**
   `retry_policy` 参数（用户介入节点不应自动重试）
3. 集成测试：mock 一个节点抛出 `ConnectionError`（瞬时错误），验证 RetryPolicy
   自动重试 3 次后才失败

设计说明：
- 测试 1/2 通过 mock `StateGraph.add_node` 捕获调用 kwargs，避免依赖真实 DB
  checkpointer / store（mock `compile` + `_get_checkpointer` + `_get_store`）
- 测试 3 使用 `InMemorySaver` 构建最小独立图，验证 RetryPolicy 真实重试行为
- RetryPolicy 导入路径：`from langgraph.types import RetryPolicy`（LangGraph 1.2+）
"""
import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# 确保 Django 环境可用（settings 模块 + setup）
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django  # noqa: E402
from django.apps import apps as django_apps  # noqa: E402

if not getattr(django_apps, 'ready', False):
    django.setup()

from api.agents import graph as graph_module  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.graph import StateGraph, START, END  # noqa: E402
from langgraph.types import RetryPolicy  # noqa: E402
from typing_extensions import TypedDict  # noqa: E402


# ============================================================================
# 测试常量：节点分类（对齐 Task 0.4.1 审计结果）
# ============================================================================
# 调用外部 LLM / OCR API 的节点（应配置 retry_policy）
LLM_OCR_NODES = {
    "preclassify",       # Captioner LLM（ainvoke）
    "ocr",               # ocr_image_with_strategy 多策略 OCR pipeline
    "classify",          # text LLM with_structured_output
    "extract",           # langextract / with_structured_output
    "evidence_chain",    # invoke_llm_with_tools / structured LLM
    "complaint",         # invoke_llm_with_tools / chat_with_retry
    "respond_complaint",  # invoke_llm_with_tools / chat_with_retry
}

# HITL 节点（不配置 retry_policy，应让用户介入）
HITL_NODES = {"review"}

# stage_gate 节点前缀（动态生成：stage_gate_after_<business_node>）
STAGE_GATE_PREFIX = "stage_gate_after_"


# ============================================================================
# Fixtures
# ============================================================================
@pytest.fixture
def reset_workflow_singletons():
    """重置 graph 模块的单例（_workflow / _checkpointer / _store）。

    build_case_workflow() / _get_checkpointer() / _get_store() 都使用模块级
    单例缓存，测试间必须重置以避免污染。
    """
    originals = {
        '_workflow': graph_module._workflow,
        '_checkpointer': graph_module._checkpointer,
        '_store': graph_module._store,
    }
    graph_module._workflow = None
    graph_module._checkpointer = None
    graph_module._store = None
    try:
        yield
    finally:
        graph_module._workflow = originals['_workflow']
        graph_module._checkpointer = originals['_checkpointer']
        graph_module._store = originals['_store']


def _build_workflow_with_spy():
    """使用 spy 捕获 add_node 调用，mock compile / checkpointer / store。

    Returns:
        (workflow, add_node_calls) — workflow 是 mock 编译结果，
        add_node_calls 是 [(node_name, kwargs), ...] 列表
    """
    add_node_calls: list[tuple[str, dict[str, Any]]] = []
    original_add_node = StateGraph.add_node

    def spy_add_node(self, node, action=None, **kwargs):
        add_node_calls.append((node, kwargs))
        return original_add_node(self, node, action, **kwargs)

    mock_compiled = MagicMock(name='compiled_graph')
    with patch.object(StateGraph, 'add_node', spy_add_node), \
            patch.object(StateGraph, 'compile', return_value=mock_compiled), \
            patch.object(graph_module, '_get_checkpointer', return_value=MagicMock(name='checkpointer')), \
            patch.object(graph_module, '_get_store', return_value=MagicMock(name='store')):
        workflow = graph_module.build_case_workflow()

    return workflow, add_node_calls


# ============================================================================
# 测试 1：LLM/OCR 节点配置 retry_policy（对齐 SubTask 0.4.5 测试 1）
# ============================================================================
class TestLLMOCRNodesRetryPolicy:
    """验证调用外部 API 的节点（LLM/OCR）在 add_node 时配置了 retry_policy。"""

    def test_all_llm_ocr_nodes_have_retry_policy(self, reset_workflow_singletons):
        """LLM/OCR 7 个节点的 add_node 调用都包含 retry_policy 参数。"""
        _, add_node_calls = _build_workflow_with_spy()
        add_node_dict = {name: kwargs for name, kwargs in add_node_calls}

        missing = LLM_OCR_NODES - set(add_node_dict.keys())
        assert not missing, f"缺少节点: {missing}"

        for node_name in LLM_OCR_NODES:
            kwargs = add_node_dict[node_name]
            assert 'retry_policy' in kwargs, (
                f"节点 {node_name} 应配置 retry_policy（调用外部 LLM/OCR API），"
                f"实际 kwargs: {list(kwargs.keys())}"
            )

    def test_retry_policy_has_correct_values(self, reset_workflow_singletons):
        """retry_policy 参数值符合规范：max_attempts=3, initial_interval=1.0,
        backoff_factor=2.0, max_interval=10.0。"""
        _, add_node_calls = _build_workflow_with_spy()
        add_node_dict = {name: kwargs for name, kwargs in add_node_calls}

        for node_name in LLM_OCR_NODES:
            rp = add_node_dict[node_name]['retry_policy']
            assert isinstance(rp, RetryPolicy), (
                f"节点 {node_name} 的 retry_policy 应为 RetryPolicy 实例，"
                f"实际类型: {type(rp).__name__}"
            )
            assert rp.max_attempts == 3, (
                f"节点 {node_name} retry_policy.max_attempts 应为 3，实际: {rp.max_attempts}"
            )
            assert rp.initial_interval == 1.0, (
                f"节点 {node_name} retry_policy.initial_interval 应为 1.0，"
                f"实际: {rp.initial_interval}"
            )
            assert rp.backoff_factor == 2.0, (
                f"节点 {node_name} retry_policy.backoff_factor 应为 2.0，"
                f"实际: {rp.backoff_factor}"
            )
            assert rp.max_interval == 10.0, (
                f"节点 {node_name} retry_policy.max_interval 应为 10.0，"
                f"实际: {rp.max_interval}"
            )

    def test_llm_ocr_nodes_also_have_timeout_and_error_handler(self, reset_workflow_singletons):
        """LLM/OCR 节点同时保留 timeout + error_handler（三者协同）。"""
        _, add_node_calls = _build_workflow_with_spy()
        add_node_dict = {name: kwargs for name, kwargs in add_node_calls}

        for node_name in LLM_OCR_NODES:
            kwargs = add_node_dict[node_name]
            assert 'timeout' in kwargs, f"节点 {node_name} 应保留 timeout 参数"
            assert 'error_handler' in kwargs, f"节点 {node_name} 应保留 error_handler 参数"
            assert 'retry_policy' in kwargs, f"节点 {node_name} 应新增 retry_policy 参数"


# ============================================================================
# 测试 2：HITL 节点不配置 retry_policy（对齐 SubTask 0.4.5 测试 2）
# ============================================================================
class TestHITLNodesNoRetryPolicy:
    """验证 HITL 节点（review / stage_gate_after_*）不配置 retry_policy。"""

    def test_review_node_has_no_retry_policy(self, reset_workflow_singletons):
        """review 节点不配置 retry_policy（HITL 节点应让用户介入）。"""
        _, add_node_calls = _build_workflow_with_spy()
        add_node_dict = {name: kwargs for name, kwargs in add_node_calls}

        for node_name in HITL_NODES:
            assert node_name in add_node_dict, f"缺少节点: {node_name}"
            kwargs = add_node_dict[node_name]
            assert 'retry_policy' not in kwargs, (
                f"节点 {node_name} 是 HITL 节点，不应配置 retry_policy，"
                f"实际 kwargs: {list(kwargs.keys())}"
            )

    def test_stage_gate_nodes_have_no_retry_policy(self, reset_workflow_singletons):
        """所有 stage_gate_after_* 节点不配置 retry_policy（HITL 暂停门）。"""
        _, add_node_calls = _build_workflow_with_spy()

        stage_gate_nodes = [
            (name, kwargs) for name, kwargs in add_node_calls
            if name.startswith(STAGE_GATE_PREFIX)
        ]
        # 8 个业务节点对应 8 个 stage_gate 节点
        assert len(stage_gate_nodes) == 8, (
            f"应有 8 个 stage_gate 节点，实际: {len(stage_gate_nodes)}"
        )

        for node_name, kwargs in stage_gate_nodes:
            assert 'retry_policy' not in kwargs, (
                f"节点 {node_name} 是 HITL 暂停门，不应配置 retry_policy，"
                f"实际 kwargs: {list(kwargs.keys())}"
            )

    def test_review_node_keeps_timeout_and_error_handler(self, reset_workflow_singletons):
        """review 节点保留 timeout + error_handler（仅不配置 retry_policy）。"""
        _, add_node_calls = _build_workflow_with_spy()
        add_node_dict = {name: kwargs for name, kwargs in add_node_calls}

        kwargs = add_node_dict['review']
        assert 'timeout' in kwargs, "review 节点应保留 timeout 参数"
        assert 'error_handler' in kwargs, "review 节点应保留 error_handler 参数"
        assert 'retry_policy' not in kwargs, "review 节点不应配置 retry_policy"


# ============================================================================
# 测试 3：RetryPolicy 实际重试行为（对齐 SubTask 0.4.5 集成测试）
# ============================================================================
class TestRetryPolicyActualBehavior:
    """验证 RetryPolicy 在节点抛出 ConnectionError 时自动重试 3 次。

    使用 InMemorySaver 构建最小独立图，避免依赖真实 PostgresSaver。
    """

    def test_connection_error_retries_3_times(self):
        """节点抛出 ConnectionError 时，RetryPolicy 自动重试 3 次（max_attempts）后失败。"""
        call_count = {'count': 0}

        class TestState(TypedDict):
            value: str

        def failing_node(state: TestState) -> dict:
            call_count['count'] += 1
            raise ConnectionError("Simulated network error (瞬时错误)")

        # 使用极短间隔加速测试（不验证退避时长，仅验证重试次数）
        retry_policy = RetryPolicy(
            max_attempts=3,
            initial_interval=0.01,
            backoff_factor=1.0,
            max_interval=0.01,
            jitter=False,
        )

        builder = StateGraph(TestState)
        builder.add_node("failing_node", failing_node, retry_policy=retry_policy)
        builder.add_edge(START, "failing_node")
        builder.add_edge("failing_node", END)

        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "test-retry-1"}}

        # RetryPolicy 重试 3 次后仍失败，应抛出 ConnectionError
        with pytest.raises(ConnectionError):
            graph.invoke({"value": "test"}, config)

        # 验证重试次数 = max_attempts（3 次）
        assert call_count['count'] == 3, (
            f"RetryPolicy 应自动重试 3 次（max_attempts），实际调用次数: {call_count['count']}"
        )

    def test_non_retryable_error_does_not_retry(self):
        """ValueError 不在 default_retry_on 重试范围内，应立即失败不重试。

        default_retry_on 对 ValueError / TypeError / RuntimeError / OSError 等返回 False，
        仅对 ConnectionError / httpx 5xx / requests 5xx 等瞬时错误重试。
        """
        call_count = {'count': 0}

        class TestState(TypedDict):
            value: str

        def failing_node(state: TestState) -> dict:
            call_count['count'] += 1
            raise ValueError("非瞬时错误（数据格式问题），不应重试")

        retry_policy = RetryPolicy(
            max_attempts=3,
            initial_interval=0.01,
            backoff_factor=1.0,
            max_interval=0.01,
            jitter=False,
        )

        builder = StateGraph(TestState)
        builder.add_node("failing_node", failing_node, retry_policy=retry_policy)
        builder.add_edge(START, "failing_node")
        builder.add_edge("failing_node", END)

        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "test-retry-2"}}

        with pytest.raises(ValueError):
            graph.invoke({"value": "test"}, config)

        # 验证未重试（仅调用 1 次）
        assert call_count['count'] == 1, (
            f"ValueError 不应触发重试，实际调用次数: {call_count['count']}"
        )

    def test_retry_succeeds_on_second_attempt(self):
        """节点首次失败、第二次成功时，RetryPolicy 应自动重试并最终成功。"""
        call_count = {'count': 0}

        class TestState(TypedDict):
            value: str

        def flaky_node(state: TestState) -> dict:
            call_count['count'] += 1
            if call_count['count'] == 1:
                raise ConnectionError("首次调用网络抖动")
            return {"value": "recovered"}

        retry_policy = RetryPolicy(
            max_attempts=3,
            initial_interval=0.01,
            backoff_factor=1.0,
            max_interval=0.01,
            jitter=False,
        )

        builder = StateGraph(TestState)
        builder.add_node("flaky_node", flaky_node, retry_policy=retry_policy)
        builder.add_edge(START, "flaky_node")
        builder.add_edge("flaky_node", END)

        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "test-retry-3"}}

        result = graph.invoke({"value": "initial"}, config)

        # 验证重试后成功
        assert call_count['count'] == 2, (
            f"应在第 2 次调用成功，实际调用次数: {call_count['count']}"
        )
        assert result['value'] == 'recovered'


# ============================================================================
# 测试 4：RetryPolicy 导入路径验证（对齐 SubTask 0.4.2 约束）
# ============================================================================
class TestRetryPolicyImport:
    """验证 RetryPolicy 从 langgraph.types 导入（LangGraph 1.2+ 官方入口）。"""

    def test_retry_policy_importable_from_langgraph_types(self):
        """RetryPolicy 可从 langgraph.types 导入（LangGraph 1.2+ 官方路径）。"""
        from langgraph.types import RetryPolicy as ImportedRetryPolicy
        assert ImportedRetryPolicy is RetryPolicy

    def test_graph_module_uses_retry_policy(self):
        """graph 模块导出的 _API_NODE_RETRY_POLICY 是 RetryPolicy 实例。"""
        from api.agents.graph import _API_NODE_RETRY_POLICY
        assert isinstance(_API_NODE_RETRY_POLICY, RetryPolicy)
        assert _API_NODE_RETRY_POLICY.max_attempts == 3
        assert _API_NODE_RETRY_POLICY.initial_interval == 1.0
        assert _API_NODE_RETRY_POLICY.backoff_factor == 2.0
        assert _API_NODE_RETRY_POLICY.max_interval == 10.0
