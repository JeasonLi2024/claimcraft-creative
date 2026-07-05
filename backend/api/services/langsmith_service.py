# -*- coding: utf-8 -*-
"""LangSmith 观察配置服务：程序化配置 + 区域端点解析 + 采样控制。

与 llm_service.py 风格一致，提供单例 Client + tracing_context 包装 +
should_sample 程序化采样。所有接口在 LangSmith 未启用或 langsmith 包缺失时
降级为 no-op，保证业务代码无感知。

环境变量（与 settings.py LangSmith 块一致）：
- LANGSMITH_TRACING:        true/false，是否启用 trace
- LANGSMITH_API_KEY:        LangSmith API Key
- LANGSMITH_ENDPOINT:       自定义端点（与 LANGSMITH_REGION 二选一）
- LANGSMITH_REGION:         区域代码（us/eu/ap/cn），优先于 ENDPOINT
- LANGSMITH_PROJECT:        项目名（默认 claimcraft-creative）
- LANGSMITH_WORKSPACE_ID:   Workspace ID（多 workspace 隔离时填写）
- LANGSMITH_SAMPLING_RATE:  采样率 0.0-1.0（默认 1，全量采样）

核心接口：
- is_tracing_enabled(): tracing 是否启用
- get_langsmith_client(): 懒加载 Client 单例
- trace_context(**kwargs): 包装 langsmith.tracing_context，禁用降级 nullcontext
- should_sample(): 程序化采样判断
- trace_for_case(case_id, owner_id, *, case_type, has_sensitive): 按 case 注入
  追踪上下文（敏感证据 enabled=False 零数据保留；按 case_type 路由 project_name）
"""
import contextlib
import logging
import os
import random

logger = logging.getLogger(__name__)

# 单例缓存
_client = None
_endpoint_resolved = None

# LangSmith 区域端点映射（覆盖 LangSmith Cloud 主要区域）
_REGION_ENDPOINTS = {
    "us": "https://api.smith.langchain.com",
    "eu": "https://eu.api.smith.langchain.com",
    "ap": "https://api.smith.langchain.com",  # 亚太暂用默认
    "cn": "https://api.smith.langchain.com",  # 国内中转，按需调整
}


def is_tracing_enabled() -> bool:
    """是否启用 LangSmith trace。"""
    return os.environ.get("LANGSMITH_TRACING", "false").lower() == "true"


def _resolve_endpoint() -> str:
    """解析 LangSmith 端点：LANGSMITH_REGION 优先，其次 LANGSMITH_ENDPOINT，最后默认值。

    缓存解析结果避免重复计算。
    """
    global _endpoint_resolved
    if _endpoint_resolved is not None:
        return _endpoint_resolved
    region = os.environ.get("LANGSMITH_REGION", "").strip().lower()
    if region and region in _REGION_ENDPOINTS:
        _endpoint_resolved = _REGION_ENDPOINTS[region]
    else:
        _endpoint_resolved = os.environ.get(
            "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"
        )
    return _endpoint_resolved


def get_langsmith_client():
    """懒加载 LangSmith Client 单例。

    Returns:
        langsmith.Client | None：未启用、未配置 API Key 或 langsmith 包缺失时返回 None。
    """
    global _client
    if not is_tracing_enabled():
        return None
    if _client is not None:
        return _client
    api_key = os.environ.get("LANGSMITH_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "LANGSMITH_TRACING=true 但未配置 LANGSMITH_API_KEY，trace 不会上报"
        )
        return None
    try:
        from langsmith import Client
    except ImportError:
        logger.warning("未安装 langsmith 包，trace 不会上报")
        return None
    workspace_id = os.environ.get("LANGSMITH_WORKSPACE_ID", "").strip() or None
    _client = Client(
        api_key=api_key,
        api_url=_resolve_endpoint(),
        workspace_id=workspace_id,
    )
    logger.info(f"LangSmith Client 已初始化: endpoint={_resolve_endpoint()}")
    return _client


def trace_context(**kwargs):
    """包装 langsmith.tracing_context，禁用或导入失败时降级为 nullcontext。

    优先级：本函数 kwargs > 环境变量。

    用法：
        with trace_context(project_name="my-project"):
            workflow.invoke(...)
    """
    if not is_tracing_enabled():
        return contextlib.nullcontext()
    try:
        from langsmith import tracing_context
    except ImportError:
        return contextlib.nullcontext()
    client = get_langsmith_client()
    defaults = {
        "client": client,
        "project_name": os.environ.get("LANGSMITH_PROJECT", "claimcraft-creative"),
        "enabled": True,
    }
    defaults.update(kwargs)
    return tracing_context(**defaults)


def should_sample() -> bool:
    """程序化采样：基于 LANGSMITH_SAMPLING_RATE（0.0-1.0）。

    Returns:
        True 表示本次调用应上报 trace；False 表示跳过。
        tracing 未启用时恒返回 False。
    """
    if not is_tracing_enabled():
        return False
    try:
        rate = float(os.environ.get("LANGSMITH_SAMPLING_RATE", "1"))
    except ValueError:
        return True
    # 边界保护：超出 [0, 1] 范围按 1 处理（全量采样）
    if rate >= 1:
        return True
    if rate <= 0:
        return False
    return random.random() < rate


@contextlib.contextmanager
def trace_for_case(case_id, owner_id, *, case_type=None, has_sensitive=False):
    """按 case 注入 LangSmith 追踪上下文。

    三级处理：
    - tracing 未启用 → 直接 yield（no-op，业务无感知）
    - has_sensitive=True → tracing_context(enabled=False)（敏感证据零数据保留，
      符合合规要求；tracing_context(enabled=...) 优先级最高，覆盖全局配置）
    - 默认 → 按 case_type 路由 project_name + 注入 metadata/tags 便于 UI 筛选

    Args:
        case_id: 案件 ID（注入到 metadata + tags）
        owner_id: 案件归属用户 ID（注入到 metadata）
        case_type: 案件类型（如 "refund"；用于 project_name 路由 + tags）
        has_sensitive: 是否含敏感证据；True 时禁用 trace

    用法：
        with trace_for_case(case.id, case.owner_id,
                           case_type=case.case_type, has_sensitive=has_s):
            result = async_to_sync(workflow.ainvoke)(initial_state, config)
    """
    if not is_tracing_enabled():
        yield
        return

    if has_sensitive:
        # 敏感证据：禁用 trace（tracing_context(enabled=False) 优先级最高）
        with trace_context(enabled=False):
            yield
        return

    project = os.environ.get("LANGSMITH_PROJECT", "claimcraft-creative")
    if case_type:
        project = f"{project}-{case_type}"  # 按类型路由到子项目

    with trace_context(
        enabled=True,
        project_name=project,
        metadata={
            "case_id": case_id,
            "owner_id": owner_id,
            "case_type": case_type or "unknown",
        },
        tags=[f"case-{case_id}", case_type or "unknown"],
    ):
        yield
