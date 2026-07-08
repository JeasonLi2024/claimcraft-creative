# -*- coding: utf-8 -*-
"""Rerank 重排服务（v10 新增）。

使用 Cross-encoder 模型对粗排候选做精排，提升法律/医疗等高严谨领域的检索精度。

设计要点：
- 调用 SiliconFlow /v1/rerank 端点（非 OpenAI 兼容，需用 httpx 直接调用）
- 模型：BAAI/bge-reranker-v2-m3（多语言 Cross-encoder，中英文均优）
- 输入：query + 候选文档列表（粗排后的几十条法条）
- 输出：按相关性分数降序排列的文档索引
- 失败时优雅降级（返回原始顺序，不阻塞主检索流程）

Cross-encoder vs Bi-encoder：
- Bi-encoder（向量检索）：query 和 document 分别编码，计算余弦相似度，速度快但精度低
- Cross-encoder（rerank）：query 和 document 拼接后输入同一 Transformer，输出相关性分数，
  精度高（比 bi-encoder 高 10-20%），但速度慢（每个 (q,d) 对都要一次前向计算）
- 最佳实践：粗排用 bi-encoder 召回 top-50，rerank 用 cross-encoder 精排 top-5
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _get_rerank_config() -> dict:
    """读取 Rerank 服务配置（从 .env）。

    Returns:
        dict: {api_key, base_url, model, top_n, candidate_limit, score_threshold, timeout}
    """
    return {
        'api_key': os.environ.get('RERANK_API_KEY', '').strip(),
        'base_url': os.environ.get(
            'RERANK_BASE_URL', 'https://api.siliconflow.cn/v1'
        ).strip().rstrip('/'),
        'model': os.environ.get(
            'RERANK_MODEL', 'BAAI/bge-reranker-v2-m3'
        ).strip(),
        'top_n': int(os.environ.get('RERANK_TOP_N', '5')),
        'candidate_limit': int(os.environ.get('RERANK_CANDIDATE_LIMIT', '50')),
        'score_threshold': float(os.environ.get('RERANK_SCORE_THRESHOLD', '0.0')),
        'timeout': int(os.environ.get('RERANK_TIMEOUT', '30')),
        'max_retries': int(os.environ.get('RERANK_MAX_RETRIES', '2')),
    }


def is_rerank_available() -> bool:
    """检查 Rerank 服务是否可用（API Key 已配置）。"""
    return bool(_get_rerank_config()['api_key'])


def _build_document_text(article_dict: dict) -> str:
    """从法条字典构建 rerank 输入文本。

    将 law_name + article_number + content 拼接，给 reranker 提供完整上下文。
    截断到 500 字符（bge-reranker-v2-m3 限制 512 token）。

    Args:
        article_dict: 法条字典（含 law_name, article_number, content）

    Returns:
        拼接后的文档文本
    """
    law_name = article_dict.get('law_name', '')
    article_number = article_dict.get('article_number', '')
    content = article_dict.get('content', '') or ''
    # 拼接：法律名称 条款编号：条文内容
    header = f'{law_name} {article_number}：' if law_name or article_number else ''
    text = header + content
    return text[:500]


async def rerank(
    query: str,
    candidates: list[dict],
    top_n: int = 0,
) -> list[dict]:
    """对候选法条做 rerank 精排。

    调用 SiliconFlow /v1/rerank 端点，使用 bge-reranker-v2-m3 Cross-encoder
    对每个 (query, candidate) 对计算相关性分数，按分数降序排列。

    Args:
        query: 用户查询文本
        candidates: 候选法条列表（粗排结果，每条含 law_name/article_number/content 等）
        top_n: 返回 top-n 条（0=使用 .env 默认值 RERANK_TOP_N）

    Returns:
        重排后的法条列表（按 rerank score 降序），每条新增字段：
            rerank_score: rerank 相关性分数（0-1）
        原始顺序保留降级使用（rerank 失败时）

    失败降级：
        - API Key 未配置：直接返回原始 candidates（截断到 top_n）
        - API 调用失败：返回原始 candidates（截断到 top_n），记录日志
    """
    cfg = _get_rerank_config()

    if not cfg['api_key']:
        logger.info('[Rerank] 未配置 RERANK_API_KEY，跳过重排（使用粗排顺序）')
        n = top_n or cfg['top_n']
        return candidates[:n]

    if not candidates:
        return []

    if not query or not query.strip():
        logger.warning('[Rerank] 查询为空，跳过重排')
        n = top_n or cfg['top_n']
        return candidates[:n]

    n = top_n or cfg['top_n']
    # 限制候选数量（避免 rerank 成本过高）
    candidate_limit = cfg['candidate_limit']
    to_rerank = candidates[:candidate_limit]

    # 构建文档文本列表
    documents = [_build_document_text(c) for c in to_rerank]

    logger.info(
        f'[Rerank] 开始重排: query="{query[:50]}", '
        f'{len(to_rerank)} 条候选, top_n={n}'
    )

    try:
        import httpx

        url = f'{cfg["base_url"]}/rerank'
        headers = {
            'Authorization': f'Bearer {cfg["api_key"]}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': cfg['model'],
            'query': query,
            'documents': documents,
            'top_n': len(to_rerank),  # 返回全部候选的分数，自己截断
            'return_documents': False,
        }

        async with httpx.AsyncClient(timeout=cfg['timeout']) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            logger.warning(
                f'[Rerank] API 返回 {response.status_code}: '
                f'{response.text[:200]}，降级使用粗排顺序'
            )
            return to_rerank[:n]

        data = response.json()
        results = data.get('results', [])

        if not results:
            logger.warning('[Rerank] API 返回空结果，降级使用粗排顺序')
            return to_rerank[:n]

        # 按 relevance_score 降序排列，映射回原始候选
        results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

        reranked = []
        for r in results:
            idx = r.get('index', -1)
            score = float(r.get('relevance_score', 0))
            if idx < 0 or idx >= len(to_rerank):
                continue
            candidate = dict(to_rerank[idx])  # 浅拷贝
            candidate['rerank_score'] = round(score, 4)
            reranked.append(candidate)

        # 应用分数阈值
        threshold = cfg['score_threshold']
        if threshold > 0:
            reranked = [r for r in reranked if r['rerank_score'] >= threshold]

        # 截断到 top_n
        reranked = reranked[:n]

        logger.info(
            f'[Rerank] 重排完成: {len(to_rerank)} → {len(reranked)} 条, '
            f'top1 score={reranked[0]["rerank_score"] if reranked else 0:.4f}'
        )

        return reranked

    except Exception as e:
        logger.error(f'[Rerank] 重排失败（降级使用粗排顺序）: {e}', exc_info=True)
        return to_rerank[:n]
