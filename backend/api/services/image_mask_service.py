# -*- coding: utf-8 -*-
"""证据图片打码：Tesseract 定位敏感文字后使用不透明遮盖。"""
import io
import logging
import os
import re
import shutil
import uuid

import pytesseract
from PIL import Image, ImageDraw
from django.core.files.base import ContentFile
from django.db import transaction

from api.services.mask_service import contains_sensitive_info

logger = logging.getLogger(__name__)


def _resolve_tesseract_cmd():
    env_path = os.environ.get('TESSERACT_CMD')
    if env_path and os.path.exists(env_path):
        return env_path
    which_path = shutil.which('tesseract')
    if which_path:
        return which_path
    win_default = r'D:\tesseract\tesseract.exe'
    return win_default if os.path.exists(win_default) else None


def _normalize_ocr_text(value):
    return re.sub(r'[\s\-—_]+', '', str(value or ''))


def _line_regions(data):
    """合并同一 OCR 行的词，支持被空格切开的手机号和身份证号。"""
    groups = {}
    count = len(data.get('text', []))
    for index in range(count):
        text = str(data['text'][index] or '').strip()
        if not text:
            continue
        key = (
            data.get('block_num', [0] * count)[index],
            data.get('par_num', [0] * count)[index],
            data.get('line_num', [0] * count)[index],
        )
        groups.setdefault(key, []).append({
            'text': text,
            'left': int(data['left'][index]),
            'top': int(data['top'][index]),
            'width': int(data['width'][index]),
            'height': int(data['height'][index]),
        })

    regions = []
    for words in groups.values():
        normalized = _normalize_ocr_text(''.join(word['text'] for word in words))
        if not contains_sensitive_info(normalized):
            continue
        left = min(word['left'] for word in words)
        top = min(word['top'] for word in words)
        right = max(word['left'] + word['width'] for word in words)
        bottom = max(word['top'] + word['height'] for word in words)
        regions.append((left, top, right - left, bottom - top))
    return regions


def _expand_region(region, image_size):
    x, y, width, height = region
    image_width, image_height = image_size
    padding = max(4, int(height * 0.2))
    return (
        max(0, x - padding),
        max(0, y - padding),
        min(image_width, x + width + padding),
        min(image_height, y + height + padding),
    )


def _encode_lossless(image):
    """无损编码遮罩图，优先 WebP（体积更小），不可用时回退 PNG。

    两者均从 RGB 重新编码，天然丢弃原图 EXIF/GPS 等元数据（设计文档 §6.3），
    且无损避免 JPEG 在遮盖边缘产生压缩伪影。
    """
    try:
        buffer = io.BytesIO()
        image.save(buffer, format='WEBP', lossless=True, method=6)
        return buffer.getvalue(), 'webp'
    except Exception as exc:
        logger.warning('WebP 无损编码不可用，回退 PNG: %s', exc)
        buffer = io.BytesIO()
        image.save(buffer, format='PNG', optimize=True)
        return buffer.getvalue(), 'png'


def mask_evidence_image(evidence):
    """从原图生成脱敏副本。

    区分三种情况，避免把「干净图片」误判为失败（设计文档 阶段 A 纠偏）：
    - OCR 不可用 / 解析异常 → 抛错（视为处理失败，由调用方置 failed）；
    - OCR 成功且命中敏感文字 → 遮盖后输出；
    - OCR 成功但无敏感内容 → 并非失败，仍输出一份去元数据的无损副本并置 done。
    """
    if not evidence.image:
        raise ValueError('证据没有原始图片')

    image_path = evidence.image.path
    with Image.open(image_path) as source:
        image = source.convert('RGB')

    tesseract_cmd = _resolve_tesseract_cmd()
    if not tesseract_cmd:
        raise RuntimeError('Tesseract 不可用，无法安全定位敏感信息')
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    # image_to_data 抛错（如图片损坏）会向上传播 → 调用方标记为 failed（真实失败）。
    data = pytesseract.image_to_data(
        image,
        lang='chi_sim+eng',
        output_type=pytesseract.Output.DICT,
    )
    mask_regions = _line_regions(data)

    # 无命中不是失败：不遮盖，仍输出去元数据的干净副本。
    if mask_regions:
        draw = ImageDraw.Draw(image)
        for region in mask_regions:
            draw.rectangle(_expand_region(region, image.size), fill=(24, 24, 24))

    payload, ext = _encode_lossless(image)
    masked_name = f'masked_{evidence.id}_{uuid.uuid4().hex[:8]}.{ext}'
    old_masked = evidence.masked_image.name if evidence.masked_image else ''
    evidence.masked_image.save(
        masked_name,
        ContentFile(payload),
        save=False,
    )
    evidence.mask_status = 'done'
    evidence.save(update_fields=['masked_image', 'mask_status'])

    if old_masked and old_masked != evidence.masked_image.name:
        try:
            evidence.masked_image.storage.delete(old_masked)
        except Exception as exc:
            logger.warning('旧打码图清理失败 (evidence=%s): %s', evidence.id, exc)
    return evidence.masked_image.path


def mask_case_images(case, force=False):
    """批量打码图片；已完成的记录默认幂等跳过，并记录失败状态。"""
    results = []
    evidence_ids = list(
        case.evidences.exclude(image='').exclude(image__isnull=True)
        .order_by('order', 'id').values_list('id', flat=True)
    )
    from api.models import Evidence

    for evidence_id in evidence_ids:
        with transaction.atomic():
            evidence = Evidence.objects.select_for_update().get(
                pk=evidence_id,
                case=case,
            )
            if evidence.mask_status == 'done' and evidence.masked_image and not force:
                results.append(evidence)
                continue
            # 注意：不跳过 pending —— 上一次请求崩溃会遗留 pending，若跳过将永久卡死；
            # 同步处理下 pending 视为可重跑，天然恢复卡住状态。
            evidence.mask_status = 'pending'
            evidence.save(update_fields=['mask_status'])

        try:
            mask_evidence_image(evidence)
        except Exception as exc:
            logger.exception('证据 %s 打码失败: %s', evidence.code, exc)
            evidence.mask_status = 'failed'
            evidence.save(update_fields=['mask_status'])
        results.append(evidence)
    return results
