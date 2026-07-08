# -*- coding: utf-8 -*-
"""v10 法条关键词 LLM 重新生成管理命令。

为每条法条基于 content 生成独立的 keywords，替代整部法律共用 keywords 的现状。

用法：
    # 为所有法条重新生成 keywords（基于 content）
    python manage.py regenerate_keywords

    # 仅重新生成指定分类
    python manage.py regenerate_keywords --category=consumer_protection

    # 仅处理前 N 条（测试用）
    python manage.py regenerate_keywords --limit=10

    # 强制重新生成（默认跳过已使用 LLM 生成过的法条）
    python manage.py regenerate_keywords --force

    # 指定并发数（默认 8）
    python manage.py regenerate_keywords --max-concurrent=12

流程：
1. 查询待处理的 LawArticle（默认跳过已有独立 keywords 的，--force 全部重做）
2. 分块并发调用 LLM 提取关键词（默认每块 50 条，块内并发）
3. 每块完成后立即写入数据库（增量保存，崩溃安全）
4. 输出统计信息
"""
import asyncio
import logging
import time

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)

# 分块大小：每块处理完后立即写库（崩溃安全）
CHUNK_SIZE = 50


class Command(BaseCommand):
    help = '使用 LLM 为法条重新生成独立 keywords（基于 content）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--category', type=str, default='',
            help='仅处理指定分类（consumer_protection/e-commerce/contract/quality/safety/privacy/service/medical/labor）'
        )
        parser.add_argument(
            '--limit', type=int, default=0,
            help='仅处理前 N 条（0=全部，测试用）'
        )
        parser.add_argument(
            '--force', action='store_true', default=False,
            help='强制重新生成（默认跳过已使用 LLM 生成过的法条）'
        )
        parser.add_argument(
            '--dry-run', action='store_true', default=False,
            help='仅打印提取结果，不写入数据库'
        )
        parser.add_argument(
            '--max-concurrent', type=int, default=0,
            help='最大并发数（0=从 .env 读取 LLM_KEYWORD_MAX_CONCURRENT，默认 8）'
        )

    def handle(self, *args, **options):
        from api.models import LawArticle
        from api.services.keyword_extraction_service import (
            is_keyword_llm_available,
            extract_keywords_batch,
        )

        # 1. 检查 LLM 可用性
        if not is_keyword_llm_available():
            self.stdout.write(self.style.ERROR(
                '关键词提取 LLM 不可用：未配置 LLM_KEYWORD_API_KEY。'
                '请在 .env 中设置。'
            ))
            return

        # 2. 查询待处理法条
        qs = LawArticle.objects.filter(is_active=True)
        if options['category']:
            qs = qs.filter(category=options['category'])
            self.stdout.write(self.style.SUCCESS(
                f'仅处理分类 {options["category"]}'
            ))

        # 默认跳过已使用 LLM 生成过的法条（通过标记区分）
        # 标记规则：keywords 不等于同法律第一条的 keywords（说明已独立化）
        if not options['force']:
            all_articles = list(qs.order_by('law_name', 'id'))
            law_first_keywords = {}  # law_name → 第一条的 keywords
            for a in all_articles:
                if a.law_name not in law_first_keywords:
                    law_first_keywords[a.law_name] = a.keywords or []

            # 待处理：keywords 等于该法律第一条的 keywords（说明整部共用）
            to_process = []
            for a in all_articles:
                first_kw = law_first_keywords.get(a.law_name, [])
                if (a.keywords or []) == first_kw and len(first_kw) > 0:
                    to_process.append(a)
            self.stdout.write(self.style.SUCCESS(
                f'待处理法条 {len(to_process)} 条（已独立化的跳过，使用 --force 全部重做）'
            ))
        else:
            to_process = list(qs.order_by('law_name', 'id'))
            self.stdout.write(self.style.SUCCESS(
                f'强制重新生成 {len(to_process)} 条法条的 keywords'
            ))

        # 限制数量
        if options['limit'] > 0:
            to_process = to_process[:options['limit']]
            self.stdout.write(self.style.SUCCESS(
                f'限制处理前 {len(to_process)} 条'
            ))

        if not to_process:
            self.stdout.write(self.style.WARNING('无待处理法条'))
            return

        # 3. 分块并发提取 + 增量保存
        self.stdout.write('\n开始使用 LLM 并发提取关键词...')
        max_concurrent = options['max_concurrent']
        dry_run = options['dry_run']

        # Windows psycopg async 兼容：使用 SelectorEventLoop
        import sys
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        total = len(to_process)
        total_success = 0
        total_failed = 0
        total_skipped = 0
        start_time = time.time()

        # 进度回调
        last_report = [0]
        def on_progress(done, tot, succ, fail):
            # 每 50 条或最后一条打印进度
            if done - last_report[0] >= 50 or done == tot:
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                eta = (tot - done) / rate if rate > 0 else 0
                self.stdout.write(
                    f'  进度: {done}/{tot} ({done*100//tot}%) | '
                    f'成功 {succ} 失败 {fail} | '
                    f'{rate:.1f} 条/秒 | ETA {eta:.0f}s'
                )
                last_report[0] = done

        # 分块处理
        chunk_count = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
        for chunk_idx in range(chunk_count):
            chunk_start = chunk_idx * CHUNK_SIZE
            chunk_end = min(chunk_start + CHUNK_SIZE, total)
            chunk = to_process[chunk_start:chunk_end]

            self.stdout.write(self.style.SUCCESS(
                f'\n--- 块 {chunk_idx + 1}/{chunk_count} ({len(chunk)} 条) ---'
            ))

            # 块内进度
            chunk_success = [0]
            chunk_failed = [0]
            chunk_done = [0]
            def chunk_progress(done, tot, succ, fail):
                chunk_done[0] = done
                chunk_success[0] = succ
                chunk_failed[0] = fail

            try:
                results = asyncio.run(extract_keywords_batch(
                    chunk,
                    max_concurrent=max_concurrent,
                    on_progress=chunk_progress,
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'块 {chunk_idx + 1} 提取失败: {e}'
                ))
                total_failed += len(chunk)
                continue

            # 立即写库（增量保存，崩溃安全）
            for article, keywords in results:
                if keywords is None:
                    total_failed += 1
                    continue
                if not keywords:
                    total_skipped += 1
                    continue

                if not dry_run:
                    try:
                        with transaction.atomic():
                            article.keywords = keywords
                            article.save(update_fields=['keywords'])
                        total_success += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(
                            f'  写入失败 {article.law_name} {article.article_number}: {e}'
                        ))
                        total_failed += 1
                else:
                    total_success += 1
                    if total_success <= 3:  # dry-run 仅打印前 3 条示例
                        self.stdout.write(
                            f'  ✅ {article.law_name} {article.article_number}: {keywords}'
                        )

            # 块统计
            elapsed = time.time() - start_time
            overall_done = total_success + total_failed + total_skipped
            self.stdout.write(
                f'  块 {chunk_idx + 1} 完成: '
                f'成功 {chunk_success[0]} 失败 {chunk_failed[0]} | '
                f'累计 {overall_done}/{total} | 耗时 {elapsed:.0f}s'
            )

        # 4. 统计
        elapsed = time.time() - start_time
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'关键词生成完成: 成功 {total_success}, 失败 {total_failed}, 跳过 {total_skipped}'
        ))
        self.stdout.write(f'总耗时: {elapsed:.0f}s ({elapsed/60:.1f} 分钟)')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                '(dry-run 模式：未写入数据库)'
            ))
