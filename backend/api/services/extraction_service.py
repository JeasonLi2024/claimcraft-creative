# -*- coding: utf-8 -*-
"""关键信息抽取服务：从 OCR 文本中用正则抽取关键字段。"""
import re

from api.models import ExtractedField

# 字段抽取规则：(field_name, regex_pattern, confidence)
EXTRACTION_RULES = [
    ('订单号', r'订单号[：:]\s*(\d+)', 0.9),
    ('金额', r'(\d+(?:\.\d+)?)\s*元', 0.85),
    ('手机号', r'(1[3-9]\d{9})', 0.9),
    ('地址', r'([\u4e00-\u9fa5]{2,6}市[\u4e00-\u9fa5\d\w号路街]+)', 0.7),
    ('时间', r'(\d{4}-\d{2}-\d{2}[\s\d:]+)', 0.8),
    ('承诺话术', r'(\d+\s*小时.*?发货)', 0.75),
]


def extract_fields(evidence):
    """从 evidence.extracted_text 抽取关键字段，创建 ExtractedField 记录。"""
    text = evidence.extracted_text or ''
    # 先清除旧记录
    evidence.extracted_fields.all().delete()
    created = []
    for field_name, pattern, confidence in EXTRACTION_RULES:
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip()
            obj = ExtractedField.objects.create(
                evidence=evidence,
                field_name=field_name,
                field_value=value,
                confidence=confidence
            )
            created.append(obj)
    return created
