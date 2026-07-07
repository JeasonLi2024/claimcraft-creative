# -*- coding: utf-8 -*-
"""v10 法律条文导入管理命令。

用法：
    # 导入预置的 14 条真实法条（消保法/电商法/民法典/食安法/产品质量法）
    python manage.py import_law_articles

    # 导入自定义 JSON 文件（格式见 law_data.py）
    python manage.py import_law_articles --file=path/to/law_articles.json

    # 仅导入指定分类（consumer_protection/e-commerce/contract/quality/safety）
    python manage.py import_law_articles --category=consumer_protection

    # 强制重新生成 embedding（默认跳过已有法条）
    python manage.py import_law_articles --force-embed

流程：
1. 加载法条数据（预置或自定义 JSON）
2. 写入 MySQL LawArticle 表（upsert）
3. 生成 embedding 并写入 PG law_article_vectors 表（可选）
"""
import json
import asyncio
import logging

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '导入法律条文到 LawArticle 表（含 embedding 向量索引）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str, default='',
            help='自定义法条 JSON 文件路径（不指定则使用预置法条）'
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
                            'effective_date': article_data.get('effective_date'),
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
            embed_count = asyncio.run(self._generate_embeddings(
                law_articles_for_embed, options['force_embed']
            ))
            self.stdout.write(self.style.SUCCESS(
                f'PG 向量写入完成: {embed_count} 条法条已生成 embedding'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Embedding 生成失败: {e}'))
            self.stdout.write(self.style.WARNING(
                '法条结构化数据已写入 MySQL，可稍后单独运行 embedding 生成'
            ))

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

        # 批量生成 embedding
        self.stdout.write(f'正在为 {len(to_embed)} 条法条生成 embedding...')
        embeddings = await embed_documents(texts)

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
