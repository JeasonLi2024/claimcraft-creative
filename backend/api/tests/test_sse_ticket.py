# -*- coding: utf-8 -*-
"""Task 1.4：SSE Ticket 一次性鉴权服务测试。

测试覆盖（对齐 SubTask 1.4.1）：
1. issue_ticket 返回字符串以 "wf_sse_" 开头
2. validate_ticket 对有效 ticket + 正确 run_id 返回 True
3. validate_ticket 对错误 run_id 返回 False
4. revoke_ticket 后 validate_ticket 返回 False
5. TTL 过期后 validate_ticket 返回 False（直接测试 _InMemoryTicketStore 过期逻辑 + mock time）
6. （可选）如 Redis 可用，重复核心测试

运行方式（任选其一）：
    cd backend
    python manage.py test api.tests.test_sse_ticket -v 2
    # 或（如已安装 pytest）：
    python -m pytest api/tests/test_sse_ticket.py -v
"""
import os
import sys
import time
import unittest
from unittest.mock import patch

# 确保可从项目根目录或 backend/ 目录运行（backend/ 需在 sys.path 上以解析 claimcraft.settings）
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# 配置 Django（与其它测试保持一致；sse_ticket_service 本身不依赖 Django，
# 但放在 api/tests/ 目录下随 Django test runner 一起运行更方便）
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django  # noqa: E402
from django.apps import apps as _django_apps  # noqa: E402
if not _django_apps.ready:
    django.setup()

from api.services import sse_ticket_service  # noqa: E402
from api.services.sse_ticket_service import (  # noqa: E402
    TICKET_PREFIX,
    _InMemoryTicketStore,
    _hash_ticket,
    issue_ticket,
    revoke_ticket,
    validate_ticket,
)


def _reset_store():
    """重置全局 store，确保测试之间互不影响。

    sse_ticket_service 模块以全局变量缓存 store 实例（_store / _redis_client），
    每个 test case 的 setUp 都应调用本函数，强制下次 _get_store() 重新初始化。
    """
    sse_ticket_service._store = None
    sse_ticket_service._redis_client = None


class IssueTicketTest(unittest.TestCase):
    """测试 1：issue_ticket 返回字符串以 TICKET_PREFIX 开头。"""

    def setUp(self):
        _reset_store()

    def test_ticket_has_correct_prefix(self):
        ticket = issue_ticket(run_id=1, user_id=1)
        self.assertIsInstance(ticket, str)
        self.assertTrue(ticket.startswith(TICKET_PREFIX))

    def test_ticket_has_sufficient_entropy(self):
        """token 部分应足够长（secrets.token_urlsafe(32) ≈ 43 字符）。"""
        ticket = issue_ticket(run_id=1, user_id=1)
        # 前缀 + 至少 32 字符的随机部分
        self.assertGreater(len(ticket), len(TICKET_PREFIX) + 32)

    def test_each_call_returns_unique_ticket(self):
        """每次签发应返回不同的 ticket（极小概率重复，此处假设不冲突）。"""
        t1 = issue_ticket(run_id=1, user_id=1)
        t2 = issue_ticket(run_id=1, user_id=1)
        self.assertNotEqual(t1, t2)


class ValidateTicketCorrectRunIdTest(unittest.TestCase):
    """测试 2：validate_ticket 对有效 ticket + 正确 run_id 返回 True。"""

    def setUp(self):
        _reset_store()

    def test_valid_ticket_correct_run_id_returns_true(self):
        ticket = issue_ticket(run_id=42, user_id=7)
        self.assertTrue(validate_ticket(ticket, 42))

    def test_validate_does_not_consume_ticket(self):
        """validate_ticket 不应消耗 ticket（重复调用仍 True）。"""
        ticket = issue_ticket(run_id=42, user_id=7)
        self.assertTrue(validate_ticket(ticket, 42))
        self.assertTrue(validate_ticket(ticket, 42))
        self.assertTrue(validate_ticket(ticket, 42))


class ValidateTicketWrongRunIdTest(unittest.TestCase):
    """测试 3：validate_ticket 对错误 run_id 返回 False。"""

    def setUp(self):
        _reset_store()

    def test_wrong_run_id_returns_false(self):
        ticket = issue_ticket(run_id=42, user_id=7)
        # 不同的 run_id 应失败
        self.assertFalse(validate_ticket(ticket, 99))
        self.assertFalse(validate_ticket(ticket, 41))
        self.assertFalse(validate_ticket(ticket, 0))

    def test_wrong_prefix_returns_false(self):
        # 前缀不符直接失败
        self.assertFalse(validate_ticket("wrong_prefix_abc", 1))

    def test_empty_or_none_ticket_returns_false(self):
        self.assertFalse(validate_ticket("", 1))
        self.assertFalse(validate_ticket(None, 1))

    def test_non_existent_valid_prefix_ticket_returns_false(self):
        # 前缀正确但不存在的 ticket 应返回 False
        self.assertFalse(validate_ticket(TICKET_PREFIX + "nonexistent_token", 1))


class RevokeTicketTest(unittest.TestCase):
    """测试 4：revoke_ticket 后 validate_ticket 返回 False。"""

    def setUp(self):
        _reset_store()

    def test_validate_true_before_revoke(self):
        ticket = issue_ticket(run_id=10, user_id=1)
        # revoke 前应有效
        self.assertTrue(validate_ticket(ticket, 10))

    def test_revoke_returns_true_for_valid_ticket(self):
        ticket = issue_ticket(run_id=10, user_id=1)
        self.assertTrue(revoke_ticket(ticket))

    def test_validate_false_after_revoke(self):
        """核心用例：revoke 后 validate 返回 False（一次性使用语义）。"""
        ticket = issue_ticket(run_id=10, user_id=1)
        revoke_ticket(ticket)
        # revoke 后应失效
        self.assertFalse(validate_ticket(ticket, 10))

    def test_revoke_returns_false_for_invalid_ticket(self):
        # 不存在的 ticket revoke 应返回 False
        self.assertFalse(revoke_ticket(TICKET_PREFIX + "nonexistent"))
        self.assertFalse(revoke_ticket(""))

    def test_revoke_idempotent_second_call_returns_false(self):
        """第二次 revoke 同一 ticket 应返回 False（已被第一次撤销）。"""
        ticket = issue_ticket(run_id=10, user_id=1)
        self.assertTrue(revoke_ticket(ticket))
        # 第二次 revoke 应返回 False（已撤销）
        self.assertFalse(revoke_ticket(ticket))


class InMemoryStoreTtlExpirationTest(unittest.TestCase):
    """测试 5：TTL 过期后 validate_ticket 返回 False。

    采用两种策略：
    1. 直接测试 _InMemoryTicketStore 的过期逻辑（put 过去时间 → get 返回 None）
    2. mock time.time 模拟时间流逝，测试 issue_ticket + validate_ticket 端到端过期
    """

    def setUp(self):
        _reset_store()

    def test_expired_entry_returns_none_on_get(self):
        """_InMemoryTicketStore.get 在过期时返回 None 并清理条目。"""
        store = _InMemoryTicketStore()
        ticket_hash = "fake_hash_for_testing"
        # expire_ts 设为过去时间
        past_ts = int(time.time()) - 100
        store.put(ticket_hash, expire_ts=past_ts, run_id=1, user_id=1)
        # get 应返回 None（已过期）
        self.assertIsNone(store.get(ticket_hash))
        # 条目应被清理
        self.assertNotIn(ticket_hash, store._store)

    def test_expired_entry_pop_returns_none(self):
        """_InMemoryTicketStore.pop 在过期时返回 None 并清理条目。"""
        store = _InMemoryTicketStore()
        ticket_hash = "fake_hash_for_testing"
        past_ts = int(time.time()) - 100
        store.put(ticket_hash, expire_ts=past_ts, run_id=1, user_id=1)
        self.assertIsNone(store.pop(ticket_hash))

    def test_cleanup_expired_removes_only_expired_entries(self):
        """cleanup_expired 仅清理过期条目，保留有效条目。"""
        store = _InMemoryTicketStore()
        now = int(time.time())
        # 过期条目
        store.put("expired_hash", expire_ts=now - 100, run_id=1, user_id=1)
        # 有效条目
        store.put("valid_hash", expire_ts=now + 100, run_id=2, user_id=2)
        removed = store.cleanup_expired()
        self.assertEqual(removed, 1)
        self.assertNotIn("expired_hash", store._store)
        self.assertIn("valid_hash", store._store)

    def test_expired_ticket_validate_returns_false_via_mock_time(self):
        """端到端：签发的 ticket 在 TTL 过期后 validate 返回 False。

        通过 mock time.time 使 issue_ticket 用「过去」时间签发，
        validate 时时间已流逝到过期之后。
        """
        # 1. mock 签发时间为 t0，TTL=180s → 过期时间为 t0+180
        # 2. mock 验证时间为 t0+200 → 已过期
        base_time = 1_000_000.0
        with patch("api.services.sse_ticket_service.time.time", return_value=base_time):
            ticket = issue_ticket(run_id=1, user_id=1)
        # 此时 ticket 已签发，过期时间为 base_time + 180
        with patch("api.services.sse_ticket_service.time.time", return_value=base_time + 200):
            # ticket 应已过期
            self.assertFalse(validate_ticket(ticket, 1))

    def test_ticket_still_valid_before_ttl_via_mock_time(self):
        """对照组：TTL 未过期时 validate 返回 True。"""
        base_time = 1_000_000.0
        with patch("api.services.sse_ticket_service.time.time", return_value=base_time):
            ticket = issue_ticket(run_id=1, user_id=1)
        # 时间仅推进 100 秒（TTL=180），仍在有效期内
        with patch("api.services.sse_ticket_service.time.time", return_value=base_time + 100):
            self.assertTrue(validate_ticket(ticket, 1))


class HashTicketTest(unittest.TestCase):
    """补充测试：_hash_ticket 行为（用于确认日志不记录明文 ticket）。"""

    def test_hash_is_sha256_hex(self):
        h = _hash_ticket("wf_sse_test123")
        # SHA-256 hex 长度 = 64
        self.assertEqual(len(h), 64)
        # 同输入同输出
        self.assertEqual(h, _hash_ticket("wf_sse_test123"))

    def test_hash_different_for_different_tickets(self):
        h1 = _hash_ticket("wf_sse_aaa")
        h2 = _hash_ticket("wf_sse_bbb")
        self.assertNotEqual(h1, h2)

    def test_hash_does_not_contain_plain_ticket(self):
        """hash 不应包含明文 ticket（避免日志泄露）。"""
        ticket = "wf_sse_secret_value_12345"
        h = _hash_ticket(ticket)
        # hash 是 hex 字符串，不应包含原始 ticket 的非 hex 部分
        self.assertNotIn("wf_sse", h)
        self.assertNotIn("secret", h)


class RedisBackendTest(unittest.TestCase):
    """测试 6（可选）：如 Redis 可用，重复核心测试。

    自动跳过条件：
    - 未安装 redis 库
    - 未配置 REDIS_URL 环境变量
    - Redis 服务器不可达
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            raise unittest.SkipTest("未配置 REDIS_URL，跳过 Redis 后端测试")
        try:
            import redis  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("未安装 redis 库，跳过 Redis 后端测试")
        # 尝试实际连接
        try:
            import redis
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
        except Exception as e:
            raise unittest.SkipTest(f"Redis 不可达: {e}")

    def setUp(self):
        _reset_store()

    def test_redis_issue_validate_revoke(self):
        """Redis 后端：issue + validate + revoke 完整流程。"""
        ticket = issue_ticket(run_id=1, user_id=1)
        self.assertTrue(ticket.startswith(TICKET_PREFIX))
        self.assertTrue(validate_ticket(ticket, 1))
        self.assertTrue(revoke_ticket(ticket))
        self.assertFalse(validate_ticket(ticket, 1))

    def test_redis_wrong_run_id(self):
        """Redis 后端：错误 run_id 应失败。"""
        ticket = issue_ticket(run_id=42, user_id=1)
        try:
            self.assertFalse(validate_ticket(ticket, 99))
        finally:
            revoke_ticket(ticket)

    def test_redis_revoke_idempotent(self):
        """Redis 后端：revoke 幂等性。"""
        ticket = issue_ticket(run_id=10, user_id=1)
        self.assertTrue(revoke_ticket(ticket))
        self.assertFalse(revoke_ticket(ticket))


if __name__ == "__main__":
    unittest.main()
