# -*- coding: utf-8 -*-
"""清理过期 LangGraph checkpoint（PostgresSaver 表）。

用法：
    python manage.py cleanup_checkpoints --days=30          # 清理 30 天前
    python manage.py cleanup_checkpoints --days=30 --dry-run  # 仅预览

策略：保留每 thread 最新 checkpoint（避免误删活跃 thread），删除超过 N 天的旧 checkpoint。
部署：cron 每日 02:00 运行。
"""
from django.core.management.base import BaseCommand
from psycopg.rows import tuple_row
from api.agents.graph import _get_connection_pool


class Command(BaseCommand):
    help = '清理超过指定天数的 LangGraph checkpoint（PostgresSaver 表），保留每 thread 最新'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='保留最近 N 天（默认 30）')
        parser.add_argument('--dry-run', action='store_true', help='只显示将清理的数量，不执行')

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        pool = _get_connection_pool()

        with pool.connection() as conn:
            with conn.cursor(row_factory=tuple_row) as cur:
                # 先统计将清理的数量（保留每 thread 最新 checkpoint）
                cur.execute("""
                    SELECT COUNT(*) FROM checkpoints
                    WHERE checkpoint_id NOT IN (
                        SELECT MAX(checkpoint_id) FROM checkpoints GROUP BY thread_id
                    )
                    AND created_at < NOW() - INTERVAL '%s days'
                """, (days,))
                will_delete = cur.fetchone()[0]

                if dry_run:
                    self.stdout.write(self.style.WARNING(
                        f'[DRY-RUN] 将清理 {will_delete} 条过期 checkpoint（>{days}天），'
                        f'保留每 thread 最新'
                    ))
                    return

                cur.execute("""
                    DELETE FROM checkpoints
                    WHERE checkpoint_id NOT IN (
                        SELECT MAX(checkpoint_id) FROM checkpoints GROUP BY thread_id
                    )
                    AND created_at < NOW() - INTERVAL '%s days'
                """, (days,))
                deleted = cur.rowcount

        self.stdout.write(self.style.SUCCESS(
            f'已清理 {deleted} 条过期 checkpoint（>{days}天），保留每 thread 最新'
        ))
