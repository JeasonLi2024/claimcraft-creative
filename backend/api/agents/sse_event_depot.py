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
        run_id BIGINT NULL,                 -- Task 1.3.1: WorkflowRun.id（Task 3.1 引入前为 NULL）
        revision INT NULL,                  -- Task 1.3.1: state.revision 快照
        occurred_at TIMESTAMPTZ NULL,       -- Task 1.3.1: 业务发生时间（统一信封字段）
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- 保留兼容：DB 写入时间
        UNIQUE(thread_id, event_id)
    );

event_id 分配：每个 thread_id 独立计数器（从 1 开始），
通过事务级 advisory lock 保证并发安全（同一 thread_id 串行化）。

迁移说明（Task 1.3.1）：
    对已部署的旧表，setup() 内会幂等执行 ALTER TABLE ADD COLUMN IF NOT EXISTS
    补齐 run_id / revision / occurred_at 三列。旧数据这三列为 NULL，读取兼容。
    迁移 SQL 也独立保存在 backend/api/agents/migrations/sse_event_depot_add_envelope_cols.sql
    供 DBA 手工执行。
"""
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from asgiref.sync import sync_to_async
from psycopg.rows import tuple_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from api.agents.graph import _get_connection_pool

logger = logging.getLogger(__name__)


def _parse_iso_to_dt(iso_str: str | None) -> datetime | None:
    """将 ISO 8601 字符串解析为 timezone-aware datetime（Postgres TIMESTAMPTZ 接受）。

    None 或空串返回 None（DB 列保持 NULL）。
    解析失败时记录 warning 并返回 None，避免持久化路径因时间戳格式问题中断。
    """
    if not iso_str:
        return None
    try:
        # datetime.fromisoformat 在 Python 3.11+ 支持 'Z' 后缀，3.10 及以下不支持
        # 这里手动兼容 'Z' 后缀以适配更多调用方
        s = iso_str.replace("Z", "+00:00") if iso_str.endswith("Z") else iso_str
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError) as e:
        logger.warning(f"解析 occurred_at 失败（{iso_str!r}）: {e}，DB 列将保持 NULL")
        return None


def _row_to_event_dict(r: tuple) -> dict:
    """将 SELECT 行元组转换为事件 dict（统一信封字段 + 兼容字段）。

    SELECT 列顺序：event_id, event_type, payload, run_id, revision, occurred_at, created_at
    """
    return {
        "event_id": r[0],
        "event_type": r[1],
        "payload": r[2],
        "run_id": r[3],
        "revision": r[4],
        "occurred_at": r[5].isoformat() if r[5] else None,
        "created_at": r[6].isoformat() if r[6] else None,
    }


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
                with conn.cursor(row_factory=tuple_row) as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS sse_event_depot (
                            id BIGSERIAL PRIMARY KEY,
                            thread_id VARCHAR(100) NOT NULL,
                            event_id BIGINT NOT NULL,
                            event_type VARCHAR(50) NOT NULL,
                            payload JSONB NOT NULL,
                            run_id BIGINT NULL,
                            revision INT NULL,
                            occurred_at TIMESTAMPTZ NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE(thread_id, event_id)
                        )
                    """)
                    # Task 1.3.1: 已部署旧表幂等补列（PostgreSQL 9.6+ 支持
                    # ADD COLUMN IF NOT EXISTS；若有更老版本可改用 DO 块）
                    cur.execute(
                        "ALTER TABLE sse_event_depot "
                        "ADD COLUMN IF NOT EXISTS run_id BIGINT NULL"
                    )
                    cur.execute(
                        "ALTER TABLE sse_event_depot "
                        "ADD COLUMN IF NOT EXISTS revision INT NULL"
                    )
                    cur.execute(
                        "ALTER TABLE sse_event_depot "
                        "ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ NULL"
                    )
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_depot_thread_event "
                        "ON sse_event_depot(thread_id, event_id)"
                    )
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_depot_created "
                        "ON sse_event_depot(created_at)"
                    )
                    # Task 1.3.1: 按 run_id 检索事件（用于 /workflow-runs/<run_id>/ 端点）
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_depot_run_id "
                        "ON sse_event_depot(run_id) WHERE run_id IS NOT NULL"
                    )
                conn.commit()
            EventDepot._setup_done = True
            logger.info("sse_event_depot 表已就绪（CREATE TABLE IF NOT EXISTS）")

    async def persist(
        self,
        thread_id: str,
        event_type: str,
        payload: dict,
        run_id: int | None = None,
        revision: int | None = None,
        occurred_at: str | None = None,
    ) -> int:
        """持久化事件，返回分配的 event_id。

        通过事务级 advisory lock 串行化同一 thread_id 的事件分配。

        Args:
            thread_id: 工作流线程 ID
            event_type: SSE 事件类型（如 "node.start" / "workflow.complete"）
            payload: 事件数据 dict（JSONB 序列化）
            run_id: Task 1.3.1 统一信封字段，WorkflowRun.id（Task 3.1 引入前为 None）
            revision: Task 1.3.1 统一信封字段，state.revision 快照
            occurred_at: Task 1.3.1 统一信封字段，业务发生时间（ISO 8601 字符串）
                传 None 时由 DB 列默认 NULL 表示「未提供」，前端读取时回退到 created_at。

        Returns:
            分配的 event_id（从 1 开始递增）
        """
        # TODO(Task 3.1): WorkflowRun 模型引入后，run_id 由调用方从 WorkflowRun.id 注入；
        # 目前（Task 1.3）WorkflowRunner 暂未传 run_id，列保持 NULL。

        # occurred_at 字符串 → datetime 转换（Postgres TIMESTAMPTZ 列接受 datetime）
        occurred_at_dt = _parse_iso_to_dt(occurred_at)

        def _persist_sync() -> int:
            with self.pool.connection() as conn:
                # LangGraph 要求连接池 autocommit；此处显式事务保证事件取号与插入原子完成。
                with conn.transaction():
                    with conn.cursor(row_factory=tuple_row) as cur:
                        cur.execute(
                            "SELECT pg_advisory_xact_lock(hashtext(%s))", (thread_id,)
                        )
                        cur.execute(
                            "SELECT COALESCE(MAX(event_id),0)+1 FROM sse_event_depot "
                            "WHERE thread_id=%s", (thread_id,)
                        )
                        event_id = cur.fetchone()[0]
                        cur.execute(
                            "INSERT INTO sse_event_depot "
                            "(thread_id, event_id, event_type, payload, run_id, "
                            " revision, occurred_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING event_id",
                            (
                                thread_id, event_id, event_type, Json(payload),
                                run_id, revision, occurred_at_dt,
                            ),
                        )
                        return cur.fetchone()[0]

        return await sync_to_async(_persist_sync)()

    async def get_events_after(self, thread_id: str, last_event_id: int) -> list:
        """获取 event_id > last_event_id 的所有事件（断连续传）。

        Args:
            thread_id: 工作流线程 ID
            last_event_id: 上次收到的事件 ID（0 表示从头开始）

        Returns:
            事件 dict 列表，每项含 event_id / event_type / payload / run_id /
            revision / occurred_at / created_at
        """

        def _get_sync() -> list:
            with self.pool.connection() as conn:
                with conn.cursor(row_factory=tuple_row) as cur:
                    cur.execute(
                        "SELECT event_id, event_type, payload, run_id, "
                        "       revision, occurred_at, created_at "
                        "FROM sse_event_depot "
                        "WHERE thread_id=%s AND event_id > %s "
                        "ORDER BY event_id ASC",
                        (thread_id, last_event_id)
                    )
                    rows = cur.fetchall()
                conn.rollback()  # 只读操作，回滚释放连接
                return [_row_to_event_dict(r) for r in rows]

        return await sync_to_async(_get_sync)()

    async def is_workflow_completed(self, thread_id: str) -> bool:
        """检查工作流是否已完成（有 workflow.complete 或 workflow.error 事件）。"""

        def _check_sync() -> bool:
            with self.pool.connection() as conn:
                with conn.cursor(row_factory=tuple_row) as cur:
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
                with conn.cursor(row_factory=tuple_row) as cur:
                    cur.execute(
                        "SELECT event_id, event_type, payload, run_id, "
                        "       revision, occurred_at, created_at "
                        "FROM sse_event_depot WHERE thread_id=%s "
                        "ORDER BY event_id ASC",
                        (thread_id,)
                    )
                    rows = cur.fetchall()
                conn.rollback()
                return [_row_to_event_dict(r) for r in rows]

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
                with conn.cursor(row_factory=tuple_row) as cur:
                    cur.execute(
                        "DELETE FROM sse_event_depot "
                        "WHERE created_at < NOW() - INTERVAL '%s hours'",
                        (ttl_hours,)
                    )
                    deleted = cur.rowcount
                conn.commit()
                return deleted

        return await sync_to_async(_cleanup_sync)()
