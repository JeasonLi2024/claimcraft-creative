# -*- coding: utf-8 -*-
"""用户偏好持久化服务（基于 LangGraph Store 跨运行共享）。

对齐 `langgraph-persistence` skill：节点通过 `runtime.store` 访问 Store，
不直接引用 store 实例。本服务封装三类原子操作（save / get / get_all），
供 review_node / stage_gate_node 在 resume 时记录用户介入策略、
供 WorkflowRunner.run_and_persist 在启动时读取偏好注入 run_options。

namespace 规则（对齐 spec.md Requirement: LangGraph Store Node Access Pattern）：
- `("user", user_id, "preferences")`：用户偏好（介入策略 / 默认模板类型等）

降级策略：Store 不可用时所有操作静默失败（try/except），不阻塞主流程。
"""
from datetime import datetime, timezone
from typing import Any, Optional

from langgraph.runtime import Runtime


def save_user_preference(runtime: Runtime, user_id: str, key: str, value: Any) -> None:
    """保存用户偏好到 Store。

    Args:
        runtime: LangGraph Runtime 实例（含 .store 属性）
        user_id: 用户 ID（字符串化以兼容 namespace tuple）
        key: 偏好键（如 "last_intervention_strategy"）
        value: 偏好值（JSON 可序列化）

    Note:
        Store 不可用时静默降级，不抛异常。
    """
    if runtime is None or getattr(runtime, "store", None) is None:
        return
    try:
        runtime.store.put(
            ("user", str(user_id), "preferences"),
            key,
            {
                "value": value,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        pass


def get_user_preference(runtime: Runtime, user_id: str, key: str) -> Optional[Any]:
    """读取用户偏好。

    Args:
        runtime: LangGraph Runtime 实例（含 .store 属性）
        user_id: 用户 ID
        key: 偏好键

    Returns:
        偏好值；不存在或 Store 不可用时返回 None。
    """
    if runtime is None or getattr(runtime, "store", None) is None:
        return None
    try:
        item = runtime.store.get(("user", str(user_id), "preferences"), key)
        if item is None:
            return None
        value = getattr(item, "value", None)
        if isinstance(value, dict):
            return value.get("value")
        return value
    except Exception:
        return None


def get_user_preferences_all(runtime: Runtime, user_id: str) -> dict:
    """读取用户所有偏好（用于 WorkflowRunner 启动时注入 run_options）。

    Args:
        runtime: LangGraph Runtime 实例（含 .store 属性）
        user_id: 用户 ID

    Returns:
        {key: value} dict；Store 不可用时返回空 dict。
    """
    if runtime is None or getattr(runtime, "store", None) is None:
        return {}
    try:
        items = runtime.store.search(("user", str(user_id), "preferences"))
        result: dict = {}
        for item in items:
            value = getattr(item, "value", None)
            if isinstance(value, dict):
                result[getattr(item, "key", "")] = value.get("value")
            else:
                result[getattr(item, "key", "")] = value
        return result
    except Exception:
        return {}


class _RuntimeStub:
    """轻量 Runtime 桩，用于在不进入 graph 上下文时访问 store。

    WorkflowRunner.run_and_persist 在首次启动分支需要读取用户偏好，
    但此时不在节点执行上下文中（无 runtime 注入），通过此桩包装
    `graph.py._get_store()` 单例即可复用 user_preference_service 的 API。
    """

    def __init__(self, store) -> None:
        self.store = store
