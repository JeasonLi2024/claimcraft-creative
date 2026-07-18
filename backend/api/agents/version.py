# -*- coding: utf-8 -*-
"""工作流版本常量与 State Schema 迁移。

用于 initial state 注入和审计追溯：
- WORKFLOW_VERSION：工作流主版本（变更时影响图结构或路由）
- STATE_SCHEMA_VERSION：CaseWorkflowState TypedDict 版本（字段变更时递增）
- POLICY_VERSION：质量门/降级策略版本
- PROMPT_BUNDLE_VERSION：Prompt bundle 版本（prompt 修改时递增）

注入位置：build_case_workflow() 在 graph 编译时，将版本常量作为 initial state 的一部分
通过 WorkflowRunner.start_in_background(initial_state={...}) 注入。

Task 5.2 State Schema 版本化与迁移（对齐 `langgraph-persistence` skill）：
- MigrationError：迁移失败异常（缺函数 / 未来版本降级 / 迁移函数抛异常）
- migrate_state_v1_to_v2：v1→v2 迁移函数（当前为占位，STATE_SCHEMA_VERSION=1）
- MIGRATION_REGISTRY：{from_version: migration_function} 注册表
- migrate_state：链式迁移入口（v1→v2→v3... 逐版本应用）
"""
from typing import Callable


class WorkflowVersion:
    """工作流版本常量（用于审计与兼容性检测）。"""
    WORKFLOW_VERSION = "v11"
    STATE_SCHEMA_VERSION = 1
    POLICY_VERSION = "v1"
    PROMPT_BUNDLE_VERSION = "2026.07"

    @classmethod
    def to_initial_state(cls) -> dict:
        """返回需要注入到 CaseWorkflowState 的版本字段 dict。"""
        return {
            "workflow_version": cls.WORKFLOW_VERSION,
            "state_schema_version": cls.STATE_SCHEMA_VERSION,
            "policy_version": cls.POLICY_VERSION,
            "prompt_bundle_version": cls.PROMPT_BUNDLE_VERSION,
        }


# ============================================================================
# Task 5.2.4：MigrationError 异常类
# ============================================================================


class MigrationError(Exception):
    """State schema 迁移失败异常。

    触发场景：
    - 缺少必要的迁移函数（MIGRATION_REGISTRY 未注册对应版本）
    - 旧 state 版本高于当前 STATE_SCHEMA_VERSION（来自未来版本，不可降级）
    - 迁移函数执行时抛出异常

    使用方：WorkflowRunner.resume() 捕获此异常后保留旧 WorkflowArtifact 为只读，
    返回提示「此运行基于旧版本，建议重新发起」。
    """


# ============================================================================
# Task 5.2.1：migrate_state_v1_to_v2 迁移函数（预留）
# ============================================================================


def migrate_state_v1_to_v2(old_state: dict) -> dict:
    """v1 → v2 state schema 迁移函数（预留占位）。

    当前 STATE_SCHEMA_VERSION=1，本函数为占位实现，函数体直接返回 old_state 不变。

    当 CaseWorkflowState 引入破坏性字段变更时：
    1. 递增 WorkflowVersion.STATE_SCHEMA_VERSION 至 2
    2. 在此函数中实现实际的字段重命名 / 默认值填充 / 结构调整
    3. 在 MIGRATION_REGISTRY 注册 ``{1: migrate_state_v1_to_v2}``

    Args:
        old_state: v1 版本的 state dict

    Returns:
        v2 版本的 state dict（当前等同 old_state）
    """
    return old_state


# ============================================================================
# Task 5.2.2：MIGRATION_REGISTRY + migrate_state 链式迁移入口
# ============================================================================


# 迁移注册表：{from_version: migration_function}
# - migration_function 签名：(old_state: dict) -> new_state: dict
# - 链式迁移通过逐版本应用实现（v1→v2→v3...）
# - key 表示「源版本」，函数将 state 从该版本迁移到下一版本
MIGRATION_REGISTRY: dict[int, Callable[[dict], dict]] = {
    # 当前 STATE_SCHEMA_VERSION=1，无已注册迁移
    # 当 STATE_SCHEMA_VERSION 升至 2 时：{1: migrate_state_v1_to_v2}
}


def migrate_state(old_state: dict, from_version: int, to_version: int) -> dict:
    """链式迁移 state schema 版本。

    从 ``from_version`` 逐版本应用迁移函数至 ``to_version``。
    例如 ``from=1, to=3`` 时依次应用 v1→v2 与 v2→v3。

    Args:
        old_state: 旧版本 state dict
        from_version: 旧 state 的 schema 版本
        to_version: 目标 schema 版本（通常为当前 STATE_SCHEMA_VERSION）

    Returns:
        迁移后的新版本 state dict

    Raises:
        MigrationError:
            - ``from_version > to_version``（未来版本不可降级）
            - 缺少必要的迁移函数（MIGRATION_REGISTRY 未注册）
            - 迁移函数执行抛出异常
    """
    if from_version == to_version:
        return old_state

    if from_version > to_version:
        raise MigrationError(
            f"不支持降级迁移：from_version={from_version} > to_version={to_version} "
            f"(可能来自未来版本，当前 STATE_SCHEMA_VERSION={to_version})"
        )

    current_state = old_state
    current_version = from_version
    while current_version < to_version:
        migration_fn = MIGRATION_REGISTRY.get(current_version)
        if migration_fn is None:
            raise MigrationError(
                f"缺少 v{current_version} → v{current_version + 1} 迁移函数 "
                f"(MIGRATION_REGISTRY 未注册 key={current_version})"
            )
        try:
            current_state = migration_fn(current_state)
        except MigrationError:
            raise
        except Exception as e:
            raise MigrationError(
                f"v{current_version} → v{current_version + 1} 迁移失败: {e}"
            ) from e
        current_version += 1

    return current_state
