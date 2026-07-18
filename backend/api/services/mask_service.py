# -*- coding: utf-8 -*-
"""敏感信息检测与文本打码。"""
import re

# 使用数字边界断言，避免误伤订单号、银行卡号和流水号中的子串。
PHONE_PATTERN = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')
ID_CARD_PATTERN = re.compile(
    r'(?<!\d)(?:\d{6})(?:18|19|20)\d{2}'
    r'(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)'
)

# 地址属于弱结构信息：仅在出现省/自治区/市/区县/乡镇街道等行政区划词时识别，
# 并限制长度，避免把后续整段中文说明一并吞掉。
ADDRESS_PATTERN = re.compile(
    r'((?:[\u4e00-\u9fff]{2,8}(?:省|自治区|特别行政区))?'
    r'[\u4e00-\u9fff]{2,8}(?:市|自治州|地区|盟))'
    r'([\u4e00-\u9fff0-9A-Za-z\-]{2,40}'
    r'(?:区|县|旗|镇|乡|街道|路|街|巷|村|社区|号|室))'
)

SENSITIVE_PATTERNS = (
    (ID_CARD_PATTERN, 'id_card'),
    (PHONE_PATTERN, 'phone'),
    (ADDRESS_PATTERN, 'address'),
)


def find_sensitive_types(text):
    """返回文本中命中的全部敏感类型，按身份证、手机号、地址排序。"""
    value = str(text or '')
    return [kind for pattern, kind in SENSITIVE_PATTERNS if pattern.search(value)]


def contains_sensitive_info(text):
    return bool(find_sensitive_types(text))


def mask_text(text):
    """对身份证号、手机号和结构化地址执行边界安全的替换。"""
    if not text:
        return text

    value = str(text)
    # 必须先处理身份证，避免特殊身份证前缀被手机号规则局部命中。
    value = ID_CARD_PATTERN.sub(
        lambda match: match.group()[:3] + '*' * 11 + match.group()[-4:],
        value,
    )
    value = PHONE_PATTERN.sub(
        lambda match: match.group()[:3] + '****' + match.group()[-4:],
        value,
    )
    value = ADDRESS_PATTERN.sub(
        lambda match: match.group(1) + '******',
        value,
    )
    return value


def detect_sensitive_type(text):
    """返回文本中优先级最高的敏感类型。"""
    types = find_sensitive_types(text)
    return types[0] if types else 'unknown'


def mask_case_sensitive_info(case, include_original=False):
    """扫描案件所有证据描述，返回实际命中的脱敏结果。

    默认不向客户端下发原始敏感文本；只有显式用于受控内部场景时才可请求
    ``include_original=True``。
    """
    results = []
    for evidence in case.evidences.all().order_by('order', 'id'):
        original = evidence.description or ''
        types = find_sensitive_types(original)
        if not types and not evidence.has_sensitive_info:
            continue
        item = {
            'evidence_code': evidence.code,
            'type': types[0] if types else 'unknown',
            'types': types,
            'masked': mask_text(original),
        }
        if include_original:
            item['original'] = original
        results.append(item)
    return results
