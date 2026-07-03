# -*- coding: utf-8 -*-
"""OCR 服务：Tesseract 优先，失败回退 Mock。"""
import os
import logging

logger = logging.getLogger(__name__)

TESSERACT_CMD = r'D:\tesseract\tesseract.exe'

# Mock 预置识别文本（含各类字段样本）
MOCK_OCR_TEXT = """订单号：202506101234
下单时间：2025-06-10 09:20
金额：699 元
联系电话：13812345678
收货地址：北京市朝阳区XX路1号
商家承诺：48 小时内发货
物流状态：未揽收
"""


def ocr_image(image_path):
    """对图片执行 OCR，返回识别文本。Tesseract 优先，失败回退 Mock。"""
    # 1. 检查 Tesseract 是否可用
    if os.path.exists(TESSERACT_CMD):
        try:
            import pytesseract
            from PIL import Image
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, lang='chi_sim+eng')
            logger.info("Tesseract OCR 成功")
            return text.strip()
        except Exception as e:
            logger.warning(f"Tesseract OCR 失败，回退 Mock: {e}")
    else:
        logger.warning(f"Tesseract 不存在于 {TESSERACT_CMD}，使用 Mock OCR")
    # 2. 回退 Mock
    return MOCK_OCR_TEXT
