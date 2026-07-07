# -*- coding: utf-8 -*-
"""SSE 事件保留站：基于 Postgres 表 sse_event_depot 的持久化层。

参考 spec 第 5.1 节。采用生产者-消费者解耦模式：
- 生产者（WorkflowRunner）每次产生输出立即 persist 并 notify
- 消费者（SSE 端点）从 EventDepot 读取事件推送给前端，支持断连续传

实现风格与 graph.py 一致：sync ConnectionPool + sync_to_async 桥接。

表结构：
    CREATE TABLE sse_event_depot (
        id BIGSERIAL PRIMARY KEY,
        thread_id VARCHAR(100) NOT NULL,
        event_id BIGINT NOT NULL,
        event_type VARCHAR(50) NOT NULL,
        payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(thread_id, event_id)
    );

event_id 分配：每个 thread_id 独立计数器（从 1 开始），
通过 SELECT ... FOR UPDATE 行锁保证并发安全（同一 thread_id 串行化）。
"""
import logging
import threading
from typing import Any

from asgiref.sync import sync_to_async
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from api.agents.graph import _get_connection_pool

logger = logging.getLogger(__name__)


class EventDepot:
    """SSE 事件保留站：持久化事件 + 支持断连续传。

    首次实例化时自动建表（CREATE TABLE IF NOT EXISTS，幂等）。
    所有 async 方法内部用 sync_to_async 包装 sync ConnectionPool 操作。
    """

    _setup_done: bool = False
    _setup_lock = threading.Lock()

    def __init__(self, pool: ConnectionPool | None = None):
        self.pool = pool or _get_connection_pool()
        self.setup()  # 首次调用建表（幂等）

    def setup(self) -> None:
        """建表（幂等）。首次调用执行 CREATE TABLE IF NOT EXISTS。

        与 PostgresSaver.setup() 模式一致，避免 Django migration 跨库冲突
        （sse_event_depot 表在 Postgres，Django migration 跑在 MySQL）。
        """
        if EventDepot._setup_done:
            return
        with EventDepot._setup_lock:
            if EventDepot._setup_done:
                return
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS sse_event_depot (
                            id BIGSERIAL PRIMARY KEY,
                            thread_id VARCHAR(100) NOT NULL,
                            event_id BIGINT NOT NULL,
                            event_type VARCHAR(50) NOT NULL,
                            payload JSONB NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE(thread_id, event_id)
                        )
                    """)
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_depot_thread_event "
                        "ON sse_event_depot(thread_id, event_id)"
                    )
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_depot_created "
                        "ON sse_event_depot(created_at)"
                    )
                conn.commit()
            EventDepot._setup_done = True
            logger.info("sse_event_depot 表已就绪（CREATE TABLE IF NOT EXISTS）")

    async def persist(self, thread_id: str, event_type: str, payload: dict) -> int:
        """持久化事件，返回分配的 event_id。

        通过 SELECT ... FOR UPDATE 行锁串行化同一 thread_id 的事件分配。
        注意：首个事件（无既有行）时 FOR UPDATE 不锁行，依赖 UNIQUE 约束兜底。

        Args:
            thread_id: 工作流线程 ID
            event_type: SSE 事件类型（如 "node.start" / "workflow.complete"）
            payload: 事件数据 dict（JSONB 序列化）

        Returns:
            分配的 event_id（从 1 开始递增）
        """

        def _persist_sync() -> int:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    # 行锁分配 event_id（同一 thread_id 串行化）
                    cur.execute(
                        "SELECT COALESCE(MAX(event_id),0)+1 FROM sse_event_depot "
                        "WHERE thread_id=%s FOR UPDATE",
                        (thread_id,)
                    )
                    event_id = cur.fetchone()[0]
                    cur.execute(
                        "INSERT INTO sse_event_depot "
                        "(thread_id, event_id, event_type, payload) "
                        "VALUES (%s, %s, %s, %s)",
                        (thread_id, event_id, event_type, Json(payload))
                    )
                conn.commit()  # 提交事务，释放行锁
                return event_id

        return await sync_to_async(_persist_sync)()

    async def get_events_after(self, thread_id: str, last_event_id: int) -> list:
        """获取 event_id > last_event_id 的所有事件（断连续传）。

        Args:
            thread_id: 工作流线程 ID
            last_event_id: 上次收到的事件 ID（0 表示从头开始）

        Returns:
            事件 dict 列表，每项含 event_id / event_type / payload / created_at
        """

        def _get_sync() -> list:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT event_id, event_type, payload, created_at "
                        "FROM sse_event_depot "
                        "WHERE thread_id=%s AND event_id > %s "
                        "ORDER BY event_id ASC",
                        (thread_id, last_event_id)
                    )
                    rows = cur.fetchall()
                conn.rollback()  # 只读操作，回滚释放连接
                return [
                    {
                        "event_id": r[0],
                        "event_type": r[1],
                        "payload": r[2],
                        "created_at": r[3].isoformat() if r[3] else None,
                    }
                    for r in rows
                ]

        return await sync_to_async(_get_sync)()

    async def is_workflow_completed(self, thread_id: str) -> bool:
        """检查工作流是否已完成（有 workflow.complete 或 workflow.error 事件）。"""

        def _check_sync() -> bool:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM sse_event_depot "
                        "WHERE thread_id=%s "
                        "AND event_type IN ('workflow.complete','workflow.error') "
                        "LIMIT 1",
                        (thread_id,)
                    )
                    return cur.fetchone() is not None

        return await sync_to_async(_check_sync)()

    async def get_all_events(self, thread_id: str) -> list:
        """获取 thread_id 的全部事件（测试用）。"""

        def _get_all_sync() -> list:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT event_id, event_type, payload, created_at "
                        "FROM sse_event_depot WHERE thread_id=%s "
                        "ORDER BY event_id ASC",
                        (thread_id,)
                    )
                    rows = cur.fetchall()
                conn.rollback()
                return [
                    {
                        "event_id": r[0],
                        "event_type": r[1],
                        "payload": r[2],
                        "created_at": r[3].isoformat() if r[3] else None,
                    }
                    for r in rows
                ]

        return await sync_to_async(_get_all_sync)()

    async def cleanup_old_events(self, ttl_hours: int = 24) -> int:
        """清理超过 ttl_hours 的小时数前的事件。

        Args:
            ttl_hours: 保留最近 N 小时的事件

        Returns:
            删除的行数
        """

        def _cleanup_sync() -> int:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM sse_event_depot "
                        "WHERE created_at < NOW() - INTERVAL '%s hours'",
                        (ttl_hours,)
                    )
                    deleted = cur.rowcount
                conn.commit()
                return deleted

        return await sync_to_async(_cleanup_sync)()
