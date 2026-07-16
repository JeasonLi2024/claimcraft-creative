# -*- coding: utf-8 -*-
"""清理过期 SSE 事件（sse_event_depot 表，Postgres）。

用法：
    python manage.py cleanup_sse_events              # 清理 24h 前事件（默认）
    python manage.py cleanup_sse_events --hours=48   # 清理 48h 前事件
    python manage.py cleanup_sse_events --dry-run    # 仅预览数量

部署：cron 每小时运行（SSE_EVENT_DEPOT_TTL_HOURS 环境变量可调保留期）。
注意：本命令连接 Postgres（checkpointer DB），非 MySQL default DB。
"""
import os

from django.core.management.base import BaseCommand
from psycopg.rows import tuple_row

from api.agents.graph import _get_connection_pool


class Command(BaseCommand):
    help = '清理超过指定小时数的 SSE 事件（sse_event_depot 表，Postgres）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=None,
            help='保留最近 N 小时事件（默认读取 SSE_EVENT_DEPOT_TTL_HOURS=24）',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只显示将清理的数量，不执行删除',
        )

    def handle(self, *args, **options):
        # 优先命令行参数，其次环境变量，默认 24 小时
        ttl_hours = options['hours']
        if ttl_hours is None:
            ttl_hours = int(os.environ.get('SSE_EVENT_DEPOT_TTL_HOURS', '24'))
        dry_run = options['dry_run']

        pool = _get_connection_pool()

        with pool.connection() as conn:
            with conn.cursor(row_factory=tuple_row) as cur:
                # 先统计将清理的数量
                cur.execute(
                    "SELECT COUNT(*) FROM sse_event_depot "
                    "WHERE created_at < NOW() - INTERVAL '%s hours'",
                    (ttl_hours,)
                )
                will_delete = cur.fetchone()[0]

                if dry_run:
                    self.stdout.write(self.style.WARNING(
                        f'[DRY-RUN] 将清理 {will_delete} 条过期 SSE 事件（>{ttl_hours}h）'
                    ))
                    conn.rollback()
                    return

                cur.execute(
                    "DELETE FROM sse_event_depot "
                    "WHERE created_at < NOW() - INTERVAL '%s hours'",
                    (ttl_hours,)
                )
                deleted = cur.rowcount
            conn.commit()

        self.stdout.write(self.style.SUCCESS(
            f'已清理 {deleted} 条过期 SSE 事件（>{ttl_hours}h）'
        ))
