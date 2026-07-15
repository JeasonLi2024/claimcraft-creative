# -*- coding: utf-8 -*-
"""Postgres LISTEN/NOTIFY 封装：通知 SSE 端点有新事件。

参考 spec 第 5.2 节。实现风格与 graph.py 一致：sync ConnectionPool + sync_to_async 桥接。

通道命名：evt_{thread_id 去横线}，例如 thread_id="case-1-123" → channel="evt_case_1_123"。

工作原理：
- 生产者（WorkflowRunner）每次 persist 后调用 notify(thread_id, event_id)
- 消费者（SSE 端点）通过 subscribe(thread_id, callback) 阻塞订阅 NOTIFY
- 收到通知后从 EventDepot 拉取新事件推送给前端

注意：NOTIFY 必须在事务外或提交后发送，否则不会被投递。
LISTEN 要求 autocommit 模式（psycopg3 连接池默认非 autocommit）。
"""
import asyncio
import logging
import threading
from typing import Callable

from asgiref.sync import sync_to_async
from psycopg_pool import ConnectionPool

from api.agents.graph import _get_connection_pool

logger = logging.getLogger(__name__)


class NotifyEmitter:
    """Postgres LISTEN/NOTIFY 封装，用于 SSE 端点实时通知。"""

    def __init__(self, pool: ConnectionPool | None = None):
        self.pool = pool or _get_connection_pool()

    @staticmethod
    def _channel_name(thread_id: str) -> str:
        """生成通道名：evt_{thread_id 去横线}。

        thread_id 形如 "case-1-123"，替换 '-' 为 '_' 后为合法 SQL 标识符。
        """
        return f"evt_{thread_id.replace('-', '_')}"

    async def notify(self, thread_id: str, event_id: int) -> None:
        """发送 NOTIFY 通知订阅者有新事件。

        Args:
            thread_id: 工作流线程 ID
            event_id: 新分配的事件 ID（作为 NOTIFY payload 传递）
        """

        def _notify_sync() -> None:
            channel = self._channel_name(thread_id)
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    # NOTIFY payload 必须是字符串字面量，使用参数绑定
                    cur.execute(
                        f"NOTIFY {channel}, %s",
                        (str(event_id),)
                    )
                conn.commit()  # 提交事务，确保 NOTIFY 被投递

        await sync_to_async(_notify_sync)()

    async def subscribe(
        self,
        thread_id: str,
        callback: Callable[[int, str, str], None],
        stop_event: threading.Event | None = None,
    ) -> None:
        """阻塞订阅指定 thread_id 的 NOTIFY 通知。

        在独立线程中运行（通过 sync_to_async），回调为同步函数。
        设置 stop_event 或取消 asyncio.Task 时退出循环。

        Args:
            thread_id: 工作流线程 ID
            callback: 同步回调 (pid, channel, payload) -> None
            stop_event: 取消信号，设置时退出订阅循环（None 则创建临时 Event）

        注意：
            - LISTEN 要求 autocommit 模式
            - 使用 1 秒超时循环，定期检查 stop_event 以支持优雅取消
            - 该方法阻塞，建议用 asyncio.create_task 包装后运行
        """
        channel = self._channel_name(thread_id)
        if stop_event is None:
            stop_event = threading.Event()

        def _subscribe_sync() -> None:
            with self.pool.connection() as conn:
                conn.autocommit = True  # LISTEN 要求 autocommit
                with conn.cursor() as cur:
                    cur.execute(f"LISTEN {channel}")
                while not stop_event.is_set():
                    try:
                        # psycopg3: conn.notifies() 返回生成器，用 timeout 参数设置超时
                        # 超时后生成器会停止迭代，需重新创建
                        # 使用 1 秒超时，定期检查 stop_event 以支持优雅取消
                        gen = conn.notifiers(timeout=1.0)
                        for notify in gen:
                            if stop_event.is_set():
                                break
                            callback(notify.pid, notify.channel, notify.payload)
                        # 生成器耗尽（超时）后重新进入循环检查 stop_event
                        continue
                    except StopIteration:
                        continue
                    except Exception as e:
                        logger.warning(f"LISTEN 订阅异常 (thread={thread_id}): {e}")
                        break

        try:
            await sync_to_async(_subscribe_sync, thread_sensitive=False)()
        except asyncio.CancelledError:
            stop_event.set()
            logger.debug(f"LISTEN 订阅已取消 (thread={thread_id})")
            raise
