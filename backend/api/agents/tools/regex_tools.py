# -*- coding: utf-8 -*-
"""正则兜底工具：封装既有 extraction_service 的 6 条抽取规则。

保留原始规则，供 extract_node 在 LLM 不可用时降级使用。
"""
import re

# 字段抽取规则：(field_name, regex_pattern, confidence)
# 与 extraction_service.EXTRACTION_RULES 保持一致
REGEX_RULES = [
    ('订单号', r'订单号[：:]\s*(\d+)', 0.9),
    ('金额', r'(\d+(?:\.\d+)?)\s*元', 0.85),
    ('手机号', r'(1[3-9]\d{9})', 0.9),
    ('地址', r'([\u4e00-\u9fa5]{2,6}市[\u4e00-\u9fa5\d\w号路街]+)', 0.7),
    ('时间', r'(\d{4}-\d{2}-\d{2}[\s\d:]+)', 0.8),
    ('承诺话术', r'(\d+\s*小时.*?发货)', 0.75),
]


def extract_fields_regex(text: str) -> list[dict]:
    """从文本用正则抽取字段，返回 list[dict] 格式。

    返回结构与 LLM 抽取保持一致：
    [{"field_name", "field_value", "confidence", "source": "regex"}]
    """
    if not text:
        return []
    results = []
    for field_name, pattern, confidence in REGEX_RULES:
        # 使用 finditer 支持多值匹配
        for match in re.finditer(pattern, text):
            value = match.group(1).strip()
            if value:
                results.append({
                    "field_name": field_name,
                    "field_value": value,
                    "confidence": confidence,
                    "source": "regex",
                })
    return results


def merge_fields(regex_fields: list[dict], llm_fields: list[dict]) -> list[dict]:
    """合并正则与 LLM 抽取结果。

    策略：
    - 同字段名 + 同字段值：去重，保留 confidence 高的
    - 同字段名 + 不同值：保留全部（多值场景）
    - LLM 字段 confidence < 0.6 丢弃
    """
    merged = []
    seen = set()  # (field_name, field_value) 去重键

    # 按 confidence 降序排列，优先保留高置信度
    all_fields = sorted(
        regex_fields + llm_fields,
        key=lambda f: f.get("confidence", 0.0),
        reverse=True,
    )

    for f in all_fields:
        # LLM 字段低置信度丢弃
        if f.get("source") == "llm" and f.get("confidence", 0.0) < 0.6:
            continue
        key = (f["field_name"], f["field_value"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(f)

    return merged
