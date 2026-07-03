# -*- coding: utf-8 -*-
"""证据图片打码服务：基于 Tesseract OCR 定位敏感文字区域并高斯模糊。"""
import os
import logging
import re
import io

from PIL import Image, ImageFilter
import pytesseract

logger = logging.getLogger(__name__)
TESSERACT_CMD = r'D:\tesseract\tesseract.exe'

# 敏感信息正则
SENSITIVE_PATTERNS = [
    (r'1[3-9]\d{9}', '手机号'),  # 手机号
    (r'[\u4e00-\u9fa5]{2,6}市[\u4e00-\u9fa5\d\w号路街]+', '地址'),
    (r'\d{17}[\dXx]', '身份证号'),
]


def mask_evidence_image(evidence):
    """对证据图片执行打码，返回打码后图片路径。"""
    if not evidence.image:
        return None
    image_path = evidence.image.path
    img = Image.open(image_path).convert('RGB')
    width, height = img.size
    mask_regions = []
    # 1. 尝试用 pytesseract image_to_data 获取文字坐标
    try:
        if os.path.exists(TESSERACT_CMD):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        data = pytesseract.image_to_data(
            img, lang='chi_sim+eng', output_type=pytesseract.Output.DICT
        )
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            if not text:
                continue
            for pattern, label in SENSITIVE_PATTERNS:
                if re.search(pattern, text):
                    x = data['left'][i]
                    y = data['top'][i]
                    w = data['width'][i]
                    h = data['height'][i]
                    mask_regions.append((x, y, w, h))
                    break
    except Exception as e:
        logger.warning(f"image_to_data 失败: {e}")
    # 2. 回退：底部 1/3 模糊
    if not mask_regions:
        mask_regions = [(0, int(height * 2 / 3), width, int(height / 3))]
        logger.info("回退底部 1/3 模糊")
    # 3. 对每个区域高斯模糊
    for x, y, w, h in mask_regions:
        region = img.crop((x, y, x + w, y + h))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=10))
        img.paste(blurred, (x, y))
    # 4. 保存
    from django.core.files.base import ContentFile
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=90)
    buf.seek(0)
    # 文件名
    orig_name = os.path.basename(image_path)
    masked_name = f'masked_{orig_name}'
    evidence.masked_image.save(masked_name, ContentFile(buf.getvalue()), save=False)
    evidence.mask_status = 'done'
    evidence.save()
    return evidence.masked_image.path


def mask_case_images(case):
    """批量打码该案件所有图片证据。"""
    results = []
    for ev in case.evidences.exclude(image='').exclude(image__isnull=True):
        ev.mask_status = 'pending'
        ev.save()
        try:
            mask_evidence_image(ev)
        except Exception as e:
            logger.error(f"证据 {ev.code} 打码失败: {e}")
            ev.mask_status = 'none'
            ev.save()
        results.append(ev)
    return results
