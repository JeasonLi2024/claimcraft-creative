# -*- coding: utf-8 -*-
"""Task 5.2.6 测试：State Schema 版本化与迁移。

覆盖 6 个场景（对齐 spec.md Requirement: State Schema Versioning & Migration）：
1. v1→v2 迁移成功（mock 注册表）
2. v1→v3 链式迁移（v1→v2→v3，mock 注册表）
3. 迁移失败（MigrationError）：缺少迁移函数 / 迁移函数抛异常
4. 不可迁移：state_schema_version > STATE_SCHEMA_VERSION（来自未来版本）
5. _mark_artifacts_readonly 标记产物只读（metadata.readonly=True）
6. migrate_state_v1_to_v2 占位函数返回 state 不变

测试策略：
- 纯函数测试（migrate_state / migrate_state_v1_to_v2）使用 SimpleTestCase
- 使用 unittest.mock.patch.dict 临时注入 MIGRATION_REGISTRY mock 条目
- _mark_artifacts_readonly 测试使用 TransactionTestCase（DB-backed）
- 不依赖真实 LangGraph checkpoint，仅测试迁移逻辑与产物标记

运行方式：
    cd backend
    python manage.py test api.tests.test_state_migration -v 2
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TransactionTestCase

from api.agents.version import (
    MIGRATION_REGISTRY,
    MigrationError,
    WorkflowVersion,
    migrate_state,
    migrate_state_v1_to_v2,
)
from api.models import Case, WorkflowArtifact, WorkflowRun


# ============================================================================
# 辅助函数
# ============================================================================


def asyncio_run(coro):
    """同步运行 async 函数（兼容 TransactionTestCase 的同步上下文）。"""
    import asyncio
    return asyncio.run(coro)


def _make_case(user=None, **kwargs):
    """创建一个最小 Case。"""
    return Case.objects.create(
        title=kwargs.pop("title", "测试案件-迁移"),
        owner=user,
        **kwargs,
    )


def _make_run(case, **kwargs):
    """创建一个 WorkflowRun。"""
    defaults = {
        "status": "running",
        "current_stage": "document_generation",
        "current_node": "complaint",
        "progress": 0.50,
        "revision": 1,
    }
    defaults.update(kwargs)
    return WorkflowRun.objects.create(case=case, **defaults)


def _make_artifact(run, case, **kwargs):
    """创建一个 WorkflowArtifact。"""
    defaults = {
        "artifact_type": "complaint_draft",
        "stage": "document_generation",
        "content": {"title": "测试文书"},
        "metadata": {},
    }
    defaults.update(kwargs)
    return WorkflowArtifact.objects.create(
        workflow_run=run, case=case, **defaults,
    )


# ============================================================================
# 场景 1+6：migrate_state_v1_to_v2 占位函数 + 同版本无迁移
# ============================================================================


class MigrateStateV1ToV2StubTests(SimpleTestCase):
    """场景 6：migrate_state_v1_to_v2 占位函数（STATE_SCHEMA_VERSION=1）。"""

    def test_migrate_state_v1_to_v2_returns_state_unchanged(self):
        """占位函数直接返回 old_state 不变（当前 STATE_SCHEMA_VERSION=1）。"""
        old_state = {
            "case_id": 100,
            "evidence_chain": [],
            "state_schema_version": 1,
        }
        new_state = migrate_state_v1_to_v2(old_state)
        self.assertIs(new_state, old_state)
        self.assertEqual(new_state["case_id"], 100)

    def test_migrate_state_noop_when_versions_equal(self):
        """from_version == to_version 时直接返回 old_state 不做迁移。"""
        old_state = {"case_id": 200, "state_schema_version": 1}
        result = migrate_state(old_state, from_version=1, to_version=1)
        self.assertIs(result, old_state)

    def test_migration_registry_empty_when_state_schema_version_is_1(self):
        """STATE_SCHEMA_VERSION=1 时 MIGRATION_REGISTRY 为空（无已注册迁移）。"""
        self.assertEqual(WorkflowVersion.STATE_SCHEMA_VERSION, 1)
        self.assertEqual(MIGRATION_REGISTRY, {})


# ============================================================================
# 场景 1：v1→v2 迁移成功（mock 注册表）
# ============================================================================


class MigrateStateV1ToV2SuccessTests(SimpleTestCase):
    """场景 1：v1→v2 迁移成功（通过 mock 注册表模拟）。"""

    def test_migrate_state_v1_to_v2_success_with_mock_registry(self):
        """注册 v1→v2 迁移函数后，migrate_state 正确应用迁移。"""

        def mock_v1_to_v2(state):
            new_state = dict(state)
            new_state["state_schema_version"] = 2
            new_state["new_field_in_v2"] = "migrated_value"
            return new_state

        old_state = {"case_id": 300, "state_schema_version": 1}
        with patch.dict(
            "api.agents.version.MIGRATION_REGISTRY", {1: mock_v1_to_v2}
        ):
            result = migrate_state(old_state, from_version=1, to_version=2)

        self.assertEqual(result["state_schema_version"], 2)
        self.assertEqual(result["new_field_in_v2"], "migrated_value")
        self.assertEqual(result["case_id"], 300)


# ============================================================================
# 场景 2：v1→v3 链式迁移（v1→v2→v3）
# ============================================================================


class MigrateStateChainTests(SimpleTestCase):
    """场景 2：v1→v3 链式迁移（依次应用 v1→v2 与 v2→v3）。"""

    def test_migrate_state_chain_v1_to_v3(self):
        """注册 v1→v2 和 v2→v3 后，migrate_state 链式应用两个迁移。"""
        call_order = []

        def mock_v1_to_v2(state):
            call_order.append("v1_to_v2")
            new_state = dict(state)
            new_state["state_schema_version"] = 2
            new_state["v2_field"] = "from_v2"
            return new_state

        def mock_v2_to_v3(state):
            call_order.append("v2_to_v3")
            new_state = dict(state)
            new_state["state_schema_version"] = 3
            new_state["v3_field"] = "from_v3"
            # v3 应同时看到 v2 添加的字段
            assert state.get("v2_field") == "from_v2"
            return new_state

        old_state = {"case_id": 400, "state_schema_version": 1}
        with patch.dict(
            "api.agents.version.MIGRATION_REGISTRY",
            {1: mock_v1_to_v2, 2: mock_v2_to_v3},
        ):
            result = migrate_state(old_state, from_version=1, to_version=3)

        # 链式调用顺序正确
        self.assertEqual(call_order, ["v1_to_v2", "v2_to_v3"])
        # 最终版本为 3
        self.assertEqual(result["state_schema_version"], 3)
        # v2 和 v3 字段都存在
        self.assertEqual(result["v2_field"], "from_v2")
        self.assertEqual(result["v3_field"], "from_v3")
        # 原始字段保留
        self.assertEqual(result["case_id"], 400)


# ============================================================================
# 场景 3：迁移失败（MigrationError）
# ============================================================================


class MigrateStateFailureTests(SimpleTestCase):
    """场景 3：迁移失败场景。"""

    def test_migrate_state_raises_on_missing_migration_function(self):
        """缺少 v1→v2 迁移函数时抛 MigrationError。"""
        old_state = {"case_id": 500, "state_schema_version": 1}
        # MIGRATION_REGISTRY 为空（未注册 v1→v2）
        with patch.dict("api.agents.version.MIGRATION_REGISTRY", {}, clear=True):
            with self.assertRaises(MigrationError) as ctx:
                migrate_state(old_state, from_version=1, to_version=2)
        self.assertIn("缺少 v1 → v2 迁移函数", str(ctx.exception))

    def test_migrate_state_raises_on_missing_intermediate_function(self):
        """链式迁移中缺少中间迁移函数时抛 MigrationError。"""
        old_state = {"case_id": 501, "state_schema_version": 1}

        def mock_v1_to_v2(state):
            new_state = dict(state)
            new_state["state_schema_version"] = 2
            return new_state

        # 只注册 v1→v2，未注册 v2→v3
        with patch.dict(
            "api.agents.version.MIGRATION_REGISTRY", {1: mock_v1_to_v2}
        ):
            with self.assertRaises(MigrationError) as ctx:
                migrate_state(old_state, from_version=1, to_version=3)
        self.assertIn("缺少 v2 → v3 迁移函数", str(ctx.exception))

    def test_migrate_state_wraps_migration_function_exception(self):
        """迁移函数抛出普通异常时包装为 MigrationError。"""
        def failing_migration(state):
            raise ValueError("模拟迁移失败：字段格式不兼容")

        old_state = {"case_id": 502, "state_schema_version": 1}
        with patch.dict(
            "api.agents.version.MIGRATION_REGISTRY", {1: failing_migration}
        ):
            with self.assertRaises(MigrationError) as ctx:
                migrate_state(old_state, from_version=1, to_version=2)
        self.assertIn("v1 → v2 迁移失败", str(ctx.exception))
        self.assertIn("字段格式不兼容", str(ctx.exception))

    def test_migrate_state_reraises_migration_error_from_function(self):
        """迁移函数直接抛 MigrationError 时不二次包装。"""
        def raising_migration(state):
            raise MigrationError("自定义迁移错误")

        old_state = {"case_id": 503, "state_schema_version": 1}
        with patch.dict(
            "api.agents.version.MIGRATION_REGISTRY", {1: raising_migration}
        ):
            with self.assertRaises(MigrationError) as ctx:
                migrate_state(old_state, from_version=1, to_version=2)
        self.assertEqual(str(ctx.exception), "自定义迁移错误")


# ============================================================================
# 场景 4：不可迁移（来自未来版本，from > to）
# ============================================================================


class MigrateStateFutureVersionTests(SimpleTestCase):
    """场景 4：state_schema_version > STATE_SCHEMA_VERSION（来自未来版本）。"""

    def test_migrate_state_raises_on_future_version(self):
        """from_version > to_version 时抛 MigrationError（未来版本不可降级）。"""
        old_state = {"case_id": 600, "state_schema_version": 5}
        with self.assertRaises(MigrationError) as ctx:
            migrate_state(old_state, from_version=5, to_version=1)
        self.assertIn("不支持降级迁移", str(ctx.exception))
        self.assertIn("from_version=5", str(ctx.exception))
        self.assertIn("to_version=1", str(ctx.exception))

    def test_migrate_state_future_version_with_current_version(self):
        """旧 checkpoint 版本 99 → 当前版本 1 抛 MigrationError。"""
        old_state = {"case_id": 601, "state_schema_version": 99}
        current = WorkflowVersion.STATE_SCHEMA_VERSION
        with self.assertRaises(MigrationError) as ctx:
            migrate_state(old_state, from_version=99, to_version=current)
        self.assertIn("未来版本", str(ctx.exception))


# ============================================================================
# 场景 5：_mark_artifacts_readonly 标记产物只读
# ============================================================================


class MarkArtifactsReadonlyTests(TransactionTestCase):
    """场景 5：_mark_artifacts_readonly 将产物 metadata 标记为只读。"""

    def setUp(self):
        """创建测试数据：User + Case + WorkflowRun + 2 个 WorkflowArtifact。"""
        from api.agents.workflow_runner import _mark_artifacts_readonly
        self._mark_artifacts_readonly = _mark_artifacts_readonly
        self.user = User.objects.create_user(
            username="testuser", password="testpass"
        )
        self.case = _make_case(self.user)
        self.run = _make_run(self.case)
        # 创建 2 个产物（不同类型）
        self.artifact1 = _make_artifact(
            self.run, self.case,
            artifact_type="complaint_draft",
            content={"title": "投诉书"},
            metadata={"custom_key": "custom_value"},
        )
        self.artifact2 = _make_artifact(
            self.run, self.case,
            artifact_type="evidence_chain",
            content={"nodes": []},
            metadata={},
        )

    def test_mark_artifacts_readonly_sets_metadata_flag(self):
        """_mark_artifacts_readonly 在所有产物 metadata 中写入 readonly=True。"""
        marked_count = asyncio_run(self._mark_artifacts_readonly(self.run.id))

        self.assertEqual(marked_count, 2)
        # 刷新 DB
        self.artifact1.refresh_from_db()
        self.artifact2.refresh_from_db()
        self.assertTrue(self.artifact1.metadata.get("readonly"))
        self.assertTrue(self.artifact2.metadata.get("readonly"))
        self.assertEqual(
            self.artifact1.metadata.get("readonly_reason"),
            "state_schema_migration_failed",
        )
        self.assertEqual(
            self.artifact2.metadata.get("readonly_reason"),
            "state_schema_migration_failed",
        )

    def test_mark_artifacts_readonly_preserves_existing_metadata(self):
        """_mark_artifacts_readonly 保留 metadata 中已有的键。"""
        asyncio_run(self._mark_artifacts_readonly(self.run.id))

        self.artifact1.refresh_from_db()
        # 原有 custom_key 保留
        self.assertEqual(
            self.artifact1.metadata.get("custom_key"), "custom_value"
        )
        # 新增 readonly + readonly_reason
        self.assertTrue(self.artifact1.metadata.get("readonly"))
        self.assertEqual(
            self.artifact1.metadata.get("readonly_reason"),
            "state_schema_migration_failed",
        )

    def test_mark_artifacts_readonly_returns_zero_for_no_artifacts(self):
        """没有产物的 WorkflowRun 返回 0。"""
        empty_run = _make_run(self.case, revision=2)
        marked_count = asyncio_run(self._mark_artifacts_readonly(empty_run.id))
        self.assertEqual(marked_count, 0)

    def test_mark_artifacts_readonly_only_affects_target_run(self):
        """_mark_artifacts_readonly 仅影响指定 run 的产物，不影响其他 run。"""
        other_run = _make_run(self.case, revision=3)
        other_artifact = _make_artifact(
            other_run, self.case,
            artifact_type="complaint_draft",
            metadata={},
        )

        # 仅标记 self.run 的产物
        asyncio_run(self._mark_artifacts_readonly(self.run.id))

        other_artifact.refresh_from_db()
        # other_run 的产物未被标记
        self.assertFalse(other_artifact.metadata.get("readonly"))
