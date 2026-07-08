# -*- coding: utf-8 -*-
"""BM25 检索服务（v10 新增）。

使用 rank_bm25 库实现中文法条的关键词检索，与向量检索通过 RRF 融合。

设计要点：
- jieba 分词后构建 BM25 索引
- 内存索引（2260 条法条量级，内存占用可接受）
- 按 category 维护独立索引（懒加载，首次查询时构建）
- 与向量检索结果通过 RRF（Reciprocal Rank Fusion）融合
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class _CategoryIndex:
    """单个 category 的 BM25 索引。"""

    def __init__(self):
        self._bm25 = None
        self._articles = []
        self._tokenized_corpus = []

    def build(self, articles: list):
        """构建 BM25 索引。"""
        import jieba
        from rank_bm25 import BM25Okapi

        self._articles = articles
        self._tokenized_corpus = []
        for article in articles:
            content = article.content or ''
            words = [w for w in jieba.cut(content) if len(w.strip()) >= 1]
            self._tokenized_corpus.append(words)

        if self._tokenized_corpus:
            self._bm25 = BM25Okapi(self._tokenized_corpus)
        else:
            self._bm25 = None

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """BM25 检索（返回归一化 score）。"""
        if not self._bm25 or not self._articles:
            return []

        import jieba

        query_tokens = [w for w in jieba.cut(query) if len(w.strip()) >= 1]
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # 排序并取 top_k * 2（多取一些以便后续 RRF 融合）
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        top_results = indexed_scores[:top_k * 2]

        if not top_results:
            return []

        # 归一化 score（除以最大值）
        max_score = top_results[0][1] if top_results[0][1] > 0 else 1.0
        if max_score <= 0:
            return []

        results = []
        for idx, score in top_results:
            if score <= 0:
                continue
            article = self._articles[idx]
            normalized_score = float(score) / float(max_score)
            results.append({
                'law_name': article.law_name,
                'article_number': article.article_number,
                'category': article.category,
                'score': round(normalized_score, 3),
            })

        return results[:top_k]


class LawBM25Index:
    """法条 BM25 内存索引（单例，按 category 维护独立索引）。

    使用流程：
        index = LawBM25Index.get_instance()
        results = index.search("商家欺诈退一赔三", category="consumer_protection", top_k=5)

    设计说明：
    - 每个 category 维护独立的 BM25 索引（懒加载）
    - BM25 score 在同一 category 内归一化，避免跨 category 量纲不一致
    - category="" 使用全局索引
    """

    _instance: Optional['LawBM25Index'] = None

    def __init__(self):
        self._indexes: dict[str, _CategoryIndex] = {}  # category → _CategoryIndex

    @classmethod
    def get_instance(cls) -> 'LawBM25Index':
        """获取单例实例。"""
        if cls._instance is None:
            cls._instance = LawBM25Index()
        return cls._instance

    def _get_or_build(self, category: str = "") -> _CategoryIndex:
        """获取或构建指定 category 的索引。"""
        if category in self._indexes:
            return self._indexes[category]

        from api.models import LawArticle

        qs = LawArticle.objects.filter(is_active=True)
        if category:
            qs = qs.filter(category=category)
        articles = list(qs.order_by('id'))

        idx = _CategoryIndex()
        idx.build(articles)
        self._indexes[category] = idx

        logger.info(
            f'[BM25] 索引构建完成: {len(articles)} 条法条 '
            f'(category={category or "all"})'
        )
        return idx

    def search(self, query: str, category: str = "",
               top_k: int = 5) -> list[dict]:
        """BM25 关键词检索。

        Args:
            query: 查询文本
            category: 法律分类过滤（空=全部）
            top_k: 返回 top-k

        Returns:
            list[dict]: [{law_name, article_number, category, score}]
            score 已归一化到 0-1 范围
        """
        idx = self._get_or_build(category)
        return idx.search(query, top_k=top_k)

    def invalidate(self):
        """使所有索引失效（数据更新后调用以重建索引）。"""
        self._indexes.clear()
        logger.info('[BM25] 所有索引已失效，下次查询时重建')


def reciprocal_rank_fusion(
    bm25_results: list[dict],
    vector_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """RRF（Reciprocal Rank Fusion）融合 BM25 和向量检索结果。

    RRF 公式：score = Σ 1 / (k + rank_i)
    - k=60 是常用参数，平衡 top 和 bottom 结果的权重
    - 不依赖原始 score，仅用 rank 位置，避免不同检索器的 score 量纲差异

    Args:
        bm25_results: BM25 检索结果
        vector_results: 向量检索结果
        k: RRF 参数（默认 60）

    Returns:
        list[dict]: 融合后的结果（按 RRF score 降序）
        每条含 law_name, article_number, category, score（RRF 融合分数）,
        bm25_score, vector_score
    """
    merged = {}

    # BM25 结果：按 rank 计算 RRF 分数
    for rank, r in enumerate(bm25_results, start=1):
        key = (r['law_name'], r['article_number'])
        rrf_score = 1.0 / (k + rank)
        if key not in merged:
            merged[key] = {
                'law_name': r['law_name'],
                'article_number': r['article_number'],
                'category': r['category'],
                'rrf_score': rrf_score,
                'bm25_score': r.get('score', 0.0),
                'vector_score': 0.0,
            }
        else:
            merged[key]['rrf_score'] += rrf_score
            merged[key]['bm25_score'] = r.get('score', 0.0)

    # 向量结果：按 rank 计算 RRF 分数
    for rank, r in enumerate(vector_results, start=1):
        key = (r['law_name'], r['article_number'])
        rrf_score = 1.0 / (k + rank)
        if key not in merged:
            merged[key] = {
                'law_name': r['law_name'],
                'article_number': r['article_number'],
                'category': r['category'],
                'rrf_score': rrf_score,
                'bm25_score': 0.0,
                'vector_score': r.get('score', 0.0),
            }
        else:
            merged[key]['rrf_score'] += rrf_score
            merged[key]['vector_score'] = r.get('score', 0.0)

    # 按 RRF score 降序
    results = list(merged.values())
    results.sort(key=lambda x: x['rrf_score'], reverse=True)

    return results
