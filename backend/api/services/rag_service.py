# -*- coding: utf-8 -*-
"""RAG 检索服务（v10 新增）。

包含两个核心组件：
1. LawVectorStore：管理 PG 侧的 law_article_vectors 表（CRUD + pgvector 检索）
2. LawRetriever：法律条文 RAG 检索器（向量检索 + MySQL 结构化数据聚合）

设计要点：
- 向量数据存 PostgreSQL（pgvector），结构化数据存 MySQL（LawArticle 表）
- 检索流程：PG 向量 top-k → 取 law_name+article_number → MySQL 取完整内容
- 支持 category 预过滤（缩小检索范围，提升精度+速度）
- 余弦相似度（cosine distance），中文语义检索最优
- 检索失败时优雅降级（返回空列表，不阻塞主工作流）
"""
import os
import logging
import asyncio
from typing import Optional

import psycopg
from psycopg import sql

logger = logging.getLogger(__name__)


def _get_vector_db_url() -> str:
    """获取 PG 向量库连接串（复用 checkpointer PG 实例）。"""
    return os.environ.get(
        'LAW_VECTOR_DB_URL',
        os.environ.get('CHECKPOINTER_DB_URL', '')
    )


def _get_rag_config() -> dict:
    """读取 RAG 检索配置。"""
    return {
        'top_k': int(os.environ.get('RAG_TOP_K', '5')),
        'score_threshold': float(os.environ.get('RAG_SCORE_THRESHOLD', '0.3')),
        'enabled': os.environ.get('RAG_ENABLED', 'true').lower() == 'true',
    }


def is_rag_enabled() -> bool:
    """RAG 是否启用。"""
    return _get_rag_config()['enabled']


class LawVectorStore:
    """PG 侧法条向量存储（law_article_vectors 表）。

    表结构：
        law_name VARCHAR(100)
        article_number VARCHAR(20)
        embedding vector(VECTOR_DIM)
        category VARCHAR(30)
        created_at TIMESTAMPTZ
        PRIMARY KEY (law_name, article_number)
    索引：
        HNSW 索引（embedding 字段，cosine distance）
        category + law_name 复合索引（预过滤）

    维度说明：
        Qwen3-VL-Embedding-8B 原生维度 4096（SiliconFlow 免费版不支持降维）。
        如切换模型，请同步修改 .env 中 EMBEDDING_VECTOR_DIM。
    """

    TABLE_NAME = 'law_article_vectors'

    def __init__(self, db_url: str = ""):
        self._db_url = db_url or _get_vector_db_url()
        if not self._db_url:
            raise RuntimeError(
                '未配置 LAW_VECTOR_DB_URL 或 CHECKPOINTER_DB_URL。'
                '请在 .env 中设置 PostgreSQL 连接串。'
            )

    @staticmethod
    def _get_vector_dim() -> int:
        """获取向量维度（从 .env 读取，默认 4096）。"""
        return int(os.environ.get('EMBEDDING_VECTOR_DIM', '4096'))

    async def ensure_table(self):
        """确保表和索引存在（幂等，首次导入时自动创建）。

        安全说明：CREATE INDEX CONCURRENTLY 不能在事务中执行，
        故使用 autocommit 模式。若已存在则跳过（IF NOT EXISTS）。

        索引策略：
        - 维度 ≤ 2000：创建 HNSW 索引（近似最近邻，查询快）
        - 维度 > 2000：跳过 HNSW（pgvector 限制），改用顺序扫描
          （万级以下法条量级，顺序扫描耗时仅几毫秒，完全可接受）
        """
        dim = self._get_vector_dim()
        statements = [
            # 1. 启用 pgvector 扩展（首次需要超级用户权限，已存在则跳过）
            'CREATE EXTENSION IF NOT EXISTS vector;',
            # 2. 建表
            f'''
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                law_name VARCHAR(100) NOT NULL,
                article_number VARCHAR(20) NOT NULL,
                embedding vector({dim}) NOT NULL,
                category VARCHAR(30) NOT NULL DEFAULT 'other',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (law_name, article_number)
            );
            ''',
            # 3. category + law_name 复合索引（预过滤）
            f'CREATE INDEX IF NOT EXISTS idx_law_vectors_category '
            f'ON {self.TABLE_NAME} (category, law_name);',
        ]

        # 4. HNSW 向量索引（仅维度 ≤ 2000 时创建，pgvector 限制）
        if dim <= 2000:
            statements.append(
                f'CREATE INDEX IF NOT EXISTS idx_law_vectors_hnsw '
                f'ON {self.TABLE_NAME} USING hnsw (embedding vector_cosine_ops) '
                f'WITH (m = 16, ef_construction = 64);'
            )
        else:
            logger.info(
                f'向量维度 {dim} > 2000，跳过 HNSW 索引创建（pgvector 限制），'
                f'改用顺序扫描（万级以下法条量级性能可接受）'
            )

        # autocommit 模式（CONCURRENTLY 不支持事务）
        async with await psycopg.AsyncConnection.connect(self._db_url, autocommit=True) as conn:
            for stmt in statements:
                try:
                    async with conn.cursor() as cur:
                        await cur.execute(stmt)
                except Exception as e:
                    logger.warning(f'执行 SQL 失败（忽略，可能已存在）: {e}')

    async def exists(self, law_name: str, article_number: str) -> bool:
        """检查指定法条是否已有向量。"""
        async with await psycopg.AsyncConnection.connect(self._db_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f'SELECT 1 FROM {self.TABLE_NAME} '
                    f'WHERE law_name = %s AND article_number = %s LIMIT 1',
                    (law_name, article_number)
                )
                return await cur.fetchone() is not None

    async def upsert(self, law_name: str, article_number: str,
                     embedding: list[float], category: str = 'other'):
        """写入或更新法条向量（upsert）。

        Args:
            law_name: 法律名称
            article_number: 条文编号
            embedding: 向量（维度需与表定义一致）
            category: 法律分类（用于预过滤）
        """
        async with await psycopg.AsyncConnection.connect(self._db_url) as conn:
            async with conn.cursor() as cur:
                # pgvector 使用 '[1,2,3]' 字符串格式
                embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'
                await cur.execute(
                    f'''
                    INSERT INTO {self.TABLE_NAME} (law_name, article_number, embedding, category)
                    VALUES (%s, %s, %s::vector, %s)
                    ON CONFLICT (law_name, article_number)
                    DO UPDATE SET embedding = EXCLUDED.embedding, category = EXCLUDED.category
                    ''',
                    (law_name, article_number, embedding_str, category)
                )
            await conn.commit()

    async def search(self, query_embedding: list[float],
                     category: str = "", top_k: int = 5,
                     score_threshold: float = 0.0) -> list[dict]:
        """向量相似度检索（余弦距离）。

        Args:
            query_embedding: 查询向量（维度需与表定义一致）
            category: 法律分类过滤（空字符串=不过滤）
            top_k: 返回 top-k 条结果
            score_threshold: 相似度阈值（余弦相似度，低于此值丢弃）

        Returns:
            list[dict]: [{law_name, article_number, category, score}]
            score 范围 0-1（1=完全相似）
        """
        embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

        if category:
            query = sql.SQL(f'''
                SELECT law_name, article_number, category,
                       1 - (embedding <=> %s::vector) AS score
                FROM {self.TABLE_NAME}
                WHERE category = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            ''')
            params = (embedding_str, category, embedding_str, top_k)
        else:
            query = sql.SQL(f'''
                SELECT law_name, article_number, category,
                       1 - (embedding <=> %s::vector) AS score
                FROM {self.TABLE_NAME}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            ''')
            params = (embedding_str, embedding_str, top_k)

        async with await psycopg.AsyncConnection.connect(self._db_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()

        results = []
        for row in rows:
            score = float(row[3]) if row[3] is not None else 0.0
            if score >= score_threshold:
                results.append({
                    'law_name': row[0],
                    'article_number': row[1],
                    'category': row[2],
                    'score': score,
                })
        return results


class LawRetriever:
    """法律条文 RAG 检索器（向量检索 + MySQL 结构化数据聚合）。

    使用流程：
        retriever = LawRetriever()
        results = await retriever.retrieve("商家虚假宣传欺诈消费者")
        # results: [{law_name, article_number, content, summary, score, ...}]
    """

    def __init__(self):
        self._vector_store: Optional[LawVectorStore] = None
        self._config = _get_rag_config()

    def _get_vector_store(self) -> LawVectorStore:
        """懒加载向量存储（避免初始化时连不上 PG 报错）。"""
        if self._vector_store is None:
            self._vector_store = LawVectorStore()
        return self._vector_store

    async def retrieve(self, query: str, category: str = "",
                       top_k: int = 0) -> list[dict]:
        """检索相关法条。

        Args:
            query: 查询文本（如 "商家虚假宣传欺诈消费者"）
            category: 法律分类过滤（空=全部）
            top_k: 返回 top-k（0=使用 .env 默认值 5）

        Returns:
            list[dict]: 法条列表，每条含：
                law_name, article_number, chapter, content, summary,
                category, keywords, applicable_scenarios, source_url, score
            检索失败返回空列表（不阻塞主工作流）
        """
        if not self._config['enabled']:
            logger.info('[RAG] RAG 已禁用（RAG_ENABLED=false），跳过检索')
            return []

        from api.services.embedding_service import is_embedding_available, embed_query

        if not is_embedding_available():
            logger.warning('[RAG] Embedding 服务不可用，跳过检索')
            return []

        top_k = top_k or self._config['top_k']
        score_threshold = self._config['score_threshold']

        try:
            # 1. 生成查询向量
            query_embedding = await embed_query(query)

            # 2. PG 向量检索
            vector_store = self._get_vector_store()
            vector_results = await vector_store.search(
                query_embedding, category=category,
                top_k=top_k, score_threshold=score_threshold
            )

            if not vector_results:
                logger.info(f'[RAG] 未检索到相关法条 (query={query[:50]})')
                return []

            # 3. 从 MySQL 取完整法条内容
            from api.models import LawArticle
            from asgiref.sync import sync_to_async

            law_keys = [(r['law_name'], r['article_number']) for r in vector_results]
            articles = await sync_to_async(list)(
                LawArticle.objects.filter(
                    law_name__in=[k[0] for k in law_keys],
                    article_number__in=[k[1] for k in law_keys],
                    is_active=True,
                )
            )
            article_map = {(a.law_name, a.article_number): a for a in articles}

            # 4. 聚合结果（向量 score + MySQL 结构化数据）
            results = []
            for vr in vector_results:
                article = article_map.get((vr['law_name'], vr['article_number']))
                if not article:
                    continue
                result = article.to_retrieval_dict()
                result['score'] = vr['score']
                results.append(result)

            # 按 score 降序
            results.sort(key=lambda x: x['score'], reverse=True)

            logger.info(
                f'[RAG] 检索完成 (query={query[:50]}, '
                f'category={category or "all"}, results={len(results)})'
            )
            return results

        except Exception as e:
            logger.error(f'[RAG] 检索失败（降级返回空列表）: {e}', exc_info=True)
            return []

    async def retrieve_by_keywords(self, keywords: list[str],
                                   category: str = "", top_k: int = 0) -> list[dict]:
        """按关键词列表检索法条（拼接为查询文本）。

        Args:
            keywords: 关键词列表（如 ["欺诈", "退一赔三", "虚假宣传"]）
            category: 法律分类过滤
            top_k: 返回 top-k

        Returns:
            法条列表（同 retrieve 返回格式）
        """
        query = ' '.join(keywords)
        return await self.retrieve(query, category, top_k)
