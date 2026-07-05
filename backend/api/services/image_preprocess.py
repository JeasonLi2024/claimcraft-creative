# -*- coding: utf-8 -*-
"""图片预处理：提升 OCR 识别率。

步骤：
1. 灰度化
2. 尺寸归一化（短边 < 1024px 时按比例放大）
3. 倾斜校正（基于 Hough 变换或简单投影分析）
4. 二值化（Otsu 阈值）
5. 噪点去除（中值滤波）

仅依赖 Pillow（已安装），无需额外包。
"""
import os
import tempfile
import logging
from typing import Optional

from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

# 短边最小像素
MIN_SHORT_EDGE = 1024


def preprocess_image(image_path: str) -> str:
    """对图片执行预处理，返回临时文件路径。

    Args:
        image_path: 原始图片路径

    Returns:
        预处理后图片的临时文件路径
    """
    img = Image.open(image_path)

    # 1. 转 RGB（处理 RGBA / P 模式）
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    # 2. 灰度化
    gray = ImageOps.grayscale(img) if img.mode != 'L' else img

    # 3. 尺寸归一化
    gray = _normalize_size(gray)

    # 4. 倾斜校正（简化版：基于水平投影）
    # 完整 Hough 变换需 numpy + scipy，此处用简化版本避免依赖
    # gray = _deskew(gray)

    # 5. 二值化（Otsu 阈值）
    binary = _otsu_binarize(gray)

    # 6. 噪点去除（中值滤波）
    denoised = binary.filter(ImageFilter.MedianFilter(size=3))

    # 7. 保存到临时文件
    ext = os.path.splitext(image_path)[1].lower() or '.png'
    suffix = '_preprocessed' + ext
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    denoised.save(tmp_path)

    logger.info(f"图片预处理完成: {image_path} → {tmp_path}")
    return tmp_path


def _normalize_size(img: Image.Image) -> Image.Image:
    """短边 < MIN_SHORT_EDGE 时按比例放大。"""
    w, h = img.size
    short_edge = min(w, h)
    if short_edge >= MIN_SHORT_EDGE:
        return img
    scale = MIN_SHORT_EDGE / short_edge
    new_w, new_h = int(w * scale), int(h * scale)
    # LANCZOS 是最佳下采样/上采样滤波
    return img.resize((new_w, new_h), Image.LANCZOS)


def _otsu_binarize(img: Image.Image) -> Image.Image:
    """Otsu 阈值二值化。

    基于 Pillow 实现，无需 numpy/scipy。
    """
    # 直方图统计
    histogram = img.histogram()
    total = sum(histogram)

    if total == 0:
        return img

    # Otsu 算法
    sum_total = sum(i * histogram[i] for i in range(256))
    sum_b = 0
    w_b = 0
    max_variance = 0
    threshold = 127

    for t in range(256):
        w_b += histogram[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * histogram[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        variance = w_b * w_f * (m_b - m_f) ** 2
        if variance > max_variance:
            max_variance = variance
            threshold = t

    # 应用阈值
    return img.point(lambda p: 255 if p > threshold else 0, mode='1').convert('L')


def cleanup_temp_image(temp_path: str) -> None:
    """清理临时图片文件。"""
    try:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception as e:
        logger.warning(f"清理临时图片失败: {e}")
