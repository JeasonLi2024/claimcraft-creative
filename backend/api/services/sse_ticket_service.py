# -*- coding: utf-8 -*-
"""SSE Ticket 一次性鉴权服务（Task 1.4.1）。

设计目标：
- 短时效（2-5 分钟）+ 单次使用（revoke 后失效）
- 绑定 run_id，仅可读取指定 WorkflowRun 的事件流
- 日志只记录 hash，不记录完整 ticket
- 防止 SSE URL 被复制后滥用

存储后端：
- 优先使用 Redis（如配置 REDIS_URL）
- 回退到内存 dict + TTL（开发环境）

TODO（Task 3.1）：当前 run_id 占位为 case_id。引入 WorkflowRun 模型后，
调用方应传入真正的 WorkflowRun.id，本服务无需改动。
"""
import hashlib
import logging
import os
import secrets
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Ticket TTL（秒），默认 3 分钟，可通过 SSE_TICKET_TTL 环境变量调整
TICKET_TTL_SECONDS = int(os.environ.get("SSE_TICKET_TTL", "180"))

# Ticket 前缀
TICKET_PREFIX = "wf_sse_"


class _InMemoryTicketStore:
    """内存存储（开发环境回退）。

    线程安全说明：依赖 GIL；put/get/pop 为单条 dict 操作，CPython 下原子。
    多进程部署请使用 Redis 后端。
    """

    def __init__(self):
        # ticket_hash -> (expire_ts, run_id, user_id)
        self._store: dict[str, tuple[int, int, int]] = {}

    def put(self, ticket_hash: str, expire_ts: int, run_id: int, user_id: int) -> None:
        self._store[ticket_hash] = (expire_ts, run_id, user_id)

    def get(self, ticket_hash: str) -> Optional[tuple[int, int, int]]:
        entry = self._store.get(ticket_hash)
        if entry is None:
            return None
        expire_ts, run_id, user_id = entry
        if time.time() > expire_ts:
            self._store.pop(ticket_hash, None)
            return None
        return entry

    def pop(self, ticket_hash: str) -> Optional[tuple[int, int, int]]:
        entry = self.get(ticket_hash)
        if entry is not None:
            self._store.pop(ticket_hash, None)
        return entry

    def cleanup_expired(self) -> int:
        """清理过期 ticket，返回清理数量。"""
        now = time.time()
        expired = [k for k, (e, _, _) in self._store.items() if now > e]
        for k in expired:
            self._store.pop(k, None)
        return len(expired)


# 全局 store 实例（首次使用时初始化）
_store: Optional[_InMemoryTicketStore] = None
_redis_client = None


def _get_store():
    """获取 store 实例（Redis 优先，回退到内存）。

    判定逻辑：如配置 REDIS_URL 且 redis 库可导入 + ping 成功 → 使用 Redis；
    否则回退到 _InMemoryTicketStore。
    """
    global _store, _redis_client
    # 已初始化 Redis 且仍可用 → 直接复用
    if _redis_client is not None:
        return _redis_client
    # 已初始化内存 store 且未配置 Redis → 直接复用
    if _store is not None:
        return _store

    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis
            _redis_client = redis.from_url(redis_url, decode_responses=True)
            _redis_client.ping()
            # 隐藏 URL 中的密码再打日志
            safe_url = redis_url.split("@")[-1] if "@" in redis_url else redis_url
            logger.info(f"SSE Ticket 使用 Redis 存储: {safe_url}")
            return _redis_client
        except Exception as e:
            logger.warning(f"Redis 连接失败，回退到内存存储: {e}")
            _redis_client = None

    if _store is None:
        _store = _InMemoryTicketStore()
        logger.info("SSE Ticket 使用内存存储（开发环境）")
    return _store


def _hash_ticket(ticket: str) -> str:
    """SHA-256 hash ticket，用于存储和日志（避免明文落日志）。"""
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def _is_redis(store) -> bool:
    """判定 store 是否为 Redis 客户端（用 setex 方法识别，内存 store 无此方法）。"""
    return hasattr(store, "setex")


def issue_ticket(run_id: int, user_id: int) -> str:
    """签发一次性 SSE Ticket。

    Args:
        run_id: 绑定的 WorkflowRun ID（Task 3.1 前占位为 case_id）
        user_id: 签发用户 ID

    Returns:
        ticket_str: 完整 ticket 字符串（仅返回一次，调用方应安全传递给客户端）

    安全：
    - 日志只记录 hash 前 16 位
    - 存储只保存 hash，不保存明文
    """
    ticket = TICKET_PREFIX + secrets.token_urlsafe(32)
    ticket_hash = _hash_ticket(ticket)
    expire_ts = int(time.time()) + TICKET_TTL_SECONDS

    store = _get_store()
    if _is_redis(store):  # Redis
        store.setex(
            f"sse_ticket:{ticket_hash}",
            TICKET_TTL_SECONDS,
            f"{run_id}:{user_id}",
        )
    else:  # 内存
        store.put(ticket_hash, expire_ts, run_id, user_id)

    logger.info(
        f"签发 SSE Ticket: hash={ticket_hash[:16]}..., run_id={run_id}, "
        f"user_id={user_id}, ttl={TICKET_TTL_SECONDS}s"
    )
    return ticket


def validate_ticket(ticket: str, run_id: int) -> bool:
    """验证 ticket 有效性（不消耗）。

    Args:
        ticket: 完整 ticket 字符串
        run_id: 期望的 WorkflowRun ID（Task 3.1 前占位为 case_id）

    Returns:
        True 如 ticket 有效且绑定到指定 run_id；False 如 ticket 不存在、
        已过期、已撤销、前缀不符或 run_id 不匹配
    """
    if not ticket or not ticket.startswith(TICKET_PREFIX):
        return False

    ticket_hash = _hash_ticket(ticket)
    store = _get_store()

    if _is_redis(store):  # Redis
        val = store.get(f"sse_ticket:{ticket_hash}")
        if val is None:
            return False
        try:
            stored_run_id, _stored_user_id = val.split(":")
            return int(stored_run_id) == run_id
        except (ValueError, TypeError):
            return False
    else:  # 内存
        entry = store.get(ticket_hash)
        if entry is None:
            return False
        _, stored_run_id, _ = entry
        return stored_run_id == run_id


def revoke_ticket(ticket: str) -> bool:
    """撤销 ticket（一次性使用后调用）。

    Returns:
        True 如成功撤销，False 如 ticket 不存在或已过期
    """
    if not ticket:
        return False

    ticket_hash = _hash_ticket(ticket)
    store = _get_store()

    if _is_redis(store):  # Redis
        deleted = store.delete(f"sse_ticket:{ticket_hash}")
        if deleted:
            logger.info(f"撤销 SSE Ticket: hash={ticket_hash[:16]}...")
        return bool(deleted)
    else:  # 内存
        entry = store.pop(ticket_hash)
        if entry is not None:
            logger.info(f"撤销 SSE Ticket: hash={ticket_hash[:16]}...")
            return True
        return False
