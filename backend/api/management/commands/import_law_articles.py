# -*- coding: utf-8 -*-
"""v10 法律条文导入管理命令。

用法：
    # 导入预置的 15 条真实法条（消保法/电商法/民法典/食安法/产品质量法）
    python manage.py import_law_articles

    # 导入解析后的完整法条 JSON（1646条法律+规章）
    python manage.py import_law_articles --file=api/services/law_data_raw/output/law_articles_parsed.json --no-embed

    # 导入平台规则 JSON 到 PlatformRule 表（182条，合并为规则级别记录）
    python manage.py import_law_articles --platform-file=api/services/law_data_raw/output/platform_rules_parsed.json

    # 仅导入指定分类（consumer_protection/e-commerce/contract/quality/safety）
    python manage.py import_law_articles --category=consumer_protection

    # 强制重新生成 embedding（默认跳过已有法条）
    python manage.py import_law_articles --force-embed

    # 不生成 embedding（仅写入 MySQL 结构化数据）
    python manage.py import_law_articles --no-embed

流程：
1. 加载法条数据（预置或自定义 JSON）
2. 写入 MySQL LawArticle 表（upsert）
3. 生成 embedding 并写入 PG law_article_vectors 表（可选）
4. 可选：导入平台规则到 PlatformRule 表
"""
import json
import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


# 平台名称中英文映射
PLATFORM_NAME_MAP = {
    '京东': 'jd',
    '淘宝': 'taobao',
    '天猫': 'tmall',
    '拼多多': 'pdd',
    '抖音': 'douyin',
    '抖音电商': 'douyin',
    '快手': 'kuaishou',
    '快手电商': 'kuaishou',
    '唯品会': 'vipshop',
    '苏宁易购': 'suning',
}


class Command(BaseCommand):
    help = '导入法律条文到 LawArticle 表（含 embedding 向量索引）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str, default='',
            help='自定义法条 JSON 文件路径（不指定则使用预置法条）'
        )
        parser.add_argument(
            '--platform-file', type=str, default='',
            help='平台规则 JSON 文件路径（导入到 PlatformRule 表）'
        )
        parser.add_argument(
            '--category', type=str, default='',
            help='仅导入指定分类（consumer_protection/e-commerce/contract/quality/safety）'
        )
        parser.add_argument(
            '--force-embed', action='store_true', default=False,
            help='强制重新生成 embedding（默认跳过已有法条）'
        )
        parser.add_argument(
            '--no-embed', action='store_true', default=False,
            help='不生成 embedding（仅写入 MySQL 结构化数据）'
        )

    def handle(self, *args, **options):
        # ========== 平台规则导入（如果指定了 --platform-file）==========
        if options['platform_file']:
            self._import_platform_rules(options['platform_file'])
            # 如果同时指定了 --file，继续导入法律条文
            if not options['file']:
                return

        from api.services.law_data import get_all_law_articles, get_law_articles_by_category
        from api.models import LawArticle

        # 1. 加载法条数据
        if options['file']:
            with open(options['file'], 'r', encoding='utf-8') as f:
                articles = json.load(f)
            self.stdout.write(self.style.SUCCESS(f'从文件加载 {len(articles)} 条法条: {options["file"]}'))
        else:
            if options['category']:
                articles = get_law_articles_by_category(options['category'])
                self.stdout.write(self.style.SUCCESS(
                    f'从预置数据加载分类 {options["category"]} 的 {len(articles)} 条法条'
                ))
            else:
                articles = get_all_law_articles()
                self.stdout.write(self.style.SUCCESS(
                    f'从预置数据加载全部 {len(articles)} 条法条'
                ))

        if not articles:
            self.stdout.write(self.style.WARNING('无可导入的法条数据'))
            return

        # 2. 写入 MySQL LawArticle 表（upsert）
        created_count = 0
        updated_count = 0
        skipped_count = 0
        law_articles_for_embed = []

        for article_data in articles:
            try:
                with transaction.atomic():
                    # 解析生效日期
                    effective_date = self._parse_date(article_data.get('effective_date', ''))

                    obj, created = LawArticle.objects.update_or_create(
                        law_name=article_data['law_name'],
                        article_number=article_data['article_number'],
                        defaults={
                            'chapter': article_data.get('chapter', ''),
                            'content': article_data['content'],
                            'summary': article_data.get('summary', ''),
                            'category': article_data.get('category', 'other'),
                            'keywords': article_data.get('keywords', []),
                            'applicable_scenarios': article_data.get('applicable_scenarios', []),
                            'effective_date': effective_date,
                            'is_active': article_data.get('is_active', True),
                            'source_url': article_data.get('source_url', ''),
                        }
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                    law_articles_for_embed.append(obj)
            except Exception as e:
                logger.error(f"导入法条失败 {article_data.get('law_name')} {article_data.get('article_number')}: {e}", exc_info=True)
                skipped_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nMySQL 写入完成: 新增 {created_count} 条, 更新 {updated_count} 条, 跳过 {skipped_count} 条'
        ))

        # 3. 生成 embedding 并写入 PG（可选）
        if options['no_embed']:
            self.stdout.write(self.style.WARNING('跳过 embedding 生成（--no-embed）'))
            return

        if not law_articles_for_embed:
            self.stdout.write(self.style.WARNING('无可生成 embedding 的法条'))
            return

        self.stdout.write('\n开始生成 embedding 向量...')
        try:
            # Windows 兼容：psycopg async 需要 SelectorEventLoop（非 ProactorEventLoop）
            # asyncio.run 在 Windows 默认用 ProactorEventLoop，故手动创建 SelectorEventLoop
            import sys
            if sys.platform == 'win32':
                import selectors
                loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
            else:
                loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                embed_count = loop.run_until_complete(self._generate_embeddings(
                    law_articles_for_embed, options['force_embed']
                ))
            finally:
                loop.close()
            self.stdout.write(self.style.SUCCESS(
                f'PG 向量写入完成: {embed_count} 条法条已生成 embedding'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Embedding 生成失败: {e}'))
            self.stdout.write(self.style.WARNING(
                '法条结构化数据已写入 MySQL，可稍后单独运行 embedding 生成'
            ))

    def _parse_date(self, date_str: str):
        """解析日期字符串，支持多种格式。"""
        if not date_str:
            return None
        date_str = date_str.strip()
        # 尝试多种日期格式
        formats = [
            '%Y年%m月%d日',
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%Y.%m.%d',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        # 尝试提取日期部分（如"2025年10月15日起施行" → "2025年10月15日"）
        m = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', date_str)
        if m:
            try:
                return datetime.strptime(m.group(1), '%Y年%m月%d日').date()
            except ValueError:
                pass
        return None

    def _import_platform_rules(self, json_file: str):
        """导入平台规则到 PlatformRule 表。

        将条文级别的JSON合并为规则级别的记录（每个平台每个规则一条记录）。
        """
        from api.models import PlatformRule

        with open(json_file, 'r', encoding='utf-8') as f:
            articles = json.load(f)

        self.stdout.write(self.style.SUCCESS(
            f'从文件加载 {len(articles)} 条平台规则条文: {json_file}'
        ))

        # 按 platform + rule_name 分组
        groups = defaultdict(list)
        for article in articles:
            platform_name = article.get('platform', '未知')
            rule_name = article.get('rule_name', article.get('law_name', '未知规则'))
            groups[(platform_name, rule_name)].append(article)

        self.stdout.write(f'分组完成: {len(groups)} 个规则')

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for (platform_name, rule_name), articles_in_group in groups.items():
            try:
                with transaction.atomic():
                    # 平台名称映射
                    platform_code = PLATFORM_NAME_MAP.get(platform_name, 'other')

                    # 合并所有条文为规则内容
                    content_parts = []
                    for a in sorted(articles_in_group, key=lambda x: x.get('article_number_int', 0)):
                        chapter = a.get('chapter', '')
                        article_num = a.get('article_number', '')
                        article_content = a.get('content', '')
                        if chapter:
                            content_parts.append(f'【{chapter}】')
                        content_parts.append(f'{article_num} {article_content}')
                    content = '\n\n'.join(content_parts)

                    # 推断问题类型（根据规则名称）
                    issue_type = self._infer_issue_type(rule_name)

                    # 解析日期
                    effective_date = self._parse_date(
                        articles_in_group[0].get('effective_date', '')
                    )
                    source_url = articles_in_group[0].get('source_url', '')

                    obj, created = PlatformRule.objects.update_or_create(
                        platform=platform_code,
                        rule_name=rule_name,
                        defaults={
                            'issue_type': issue_type,
                            'content': content,
                            'compensation_standard': '',
                            'handling_process': '',
                            'source_url': source_url,
                            'effective_date': effective_date,
                            'is_active': True,
                        }
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                    self.stdout.write(
                        f'  {"新增" if created else "更新"}: [{platform_name}] {rule_name} '
                        f'({len(articles_in_group)} 条)'
                    )
            except Exception as e:
                logger.error(f"导入平台规则失败 [{platform_name}] {rule_name}: {e}", exc_info=True)
                skipped_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nPlatformRule 写入完成: 新增 {created_count} 条, 更新 {updated_count} 条, 跳过 {skipped_count} 条'
        ))

    def _infer_issue_type(self, rule_name: str) -> str:
        """根据规则名称推断问题类型。"""
        name = rule_name.lower()
        if '纠纷' in rule_name or '争议' in rule_name:
            return 'dispute'
        if '延迟' in rule_name or '发货' in rule_name:
            return 'late_delivery'
        if '假' in rule_name or 'counterfeit' in name:
            return 'counterfeit'
        if '质量' in rule_name or 'quality' in name:
            return 'quality_issue'
        if '退款' in rule_name or 'refund' in name:
            return 'refund_dispute'
        return 'general'

    async def _generate_embeddings(self, law_articles, force: bool) -> int:
        """为法条生成 embedding 并写入 PG law_article_vectors 表。

        Args:
            law_articles: LawArticle 实例列表
            force: 是否强制重新生成（默认跳过已有 embedding）

        Returns:
            成功生成 embedding 的法条数量
        """
        from api.services.embedding_service import is_embedding_available, embed_documents
        from api.services.rag_service import LawVectorStore

        if not is_embedding_available():
            raise RuntimeError(
                'Embedding 服务不可用：未配置 EMBEDDING_API_KEY。'
                '请在 .env 中设置 SiliconFlow API Key 后重新运行，'
                '或使用 --no-embed 跳过 embedding 生成。'
            )

        vector_store = LawVectorStore()
        await vector_store.ensure_table()

        # 过滤：跳过已有 embedding 的法条（除非 force）
        to_embed = []
        for article in law_articles:
            if force or not await vector_store.exists(article.law_name, article.article_number):
                to_embed.append(article)

        if not to_embed:
            logger.info('所有法条已有 embedding，跳过（使用 --force-embed 强制重新生成）')
            return 0

        # 构造 embedding 输入文本（法条名称 + 编号 + 章节 + 摘要 + 关键词 + 内容）
        texts = []
        for article in to_embed:
            keywords_str = ' '.join(article.keywords) if article.keywords else ''
            scenarios_str = ' '.join(article.applicable_scenarios) if article.applicable_scenarios else ''
            text = (
                f"{article.law_name} {article.article_number}\n"
                f"摘要：{article.summary}\n"
                f"关键词：{keywords_str}\n"
                f"适用场景：{scenarios_str}\n"
                f"条文内容：{article.content}"
            )
            texts.append(text)

        # 批量生成 embedding（分批处理，每批最多 50 条）
        self.stdout.write(f'正在为 {len(to_embed)} 条法条生成 embedding...')
        batch_size = 50
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            self.stdout.write(f'  批次 {i // batch_size + 1}/{(len(texts) + batch_size - 1) // batch_size}: {len(batch)} 条')
            batch_embeddings = await embed_documents(batch)
            embeddings.extend(batch_embeddings)

        # 写入 PG
        success_count = 0
        for article, embedding in zip(to_embed, embeddings):
            try:
                await vector_store.upsert(
                    law_name=article.law_name,
                    article_number=article.article_number,
                    embedding=embedding,
                    category=article.category,
                )
                success_count += 1
            except Exception as e:
                logger.error(f"写入向量失败 {article.law_name} {article.article_number}: {e}", exc_info=True)

        return success_count
