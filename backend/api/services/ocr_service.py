# -*- coding: utf-8 -*-
"""OCR 服务：多策略 Pipeline + Mock 兜底。

跨平台路径解析（A3 修复）：
1. 优先使用环境变量 TESSERACT_CMD
2. 其次使用 shutil.which('tesseract') 在 PATH 中查找
3. 最后回退到 Windows 默认安装路径 D:\tesseract\tesseract.exe

C3 改造：接入 OCRPipeline，保留 ocr_image() 向后兼容接口。
"""
import os
import shutil
import logging

logger = logging.getLogger(__name__)


def _resolve_tesseract_cmd():
    """跨平台解析 Tesseract 可执行文件路径。"""
    # 1. 环境变量优先
    env_path = os.environ.get('TESSERACT_CMD')
    if env_path and os.path.exists(env_path):
        return env_path
    # 2. PATH 中查找（Linux/macOS/Git Bash/已加入 PATH 的 Windows）
    which_path = shutil.which('tesseract')
    if which_path:
        return which_path
    # 3. Windows 默认安装路径兜底
    win_default = r'D:\tesseract\tesseract.exe'
    if os.path.exists(win_default):
        return win_default
    return None


TESSERACT_CMD = _resolve_tesseract_cmd()

# Mock 预置识别文本（含各类字段样本）
MOCK_OCR_TEXT = """订单号：202506101234
下单时间：2025-06-10 09:20
金额：699 元
联系电话：13812345678
收货地址：北京市朝阳区XX路1号
商家承诺：48 小时内发货
物流状态：未揽收
"""


async def ocr_image_with_strategy(
    image_path: str, case_description: str = "", evidence_category: str = ""
) -> tuple[str, str, str]:
    """对图片执行多策略 OCR（异步），返回 (raw_text, corrected_text, strategy_name)。

    使用 OCRPipeline 按环境变量 OCR_STRATEGIES 配置的策略链尝试。
    全部失败则用 Mock 兜底。

    纠错规则：策略内部自管，确保「识别用啥纠错用啥」。
    - LLM Vision 策略：用同款 LLM 纠错（DeepSeek-OCR 等）
    - PaddleOCR-VL / 本地 PaddleOCR / Tesseract / Mock：不纠错（返回原文）

    Args:
        image_path: 图片本地路径（Django storage 管理，非用户直接输入）
        case_description: 案件描述（可选，透传给策略用于纠错上下文）
        evidence_category: 证据类别（透传给 LLMVisionStrategy 选 prompt）

    Returns:
        (raw_text, corrected_text, strategy_name) 三元组
    """
    from api.services.ocr_strategies import get_default_pipeline
    pipeline = get_default_pipeline()
    return await pipeline.recognize(image_path, case_description, evidence_category)


async def ocr_image(image_path: str, case_description: str = "") -> str:
    """对图片执行 OCR（异步），返回纠错后文本。

    向后兼容接口：内部 await ocr_image_with_strategy()。
    多策略 Pipeline + Mock 兜底 + 同款模型纠错。
    """
    raw_text, corrected_text, strategy = await ocr_image_with_strategy(
        image_path, case_description
    )
    logger.info(
        f"OCR 完成 (strategy={strategy}, "
        f"corrected={'yes' if corrected_text != raw_text else 'no'})"
    )
    return corrected_text
