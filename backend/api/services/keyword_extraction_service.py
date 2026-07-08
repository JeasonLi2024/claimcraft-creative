# -*- coding: utf-8 -*-
"""法条关键词 LLM 提取服务（v10 新增）。

为每条法条基于 content 生成独立的 keywords，替代整部法律共用 keywords 的现状。

设计要点：
- 使用 OpenAI 兼容接口（推荐 SiliconFlow 托管 Qwen3 系列）
- prompt 引导 LLM 从法条 content 提取 5-8 个独立关键词
- 关键词统一、合理且鲜明（覆盖核心法律术语 + 通俗表达）
- 并发处理（默认 8 并发，Semaphore 控制避免限流），增量保存（崩溃安全）
- 幂等：已生成过的不重复生成（通过版本标记区分）
"""
import os
import json
import asyncio
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)


# 关键词提取的 prompt 模板
KEYWORD_EXTRACTION_PROMPT = """你是法律文本分析专家。请从以下法律条文中提取 5-8 个独立关键词。

要求：
1. 关键词必须紧扣条文内容（不要泛化到整部法律）
2. 同时包含法律术语和通俗表达（如"欺诈"和"退一赔三"）
3. 简洁明了（2-6 个字为佳，避免长句）
4. 统一格式（中文名词或动名词，不带标点）
5. 鲜明区分（不同条款的关键词应有明显差异）

法律条文内容：
{content}

请仅输出 JSON 数组，不要其他解释。示例格式：
["欺诈", "退一赔三", "三倍赔偿", "消费者", "经营者", "500元"]
"""


def _get_keyword_llm_config() -> dict:
    """读取关键词提取 LLM 配置（从 .env）。"""
    return {
        'api_key': os.environ.get('LLM_KEYWORD_API_KEY', '').strip(),
        'base_url': os.environ.get(
            'LLM_KEYWORD_BASE_URL', 'https://api.siliconflow.cn/v1'
        ).strip(),
        'model': os.environ.get(
            'LLM_KEYWORD_MODEL', 'Qwen/Qwen3-8B'
        ).strip(),
        'temperature': float(os.environ.get('LLM_KEYWORD_TEMPERATURE', '0.1')),
        'timeout': int(os.environ.get('LLM_KEYWORD_TIMEOUT', '60')),
        'max_retries': int(os.environ.get('LLM_KEYWORD_MAX_RETRIES', '3')),
        'batch_size': int(os.environ.get('LLM_KEYWORD_BATCH_SIZE', '10')),
        'max_concurrent': int(os.environ.get('LLM_KEYWORD_MAX_CONCURRENT', '8')),
    }


def is_keyword_llm_available() -> bool:
    """检查关键词提取 LLM 是否可用。"""
    return bool(_get_keyword_llm_config()['api_key'])


# 模块级缓存 LLM 实例（避免每次调用重建，减少连接开销）
_cached_llm = None


def _get_keyword_llm():
    """获取关键词提取 LLM 实例（LangChain ChatOpenAI，模块级缓存）。"""
    global _cached_llm
    if _cached_llm is not None:
        return _cached_llm

    cfg = _get_keyword_llm_config()
    if not cfg['api_key']:
        raise RuntimeError(
            "关键词提取 LLM 不可用：未配置 LLM_KEYWORD_API_KEY。"
            "请在 .env 中设置。"
        )

    from langchain_openai import ChatOpenAI

    # Qwen3 系列默认开启 thinking 模式，导致响应慢（~20s/条）
    # 禁用 thinking 后降至 ~3s/条，2260 条 ÷ 8 并发 ≈ 14 分钟
    _cached_llm = ChatOpenAI(
        model=cfg['model'],
        api_key=cfg['api_key'],
        base_url=cfg['base_url'],
        temperature=cfg['temperature'],
        timeout=cfg['timeout'],
        max_retries=cfg['max_retries'],
        extra_body={'enable_thinking': False},
    )
    return _cached_llm


async def extract_keywords_from_content(content: str) -> Optional[list[str]]:
    """使用 LLM 从法条 content 提取独立关键词。

    Args:
        content: 法条条文内容

    Returns:
        关键词列表（5-8 个），失败返回 None
    """
    if not content or len(content) < 10:
        return None

    text = ''
    try:
        from langchain_core.messages import HumanMessage

        llm = _get_keyword_llm()
        prompt = KEYWORD_EXTRACTION_PROMPT.format(content=content)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text = response.content.strip()

        # 解析 JSON 数组（容忍 markdown 代码块）
        if text.startswith('```'):
            # 去除 ```json 或 ``` 包装
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1] if lines[-1].startswith('```') else lines[1:])

        keywords = json.loads(text)
        if not isinstance(keywords, list):
            return None

        # 清洗：去除空字符串、过长字符串、重复项
        cleaned = []
        seen = set()
        for kw in keywords:
            kw = str(kw).strip()
            if not kw or len(kw) > 20 or kw in seen:
                continue
            cleaned.append(kw)
            seen.add(kw)

        return cleaned if cleaned else None

    except json.JSONDecodeError as e:
        logger.warning(f"[关键词提取] JSON 解析失败: {e}, text={text[:100]}")
        return None
    except Exception as e:
        logger.error(f"[关键词提取] LLM 调用失败: {e}", exc_info=True)
        return None


async def _extract_one(
    article,
    semaphore: asyncio.Semaphore,
) -> tuple[object, Optional[list[str]]]:
    """并发安全的单条提取（受 Semaphore 限流）。"""
    async with semaphore:
        keywords = await extract_keywords_from_content(article.content or '')
        return (article, keywords)


async def extract_keywords_batch(
    articles: list,  # LawArticle 对象列表
    max_concurrent: int = 0,
    on_progress: Optional[Callable[[int, int, int, int], None]] = None,
) -> list[tuple[object, Optional[list[str]]]]:
    """批量并发提取关键词。

    使用 asyncio.Semaphore 控制并发度，避免触发 LLM 限流。
    相比串行处理，2260 条法条的耗时从 3-6 小时缩短到 ~25 分钟。

    Args:
        articles: LawArticle 对象列表
        max_concurrent: 最大并发数（0=从 .env 读取 LLM_KEYWORD_MAX_CONCURRENT，默认 8）
        on_progress: 进度回调 fn(done, total, success, failed)

    Returns:
        [(article, keywords), ...] 关键词为 None 表示提取失败
    """
    cfg = _get_keyword_llm_config()
    if max_concurrent <= 0:
        max_concurrent = cfg['max_concurrent']

    semaphore = asyncio.Semaphore(max_concurrent)
    total = len(articles)
    done = 0
    success = 0
    failed = 0
    results = []

    # 创建所有并发任务
    tasks = [_extract_one(a, semaphore) for a in articles]

    # as_completed 方式处理，便于回调进度
    for coro in asyncio.as_completed(tasks):
        article, keywords = await coro
        results.append((article, keywords))
        done += 1
        if keywords:
            success += 1
        else:
            failed += 1
        if on_progress:
            on_progress(done, total, success, failed)

    return results
