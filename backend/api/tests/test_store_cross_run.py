# -*- coding: utf-8 -*-
"""Task 5.1.7 测试：LangGraph Store 跨运行记忆。

覆盖 4 个场景（对齐 spec.md Requirement: LangGraph Store Node Access Pattern）：
1. 跨运行用户偏好持久化（save_user_preference → get_user_preferences_all）
2. 案件模板缓存命中（complaint_node._get_cached_skeleton 返回缓存值）
3. 法律检索缓存命中（evidence_chain_node._get_cached_legal_result 返回缓存值）
4. 缓存失效（prompt_bundle_version 变更 / TTL 过期触发 delete + 返回 None）

测试策略：
- 使用 InMemoryStore（langgraph.store.memory）作为测试 Store
- 使用 _RuntimeStub 包装 Store 模拟 runtime.store 访问（对齐 5.1.4 实现）
- 直接测试 helper 函数（_get_cached_skeleton / _get_cached_legal_result），
  避免完整节点执行（不需要 mock LLM/RAG/DB）
- 用户偏好测试通过 user_preference_service API 直接验证跨运行持久化
- 全部使用 SimpleTestCase（无 DB 依赖）

运行方式：
    cd backend
    python manage.py test api.tests.test_store_cross_run -v 2
"""
from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase
from langgraph.store.memory import InMemoryStore

from api.services.user_preference_service import (
    _RuntimeStub,
    get_user_preference,
    get_user_preferences_all,
    save_user_preference,
)


# ============================================================================
# 辅助函数
# ============================================================================


def _make_runtime(store=None):
    """构造含 store 的 runtime 桩（同一 store 实例模拟跨运行共享）。"""
    return _RuntimeStub(store if store is not None else InMemoryStore())


# ============================================================================
# 场景 1：跨运行用户偏好持久化
# ============================================================================


class CrossRunUserPreferenceTests(SimpleTestCase):
    """场景 1：用户偏好跨运行持久化（运行 #106 写入 → 运行 #107 读取）。"""

    def test_save_and_get_user_preference_roundtrip(self):
        """保存的偏好可在后续读取中检索到（跨运行共享同一 Store）。"""
        store = InMemoryStore()
        runtime_run_106 = _make_runtime(store)

        # 模拟运行 #106：review_node resume 时记录用户介入策略
        save_user_preference(
            runtime_run_106, "user-106", "last_intervention_strategy", "critical_only"
        )

        # 模拟运行 #107：WorkflowRunner 启动时读取该用户偏好
        runtime_run_107 = _make_runtime(store)  # 同一 store 实例
        value = get_user_preference(
            runtime_run_107, "user-106", "last_intervention_strategy"
        )

        self.assertEqual(value, "critical_only")

    def test_get_user_preferences_all_returns_all_keys(self):
        """get_user_preferences_all 返回该用户所有偏好键值对（用于注入 run_options）。"""
        store = InMemoryStore()
        runtime = _make_runtime(store)

        save_user_preference(
            runtime, "user-200", "last_intervention_strategy", "critical_only"
        )
        save_user_preference(
            runtime, "user-200", "preferred_template_type", "formal"
        )
        save_user_preference(
            runtime, "user-200", "default_case_mode", "respond"
        )

        all_prefs = get_user_preferences_all(runtime, "user-200")

        self.assertEqual(len(all_prefs), 3)
        self.assertEqual(all_prefs["last_intervention_strategy"], "critical_only")
        self.assertEqual(all_prefs["preferred_template_type"], "formal")
        self.assertEqual(all_prefs["default_case_mode"], "respond")

    def test_user_preferences_isolated_per_user(self):
        """不同用户的偏好互相隔离（namespace 含 user_id）。"""
        store = InMemoryStore()
        runtime = _make_runtime(store)

        save_user_preference(
            runtime, "user-alice", "last_intervention_strategy", "critical_only"
        )
        save_user_preference(
            runtime, "user-bob", "last_intervention_strategy", "full_review"
        )

        self.assertEqual(
            get_user_preference(
                runtime, "user-alice", "last_intervention_strategy"
            ),
            "critical_only",
        )
        self.assertEqual(
            get_user_preference(
                runtime, "user-bob", "last_intervention_strategy"
            ),
            "full_review",
        )

    def test_get_user_preference_returns_none_when_not_found(self):
        """未保存的偏好键返回 None。"""
        runtime = _make_runtime(InMemoryStore())
        self.assertIsNone(
            get_user_preference(runtime, "user-999", "nonexistent_key")
        )

    def test_save_user_preference_graceful_when_store_unavailable(self):
        """runtime.store 为 None 时 save/get 静默降级不抛异常。"""
        runtime = _RuntimeStub(None)
        # 不应抛异常
        save_user_preference(runtime, "user-1", "key", "value")
        self.assertIsNone(get_user_preference(runtime, "user-1", "key"))

    def test_get_user_preferences_all_returns_empty_when_store_unavailable(self):
        """runtime.store 为 None 时 get_user_preferences_all 返回空 dict。"""
        runtime = _RuntimeStub(None)
        self.assertEqual(get_user_preferences_all(runtime, "user-1"), {})


# ============================================================================
# 场景 2：案件模板缓存命中（complaint_node skeleton）
# ============================================================================


class ComplaintSkeletonCacheHitTests(SimpleTestCase):
    """场景 2：complaint_node 的 skeleton 缓存命中（跳过 LLM 模板生成）。"""

    def test_get_cached_skeleton_returns_cached_value_on_hit(self):
        """Store 中已有同 prompt_bundle_version 的 skeleton → 命中返回。"""
        from api.agents.nodes.complaint_node import (
            _COMPLAINT_SKELETON_KEY,
            _get_cached_skeleton,
            _templates_namespace,
        )

        store = InMemoryStore()
        runtime = _make_runtime(store)
        case_id = 500
        prompt_version = "2026.07"

        # 预填充缓存（模拟上一次运行写入）
        skeleton_payload = {
            "title": "测试投诉书骨架",
            "outline": ["当事人信息", "事实与理由", "诉求"],
            "prompt_bundle_version": prompt_version,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        store.put(
            _templates_namespace(case_id), _COMPLAINT_SKELETON_KEY, skeleton_payload
        )

        # 命中：返回缓存值，was_invalidated=False
        result, was_invalidated = _get_cached_skeleton(
            runtime, case_id, prompt_version
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "测试投诉书骨架")
        self.assertFalse(was_invalidated)

    def test_get_cached_skeleton_returns_none_on_miss(self):
        """Store 中无 skeleton → 返回 (None, False)（未命中，非失效）。"""
        from api.agents.nodes.complaint_node import _get_cached_skeleton

        runtime = _make_runtime(InMemoryStore())
        result, was_invalidated = _get_cached_skeleton(runtime, 999, "2026.07")
        self.assertIsNone(result)
        self.assertFalse(was_invalidated)

    def test_get_cached_skeleton_returns_none_when_runtime_is_none(self):
        """runtime 为 None 时降级返回 (None, False)。"""
        from api.agents.nodes.complaint_node import _get_cached_skeleton

        result, was_invalidated = _get_cached_skeleton(None, 500, "2026.07")
        self.assertIsNone(result)
        self.assertFalse(was_invalidated)


# ============================================================================
# 场景 3：法律检索缓存命中（evidence_chain_node legal_cache）
# ============================================================================


class LegalCacheHitTests(SimpleTestCase):
    """场景 3：evidence_chain_node 的法条检索缓存命中（跳过 RAG 流程）。"""

    def test_get_cached_legal_result_returns_result_on_hit(self):
        """Store 中已有未过期的法条检索结果 → 命中返回。"""
        from api.agents.nodes.evidence_chain_node import (
            _get_cached_legal_result,
            _legal_cache_key,
            _legal_cache_namespace,
        )

        store = InMemoryStore()
        runtime = _make_runtime(store)
        case_id = 700
        query = "欺诈行为 退一赔三"
        prompt_version = "2026.07"

        # 预填充缓存（未过期）
        cached_result = [
            {"law_name": "消费者权益保护法", "article_number": "第五十五条"},
        ]
        store.put(
            _legal_cache_namespace(case_id),
            _legal_cache_key(query),
            {
                "result": cached_result,
                "query": query,
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(days=7)
                ).isoformat(),
                "prompt_bundle_version": prompt_version,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # 命中：返回 result 列表，was_invalidated=False
        result, was_invalidated = _get_cached_legal_result(
            runtime, case_id, query, prompt_version
        )
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["law_name"], "消费者权益保护法")
        self.assertFalse(was_invalidated)

    def test_get_cached_legal_result_returns_none_on_miss(self):
        """Store 中无法条缓存 → 返回 (None, False)。"""
        from api.agents.nodes.evidence_chain_node import _get_cached_legal_result

        runtime = _make_runtime(InMemoryStore())
        result, was_invalidated = _get_cached_legal_result(
            runtime, 999, "无匹配查询", "2026.07"
        )
        self.assertIsNone(result)
        self.assertFalse(was_invalidated)

    def test_get_cached_legal_result_returns_none_when_runtime_is_none(self):
        """runtime 为 None 时降级返回 (None, False)。"""
        from api.agents.nodes.evidence_chain_node import _get_cached_legal_result

        result, was_invalidated = _get_cached_legal_result(
            None, 700, "任意查询", "2026.07"
        )
        self.assertIsNone(result)
        self.assertFalse(was_invalidated)

    def test_legal_cache_key_is_deterministic_for_same_query(self):
        """相同查询生成相同 cache key（sha256 哈希前 16 位）。"""
        from api.agents.nodes.evidence_chain_node import _legal_cache_key

        query = "欺诈行为 退一赔三"
        key1 = _legal_cache_key(query)
        key2 = _legal_cache_key(query)
        self.assertEqual(key1, key2)
        self.assertTrue(key1.startswith("legal_"))
        # 16 位 sha256 前缀
        self.assertEqual(len(key1), len("legal_") + 16)


# ============================================================================
# 场景 4：缓存失效（prompt_bundle_version 变更 / TTL 过期）
# ============================================================================


class CacheInvalidationTests(SimpleTestCase):
    """场景 4：缓存失效检测与清理。"""

    def test_skeleton_cache_invalidated_on_prompt_version_change(self):
        """skeleton 缓存的 prompt_bundle_version 与当前不一致 → delete + (None, True)。"""
        from api.agents.nodes.complaint_node import (
            _COMPLAINT_SKELETON_KEY,
            _get_cached_skeleton,
            _templates_namespace,
        )

        store = InMemoryStore()
        runtime = _make_runtime(store)
        case_id = 800

        # 预填充旧版本缓存
        store.put(
            _templates_namespace(case_id),
            _COMPLAINT_SKELETON_KEY,
            {
                "title": "旧骨架",
                "prompt_bundle_version": "2026.06",  # 旧版本
                "cached_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # 当前版本为 2026.07 → 缓存失效
        result, was_invalidated = _get_cached_skeleton(
            runtime, case_id, "2026.07"
        )
        self.assertIsNone(result)
        self.assertTrue(was_invalidated)

        # 验证旧条目已被 delete
        item = store.get(_templates_namespace(case_id), _COMPLAINT_SKELETON_KEY)
        self.assertIsNone(item)

    def test_legal_cache_invalidated_on_prompt_version_change(self):
        """法条缓存 prompt_bundle_version 不一致 → delete + (None, True)。"""
        from api.agents.nodes.evidence_chain_node import (
            _get_cached_legal_result,
            _legal_cache_key,
            _legal_cache_namespace,
        )

        store = InMemoryStore()
        runtime = _make_runtime(store)
        case_id = 801
        query = "过期查询"

        store.put(
            _legal_cache_namespace(case_id),
            _legal_cache_key(query),
            {
                "result": [{"law_name": "旧法条"}],
                "query": query,
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(days=7)
                ).isoformat(),
                "prompt_bundle_version": "2026.06",  # 旧版本
                "cached_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # 当前版本 2026.07 → 缓存失效
        result, was_invalidated = _get_cached_legal_result(
            runtime, case_id, query, "2026.07"
        )
        self.assertIsNone(result)
        self.assertTrue(was_invalidated)

        # 验证旧条目已被 delete
        item = store.get(_legal_cache_namespace(case_id), _legal_cache_key(query))
        self.assertIsNone(item)

    def test_legal_cache_invalidated_on_ttl_expiry(self):
        """法条缓存 expires_at 已过 → delete + (None, True)。"""
        from api.agents.nodes.evidence_chain_node import (
            _get_cached_legal_result,
            _legal_cache_key,
            _legal_cache_namespace,
        )

        store = InMemoryStore()
        runtime = _make_runtime(store)
        case_id = 802
        query = "TTL 过期查询"
        prompt_version = "2026.07"

        # expires_at 设为过去时间
        store.put(
            _legal_cache_namespace(case_id),
            _legal_cache_key(query),
            {
                "result": [{"law_name": "过期法条"}],
                "query": query,
                "expires_at": (
                    datetime.now(timezone.utc) - timedelta(days=1)
                ).isoformat(),
                "prompt_bundle_version": prompt_version,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # TTL 已过 → 缓存失效
        result, was_invalidated = _get_cached_legal_result(
            runtime, case_id, query, prompt_version
        )
        self.assertIsNone(result)
        self.assertTrue(was_invalidated)

        # 验证旧条目已被 delete
        item = store.get(_legal_cache_namespace(case_id), _legal_cache_key(query))
        self.assertIsNone(item)

    def test_skeleton_cache_survives_when_prompt_version_matches(self):
        """skeleton 缓存 prompt_bundle_version 一致 → 不失效，返回缓存值。"""
        from api.agents.nodes.complaint_node import (
            _COMPLAINT_SKELETON_KEY,
            _get_cached_skeleton,
            _templates_namespace,
        )

        store = InMemoryStore()
        runtime = _make_runtime(store)
        case_id = 803
        prompt_version = "2026.07"

        store.put(
            _templates_namespace(case_id),
            _COMPLAINT_SKELETON_KEY,
            {
                "title": "有效骨架",
                "prompt_bundle_version": prompt_version,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        result, was_invalidated = _get_cached_skeleton(
            runtime, case_id, prompt_version
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "有效骨架")
        self.assertFalse(was_invalidated)
