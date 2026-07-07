# -*- coding: utf-8 -*-
"""OCR 大模型统一配置层。

所有 OCR 相关配置（LLM 视觉 OCR / PaddleOCR-VL）都集中在此处读取，
业务代码（strategies）只通过函数获取结构化 dict，避免散落的 os.environ.get 调用。

设计原则：
- 业务代码 0 硬编码：所有 URL、模型名、超时、开关、Prompt 都从 .env 读取
- 默认值集中：仅在此处保留 fallback 默认值，便于维护
- 强类型：返回 dict 中的字段类型固定（int / bool / str）
"""
import os


# ============================================================
# PaddleOCR-VL 云端（aistudio 在线服务）
# ============================================================

PADDLEOCR_VL_DEFAULTS = {
    # 任务提交地址（一般无需修改，aistudio 官方端点）
    'base_url': 'https://paddleocr.aistudio-app.com/api/v2/ocr/jobs',
    # 模型名（aistudio 平台 PaddleOCR-VL-1.6 是文档识别主力模型）
    'model': 'PaddleOCR-VL-1.6',
    # 版面/文档预处理开关（默认关闭，按需开启会增加耗时和费用）
    'use_doc_orientation': False,
    'use_doc_unwarping': False,
    'use_chart_recognition': False,
    # 轮询参数
    'poll_interval': 3,
    'poll_timeout': 180,
    # 单次 HTTP 请求超时（提交任务 / 查询状态 / 下载结果共用）
    'request_timeout': 60,
}


def _str_to_bool(s: str, default: bool = False) -> bool:
    """将 .env 中的字符串转换为 bool。

    接受 true/1/yes/on（大小写不敏感），其他值或空串使用 default。
    """
    if not s:
        return default
    return s.strip().lower() in ('true', '1', 'yes', 'on')


def get_paddleocr_vl_config() -> dict:
    """读取 PaddleOCR-VL 云端 OCR 策略的全部配置。

    Returns:
        dict: {
            token, base_url, model,
            use_doc_orientation, use_doc_unwarping, use_chart_recognition,
            poll_interval, poll_timeout, request_timeout
        }
    """
    return {
        'token': os.environ.get('PADDLEOCR_VL_TOKEN', '').strip(),
        'base_url': os.environ.get(
            'PADDLEOCR_VL_BASE_URL', PADDLEOCR_VL_DEFAULTS['base_url']
        ).strip() or PADDLEOCR_VL_DEFAULTS['base_url'],
        'model': os.environ.get(
            'PADDLEOCR_VL_MODEL', PADDLEOCR_VL_DEFAULTS['model']
        ).strip() or PADDLEOCR_VL_DEFAULTS['model'],
        'use_doc_orientation': _str_to_bool(
            os.environ.get('PADDLEOCR_VL_USE_DOC_ORIENTATION', ''),
            PADDLEOCR_VL_DEFAULTS['use_doc_orientation'],
        ),
        'use_doc_unwarping': _str_to_bool(
            os.environ.get('PADDLEOCR_VL_USE_DOC_UNWARPING', ''),
            PADDLEOCR_VL_DEFAULTS['use_doc_unwarping'],
        ),
        'use_chart_recognition': _str_to_bool(
            os.environ.get('PADDLEOCR_VL_USE_CHART_RECOGNITION', ''),
            PADDLEOCR_VL_DEFAULTS['use_chart_recognition'],
        ),
        'poll_interval': int(os.environ.get(
            'PADDLEOCR_VL_POLL_INTERVAL',
            str(PADDLEOCR_VL_DEFAULTS['poll_interval'])
        )),
        'poll_timeout': int(os.environ.get(
            'PADDLEOCR_VL_POLL_TIMEOUT',
            str(PADDLEOCR_VL_DEFAULTS['poll_timeout'])
        )),
        'request_timeout': int(os.environ.get(
            'PADDLEOCR_VL_REQUEST_TIMEOUT',
            str(PADDLEOCR_VL_DEFAULTS['request_timeout'])
        )),
    }


# ============================================================
# LLM 视觉 OCR（DeepSeek-OCR / GPT-4o / Qwen-VL 等）
# ============================================================

# 默认 Prompt：识别图片中所有文字，保持原始结构，仅输出文字
DEFAULT_LLM_OCR_PROMPT = (
    "请识别并提取这张图片中的所有文字内容，保持原始结构（换行/标点），"
    "仅输出识别到的文字，不要其他解释。"
)

# 默认最大图片大小（MB），超过则等比压缩
DEFAULT_LLM_OCR_MAX_IMAGE_MB = 10


def get_llm_ocr_prompt() -> str:
    """读取 LLM 视觉 OCR 的 Prompt。

    优先级：.env 中 LLM_OCR_PROMPT > DEFAULT_LLM_OCR_PROMPT
    """
    custom = os.environ.get('LLM_OCR_PROMPT', '').strip()
    return custom or DEFAULT_LLM_OCR_PROMPT


def get_llm_ocr_prompt_by_category(category: str = "") -> str:
    """按证据类型获取 OCR prompt。

    优先级：.env 中 LLM_OCR_PROMPT（全局覆盖） > 类型化 prompt > DEFAULT_LLM_OCR_PROMPT

    Args:
        category: 证据类别（chat_screenshot/product_order/logistics_tracking/
                  payment_record/invoice/other）

    Returns:
        对应类型的 OCR prompt，无匹配时回退到通用 prompt。
    """
    # 若 .env 显式配置了全局 LLM_OCR_PROMPT，优先使用（向后兼容）
    custom = os.environ.get('LLM_OCR_PROMPT', '').strip()
    if custom:
        return custom

    if category:
        from api.agents.prompts.templates import OCR_PROMPT_BY_CATEGORY
        if category in OCR_PROMPT_BY_CATEGORY:
            return OCR_PROMPT_BY_CATEGORY[category]

    return DEFAULT_LLM_OCR_PROMPT


def get_llm_ocr_max_image_mb() -> int:
    """读取 LLM 视觉 OCR 的最大图片大小限制（MB）。

    .env 中 LLM_OCR_MAX_IMAGE_MB 留空或非法值时使用 DEFAULT_LLM_OCR_MAX_IMAGE_MB。
    """
    val = os.environ.get('LLM_OCR_MAX_IMAGE_MB', '').strip()
    if not val:
        return DEFAULT_LLM_OCR_MAX_IMAGE_MB
    try:
        return max(1, int(val))
    except ValueError:
        return DEFAULT_LLM_OCR_MAX_IMAGE_MB
