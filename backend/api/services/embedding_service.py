# -*- coding: utf-8 -*-
"""Embedding 服务（v10 新增）。

通过 SiliconFlow OpenAI 兼容接口调用 Qwen/Qwen3-VL-Embedding-8B 生成文本向量。

设计要点：
- 复用 LangChain OpenAIEmbeddings（与 LangChain 生态无缝衔接）
- 配置从 .env 读取（EMBEDDING_*），无硬编码
- 向量维度 1024（与 pgvector 索引一致）
- 同步 + 异步双接口（embed_query / aembed_query）
"""
import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


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
            'EMBEDDING_MODEL', 'Qwen/Qwen3-VL-Embedding-8B'
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
        SiliconFlow 的 Qwen3-VL-Embedding-8B 不支持 dimensions 参数（付费限制），
        故不传 dimensions，使用模型原生维度 4096。
        如需切换为支持 dimensions 的模型，请在 .env 中修改 EMBEDDING_MODEL。
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

    Args:
        text: 待向量化的文本

    Returns:
        1024 维浮点列表
    """
    llm = get_embedding_llm()
    return await llm.aembed_query(text)


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """批量异步生成文本向量。

    Args:
        texts: 文本列表

    Returns:
        向量列表（每个元素为 1024 维浮点列表）
    """
    llm = get_embedding_llm()
    return await llm.aembed_documents(texts)
