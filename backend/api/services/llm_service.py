# -*- coding: utf-8 -*-
"""LLM 服务：多供应商可切换的统一抽象层。

所有供应商均通过 OpenAI 兼容协议接入（DeepSeek / Qwen / GLM / OpenAI 等）。
通过环境变量配置，运行时切换。

环境变量（按场景拆分，详见 .env 文件）：

【文本 LLM】—— 投诉生成、字段抽取降级、证据分类、证据链构造等
- LLM_PROVIDER:  deepseek | siliconflow | qwen | glm | openai | custom
- LLM_API_KEY:   API Key
- LLM_BASE_URL:  OpenAI 兼容协议的 base URL
- LLM_MODEL:     模型名（如 deepseek-chat / qwen-max / glm-4 / gpt-4o-mini）
- LLM_TEMPERATURE / LLM_TIMEOUT / LLM_MAX_RETRIES

【OCR 视觉 LLM】—— 多模态图像识别（证据图片 OCR），独立于文本 LLM
- LLM_OCR_PROVIDER / LLM_OCR_API_KEY / LLM_OCR_BASE_URL / LLM_OCR_MODEL
- LLM_OCR_TEMPERATURE / LLM_OCR_TIMEOUT / LLM_OCR_MAX_RETRIES

【LLM 通用调用参数】—— 跨场景共享的重试策略
- LLM_COMMON_RETRY_MAX_ATTEMPTS: 应用层重试次数（默认 3）
- LLM_COMMON_RETRY_WAIT_MIN:     指数退避起始等待秒（默认 2）
- LLM_COMMON_RETRY_WAIT_MAX:     指数退避最大等待秒（默认 10）

如果 LLM_OCR_* 未显式配置，自动回退到对应的 LLM_*（向后兼容），
但日志中会提示「OCR 未独立配置，复用文本 LLM」。

核心接口：
- get_llm(): 工厂函数，返回 ChatOpenAI 实例（带重试 + 超时）
- chat(messages, schema=None): 统一调用入口
- chat_with_retry(messages, schema=None): 带 tenacity 重试
- get_scenario_config(scenario): 按场景读取配置（scenario: 'text' | 'ocr'）
- get_common_retry_config(): 读取跨场景共享的重试参数

降级策略：
- 对应场景的 API Key 未配置时，is_scenario_available(scenario) 返回 False，
  调用方应回退到既有正则/模板逻辑（见各 service 的 *_with_llm 函数）。
"""
import os
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# 供应商预设映射（仅当未显式配置 *_BASE_URL 时使用）
PROVIDER_PRESETS = {
    'deepseek': {
        'base_url': 'https://api.deepseek.com/v1',
        'model': 'deepseek-chat',
    },
    'siliconflow': {
        'base_url': 'https://api.siliconflow.cn/v1',
        'model': 'deepseek-ai/DeepSeek-V3',
    },
    'qwen': {
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'model': 'qwen-max',
    },
    'glm': {
        'base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'model': 'glm-4',
    },
    'openai': {
        'base_url': 'https://api.openai.com/v1',
        'model': 'gpt-4o-mini',
    },
}

# 场景 -> 环境变量前缀
SCENARIO_PREFIX = {
    'text': 'LLM_',
    'ocr':  'LLM_OCR_',
    'captioner': 'LLM_CAPTIONER_',
}

# OCR 场景默认值（与文本 LLM 解耦的预设）
OCR_DEFAULT_MODEL = 'deepseek-ai/DeepSeek-OCR'
OCR_DEFAULT_TEMPERATURE = 0.1
OCR_DEFAULT_TIMEOUT = 60

# Captioner 场景默认值（视觉预分类+摘要，Qwen3-Omni Captioner）
CAPTIONER_DEFAULT_MODEL = 'Qwen/Qwen3-Omni-30B-A3B-Captioner'
CAPTIONER_DEFAULT_TEMPERATURE = 0.1
CAPTIONER_DEFAULT_TIMEOUT = 30


def _get_config() -> dict:
    """从环境变量读取文本 LLM 配置，应用供应商预设。"""
    return get_scenario_config('text')


def get_scenario_config(scenario: str) -> dict:
    """按场景读取 LLM 配置。

    Args:
        scenario: 'text'（文本生成） | 'ocr'（视觉 OCR）

    Returns:
        dict: {provider, api_key, base_url, model, temperature, timeout, max_retries}
    """
    if scenario not in SCENARIO_PREFIX:
        raise ValueError(f"未知 LLM 场景: {scenario}，可选: {list(SCENARIO_PREFIX)}")

    prefix = SCENARIO_PREFIX[scenario]

    provider = os.environ.get(f'{prefix}PROVIDER', '').lower()

    # OCR 场景默认供应商
    if not provider:
        provider = 'siliconflow' if scenario == 'ocr' else 'deepseek'

    preset = PROVIDER_PRESETS.get(provider, {})

    # 默认模型：OCR / captioner 场景有独立默认值
    if scenario == 'ocr':
        default_model = OCR_DEFAULT_MODEL
        default_temperature = OCR_DEFAULT_TEMPERATURE
        default_timeout = OCR_DEFAULT_TIMEOUT
    elif scenario == 'captioner':
        default_model = CAPTIONER_DEFAULT_MODEL
        default_temperature = CAPTIONER_DEFAULT_TEMPERATURE
        default_timeout = CAPTIONER_DEFAULT_TIMEOUT
    else:
        default_model = preset.get('model', 'deepseek-chat')
        default_temperature = 0.3
        default_timeout = 30

    # captioner 场景默认供应商
    if not provider and scenario == 'captioner':
        provider = 'siliconflow'

    return {
        'provider': provider,
        'api_key': os.environ.get(f'{prefix}API_KEY', ''),
        'base_url': os.environ.get(f'{prefix}BASE_URL') or preset.get('base_url', ''),
        'model': os.environ.get(f'{prefix}MODEL') or default_model,
        'temperature': float(os.environ.get(f'{prefix}TEMPERATURE', str(default_temperature))),
        'timeout': int(os.environ.get(f'{prefix}TIMEOUT', str(default_timeout))),
        'max_retries': int(os.environ.get(f'{prefix}MAX_RETRIES', '3')),
    }


def is_llm_available() -> bool:
    """判断文本 LLM 是否可用（API Key 已配置）。"""
    return bool(_get_config()['api_key'])


def get_common_retry_config() -> dict:
    """读取跨场景共享的 LLM 重试参数（从 .env 的 LLM_COMMON_* 读取）。

    Returns:
        dict: {max_attempts, wait_min, wait_max}
    """
    return {
        'max_attempts': int(os.environ.get('LLM_COMMON_RETRY_MAX_ATTEMPTS', '3') or '3'),
        'wait_min': int(os.environ.get('LLM_COMMON_RETRY_WAIT_MIN', '2') or '2'),
        'wait_max': int(os.environ.get('LLM_COMMON_RETRY_WAIT_MAX', '10') or '10'),
    }


def is_scenario_available(scenario: str) -> bool:
    """判断指定场景的 LLM 是否可用。

    如果 LLM_OCR_* 未显式配置，自动回退到 LLM_*，复用其 api_key。
    """
    cfg = get_scenario_config(scenario)
    if cfg['api_key']:
        return True
    # OCR / captioner 场景回退到文本 LLM
    if scenario in ('ocr', 'captioner') and is_llm_available():
        logger.info(f"{scenario} 场景未独立配置，复用文本 LLM 配置")
        return True
    return False


# 场景 -> ChatOpenAI 实例缓存
_LLM_INSTANCES: dict[str, Any] = {}


def get_llm():
    """工厂函数：返回文本 LLM 的 ChatOpenAI 实例（带重试 + 超时）。

    使用 OpenAI 兼容协议，可对接 DeepSeek / Qwen / GLM / OpenAI 等。
    首次调用时初始化并缓存实例。
    """
    return get_scenario_llm('text')


def get_scenario_llm(scenario: str):
    """按场景获取 ChatOpenAI 实例（懒加载 + 缓存）。"""
    global _LLM_INSTANCES
    if scenario in _LLM_INSTANCES:
        return _LLM_INSTANCES[scenario]

    if not is_scenario_available(scenario):
        raise RuntimeError(
            f"LLM [{scenario}] 不可用：未配置 API Key。请在 .env 中设置 "
            f"{'LLM_API_KEY' if scenario == 'text' else 'LLM_OCR_API_KEY (或 LLM_API_KEY 作为回退)'}。"
        )

    # OCR / captioner 场景：若独立 API Key 未配置，复用 LLM_API_KEY
    cfg = get_scenario_config(scenario)
    if scenario in ('ocr', 'captioner') and not cfg['api_key']:
        text_cfg = _get_config()
        cfg = {**cfg, 'api_key': text_cfg['api_key']}
        logger.info(
            f"{scenario} 场景复用文本 LLM 凭证 (provider={cfg['provider']}, model={cfg['model']})"
        )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise RuntimeError(
            "未安装 langchain-openai。请运行 pip install langchain-openai"
        ) from e

    _LLM_INSTANCES[scenario] = ChatOpenAI(
        model=cfg['model'],
        api_key=cfg['api_key'],
        base_url=cfg['base_url'],
        temperature=cfg['temperature'],
        timeout=cfg['timeout'],
        max_retries=cfg['max_retries'],
    )
    logger.info(
        f"LLM [{scenario}] 初始化成功: provider={cfg['provider']}, "
        f"model={cfg['model']}, base_url={cfg['base_url']}"
    )
    return _LLM_INSTANCES[scenario]


# 重置缓存（用于测试或多环境切换）
def reset_llm_cache(scenario: Optional[str] = None):
    """重置 LLM 实例缓存。scenario=None 时清空所有。"""
    global _LLM_INSTANCES
    if scenario is None:
        _LLM_INSTANCES.clear()
    else:
        _LLM_INSTANCES.pop(scenario, None)


def chat(messages: list, schema: Optional[dict] = None) -> Any:
    """统一调用入口。

    Args:
        messages: OpenAI 消息列表 [{"role": "...", "content": "..."}]
        schema:   非 None 时启用 JSON Mode，返回解析后的 dict；
                  None 时返回纯字符串

    Returns:
        schema=None → str
        schema非None → dict（解析失败时返回 {"raw": "...", "error": "..."}）
    """
    llm = get_llm()
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

    # 转换消息格式
    lc_messages = []
    for m in messages:
        role = m.get('role', 'user')
        content = m.get('content', '')
        if role == 'system':
            lc_messages.append(SystemMessage(content=content))
        elif role == 'assistant':
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))

    if schema is not None:
        # JSON Mode：在 prompt 中明确要求 JSON 输出
        schema_hint = (
            "\n\n请严格输出符合以下 JSON Schema 的 JSON（仅输出 JSON，不要其他文本）：\n"
            + json.dumps(schema, ensure_ascii=False, indent=2)
        )
        if lc_messages:
            last = lc_messages[-1]
            lc_messages[-1] = HumanMessage(content=last.content + schema_hint)

    response = llm.invoke(lc_messages)
    text = response.content if hasattr(response, 'content') else str(response)

    if schema is not None:
        return _parse_json_response(text)
    return text


def chat_with_retry(messages: list, schema: Optional[dict] = None) -> Any:
    """带显式重试的调用（LangChain ChatOpenAI 内部已有 max_retries，
    此函数提供额外的应用层重试，使用 tenacity 指数退避）。

    重试参数从 .env 的 LLM_COMMON_RETRY_* 读取（跨场景共享）。

    失败时返回降级值：
    - schema=None → 返回空字符串
    - schema非None → 返回 {"raw": "", "error": "..."}
    """
    try:
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    except ImportError:
        # tenacity 未安装时直接调用
        try:
            return chat(messages, schema)
        except Exception as e:
            logger.error(f"LLM 调用失败（无 tenacity 重试）: {e}")
            return "" if schema is None else {"raw": "", "error": str(e)}

    retry_cfg = get_common_retry_config()

    @retry(
        stop=stop_after_attempt(retry_cfg['max_attempts']),
        wait=wait_exponential(multiplier=1, min=retry_cfg['wait_min'], max=retry_cfg['wait_max']),
        retry=retry_if_exception_type(Exception),
        reraise=False,
    )
    def _call():
        return chat(messages, schema)

    try:
        return _call()
    except Exception as e:
        logger.error(f"LLM 调用最终失败（已重试 {retry_cfg['max_attempts']} 次）: {e}")
        return "" if schema is None else {"raw": "", "error": str(e)}


def _parse_json_response(text: str) -> dict:
    """解析 LLM 的 JSON 输出，容错处理 Markdown 代码块包裹。"""
    if not text:
        return {"raw": "", "error": "empty response"}
    # 去除可能的 ```json ... ``` 包裹
    cleaned = text.strip()
    if cleaned.startswith('```'):
        lines = cleaned.split('\n')
        # 去首行 ```json 和末行 ```
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        cleaned = '\n'.join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"LLM JSON 解析失败: {e}；原始: {text[:200]}")
        return {"raw": text, "error": f"JSON parse failed: {e}"}
