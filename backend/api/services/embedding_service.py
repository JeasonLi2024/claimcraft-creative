# -*- coding: utf-8 -*-
"""Embedding 服务（v10 新增）。

通过 SiliconFlow OpenAI 兼容接口调用 BAAI/bge-large-zh-v1.5 生成文本向量。

设计要点：
- 复用 LangChain OpenAIEmbeddings（与 LangChain 生态无缝衔接）
- 配置从 .env 读取（EMBEDDING_*），无硬编码
- 向量维度 1024（与 pgvector 索引一致）
- 同步 + 异步双接口（embed_query / aembed_query）
- 模型专为中文检索优化，适合法律文本向量化
- LRU 查询向量缓存（v2 2026-07-19）：相同 query 复用向量，避免重复 HTTP 调用
"""
import os
import logging
from functools import lru_cache
from collections import OrderedDict

logger = logging.getLogger(__name__)


# ============================================================
# 查询向量 LRU 缓存（v2 2026-07-19 新增）
# ------------------------------------------------------------
# RAG 检索中相同 query 会被反复调用（pre_retrieve + 多轮工具调用 lookup_law），
# 每次 HTTP 请求 SiliconFlow API 耗时 0.3~3 秒。缓存命中可省掉这步开销。
# 容量 256 条 × 1024 维 float32 ≈ 1MB，可接受。
# ============================================================
_EMBEDDING_QUERY_CACHE: OrderedDict = OrderedDict()
_EMBEDDING_QUERY_CACHE_MAX_SIZE = 256


def _get_cached_query_embedding(text: str):
    """从 LRU 缓存中获取查询向量，未命中返回 None。"""
    return _EMBEDDING_QUERY_CACHE.get(text)


def _set_cached_query_embedding(text: str, embedding):
    """写入查询向量到 LRU 缓存，超出容量时淘汰最旧条目。"""
    _EMBEDDING_QUERY_CACHE[text] = embedding
    while len(_EMBEDDING_QUERY_CACHE) > _EMBEDDING_QUERY_CACHE_MAX_SIZE:
        _EMBEDDING_QUERY_CACHE.popitem(last=False)


def invalidate_embedding_cache():
    """清空 embedding 缓存（ embedding 模型切换时调用）。"""
    _EMBEDDING_QUERY_CACHE.clear()
    logger.info('[Embedding] 查询向量缓存已清空')


def _get_embedding_config() -> dict:
    """读取 Embedding 服务配置（从 .env）。

    Returns:
        dict: {api_key, base_url, model, dimensions}
    """
    return {
        'api_key': os.environ.get('EMBEDDING_API_KEY', '').strip(),
        'base_url': os.environ.get(
            'EMBEDDING_BASE_URL', 'https://api.siliconflow.cn/v1'
        ).strip(),
        'model': os.environ.get(
            'EMBEDDING_MODEL', 'BAAI/bge-large-zh-v1.5'
        ).strip(),
        'dimensions': int(os.environ.get('EMBEDDING_DIMENSIONS', '1024')),
    }


def is_embedding_available() -> bool:
    """检查 Embedding 服务是否可用（API Key 已配置）。"""
    return bool(_get_embedding_config()['api_key'])


@lru_cache(maxsize=1)
def get_embedding_llm():
    """获取 Embedding LLM 实例（单例，LangChain OpenAIEmbeddings）。

    Returns:
        OpenAIEmbeddings 实例

    Raises:
        RuntimeError: API Key 未配置

    说明：
        BAAI/bge-large-zh-v1.5 原生 1024 维，专为中文优化。
        仅当 dimensions 配置为非 0 时才传参（部分模型不支持 dimensions 参数）。
        如需切换模型，请在 .env 中修改 EMBEDDING_MODEL。
    """
    cfg = _get_embedding_config()
    if not cfg['api_key']:
        raise RuntimeError(
            "Embedding 服务不可用：未配置 EMBEDDING_API_KEY。"
            "请在 .env 中设置 SiliconFlow API Key。"
        )

    from langchain_openai import OpenAIEmbeddings

    kwargs = {
        'model': cfg['model'],
        'api_key': cfg['api_key'],
        'base_url': cfg['base_url'],
        # 禁用 LangChain 的 tiktoken 分词检查
        # 原因：LangChain 默认用 tiktoken 分词并传 encoding_format 参数，
        # SiliconFlow 不支持该参数会报 20015 错误。
        # bge-large-zh-v1.5 的 512 token 限制由 API 端自动截断处理。
        'check_embedding_ctx_length': False,
    }
    # 仅当 dimensions 配置为非 0 时才传参（部分模型不支持 dimensions 参数）
    if cfg['dimensions'] > 0:
        kwargs['dimensions'] = cfg['dimensions']
    return OpenAIEmbeddings(**kwargs)


def embed_query_sync(text: str) -> list[float]:
    """同步生成文本向量（1024 维）。

    Args:
        text: 待向量化的文本

    Returns:
        1024 维浮点列表
    """
    llm = get_embedding_llm()
    return llm.embed_query(text)


async def embed_query(text: str) -> list[float]:
    """异步生成文本向量（1024 维）。

    优先查 LRU 缓存，未命中才调用 embedding API。相同 query 在多轮工具调用
    场景下可省掉重复 HTTP 请求，显著降低 RAG 检索延迟。

    Args:
        text: 待向量化的文本

    Returns:
        1024 维浮点列表
    """
    if not text or not text.strip():
        text = '空'
    else:
        text = text[:500]  # bge-large-zh-v1.5 限制 512 token

    # 查缓存（命中直接返回，避免重复 HTTP 调用）
    cached = _get_cached_query_embedding(text)
    if cached is not None:
        return cached

    llm = get_embedding_llm()
    embedding = await llm.aembed_query(text)
    _set_cached_query_embedding(text, embedding)
    return embedding


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """批量异步生成文本向量。

    对输入文本做安全处理：
    - 空文本替换为占位符（避免 API 报错）
    - 超长文本截断到 500 字符（bge-large-zh-v1.5 限制 512 token）

    Args:
        texts: 文本列表

    Returns:
        向量列表（每个元素为 1024 维浮点列表）
    """
    # 安全处理：空文本替换 + 超长截断
    MAX_CHARS = 500  # bge-large-zh-v1.5 限制 512 token，中文约 1 token/字
    safe_texts = []
    for t in texts:
        if not t or not t.strip():
            safe_texts.append('空')
        else:
            safe_texts.append(t[:MAX_CHARS])

    llm = get_embedding_llm()
    return await llm.aembed_documents(safe_texts)
