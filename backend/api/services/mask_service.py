# -*- coding: utf-8 -*-
"""敏感信息打码相关业务逻辑。"""
import re

from api.models import Evidence


# 手机号：11 位数字，保留前 3 后 4，中间 ****
_PHONE_PATTERN = re.compile(r'1[3-9]\d{9}')

# 身份证号：18 位数字（最后一位可能是 X），保留前 3 后 4
_ID_CARD_PATTERN = re.compile(r'\d{17}[\dXx]')

# 地址：匹配"XX市XX区"后跟内容，简化为保留"XX市"后打码
_ADDRESS_PATTERN = re.compile(r'([\u4e00-\u9fa5]{2,6}市)[\u4e00-\u9fa5\d\w号路街]+')


def mask_text(text):
    """用正则识别并打码敏感信息。

    - 手机号：保留前 3 后 4，中间 ****
    - 身份证号：保留前 3 后 4
    - 地址：保留"XX市"后打码
    """
    if not text:
        return text

    # 手机号
    text = _PHONE_PATTERN.sub(
        lambda m: m.group()[:3] + '****' + m.group()[-4:], text
    )

    # 身份证号
    text = _ID_CARD_PATTERN.sub(
        lambda m: m.group()[:3] + '*' * 11 + m.group()[-4:], text
    )

    # 地址
    text = _ADDRESS_PATTERN.sub(
        lambda m: m.group(1) + '******', text
    )

    return text


def detect_sensitive_type(text):
    """检测文本中包含的敏感信息类型。

    优先级：身份证号 > 手机号 > 地址（身份证号正则覆盖手机号前缀）

    Returns:
        'id_card' | 'phone' | 'address' | 'unknown'
    """
    if not text:
        return 'unknown'
    if _ID_CARD_PATTERN.search(text):
        return 'id_card'
    if _PHONE_PATTERN.search(text):
        return 'phone'
    if _ADDRESS_PATTERN.search(text):
        return 'address'
    return 'unknown'


def mask_case_sensitive_info(case):
    """收集该案件所有含敏感信息的证据描述，返回打码结果列表。

    返回 [{"evidence_code": ..., "type": ..., "original": ..., "masked": ...}]
    """
    result = []
    evidences = case.evidences.filter(has_sensitive_info=True).order_by('order', 'id')
    for ev in evidences:
        original = ev.description or ''
        result.append({
            'evidence_code': ev.code,
            'type': detect_sensitive_type(original),
            'original': original,
            'masked': mask_text(original),
        })
    return result
