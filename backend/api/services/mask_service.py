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


# 风险等级映射（对齐设计文档 §5.4）：身份证=高，手机号/地址=中，其余=低。
_RISK_BY_TYPE = {'id_card': 'high', 'phone': 'medium', 'address': 'medium'}


def _risk_level(sensitive_type):
    return _RISK_BY_TYPE.get(sensitive_type, 'low')


def _dedup_signature(text):
    """返回文本命中的敏感值签名集合（脱敏后，不含原文），用于同一证据内跨字段去重。

    以「匹配到的敏感值本身」而非整段脱敏文案为准：同一手机号出现在证据描述与 OCR 文本中
    （周边文字不同）应折叠为一项。
    """
    value = str(text or '')
    sig = []
    for pattern, kind in SENSITIVE_PATTERNS:
        for match in pattern.finditer(value):
            sig.append((kind, mask_text(match.group(0))))
    return frozenset(sig)


def _scan_text(text, *, source_type, source_label, source_id,
               evidence_code=None, include_original=False):
    """扫描单段文本；命中敏感信息则返回一个结果项，否则返回 None。

    结果项统一携带 source_type / source_label / source_id / risk_level，供前端按来源
    分组展示与跳转核对（设计文档 §5.1）。默认只下发脱敏预览，不含原文。
    """
    original = str(text or '').strip()
    if not original:
        return None
    types = find_sensitive_types(original)
    if not types:
        return None
    primary = types[0]
    item = {
        'evidence_code': evidence_code,
        'source_type': source_type,
        'source_label': source_label,
        'source_id': source_id,
        'type': primary,
        'types': types,
        'risk_level': _risk_level(primary),
        'masked': mask_text(original),
        '_dedup': _dedup_signature(original),
    }
    if include_original:
        item['original'] = original
    return item


def mask_case_sensitive_info(case, include_original=False):
    """扫描案件可进入交付物的文本来源，返回命中的脱敏结果。

    覆盖来源（设计文档 §5.1）：证据描述 / 物证说明 / OCR 全文 / OCR 摘要 /
    抽取字段 / 时间线 / 最新文书。每项带 ``source_type``、``source_label``、
    ``source_id``、``risk_level``，前端据此分组与跳转。

    默认不向客户端下发原始敏感文本；仅受控内部场景可请求 ``include_original=True``。
    向后兼容：证据描述项仍保留原有键与「has_sensitive_info 但无命中→type=unknown」行为，
    且始终排在结果最前。
    """
    results = []
    seen = set()

    def _add(item):
        if not item:
            return
        # 同一证据内跨文本字段（描述/OCR/摘要等）出现相同敏感值时折叠为一项，
        # 避免同一手机号被重复列出；无证据归属的来源按 (来源, id) 区分。
        sig = item.pop('_dedup', frozenset())
        if item.get('evidence_code'):
            key = ('ev', item['evidence_code'], sig)
        else:
            key = (item['source_type'], item['source_id'], sig)
        if key in seen:
            return
        seen.add(key)
        results.append(item)

    # 1. 证据文本：描述（含 has_sensitive_info 兼容分支）/ 物证说明 / OCR 全文 / OCR 摘要
    for evidence in case.evidences.all().order_by('order', 'id'):
        code = evidence.code
        original_desc = evidence.description or ''
        desc_types = find_sensitive_types(original_desc)
        if desc_types or evidence.has_sensitive_info:
            item = {
                'evidence_code': code,
                'source_type': 'evidence',
                'source_label': f'{code} · 证据描述',
                'source_id': evidence.id,
                'type': desc_types[0] if desc_types else 'unknown',
                'types': desc_types,
                'risk_level': _risk_level(desc_types[0]) if desc_types else 'low',
                'masked': mask_text(original_desc),
                '_dedup': _dedup_signature(original_desc),
            }
            if include_original:
                item['original'] = original_desc
            _add(item)
        _add(_scan_text(
            getattr(evidence, 'physical_note', ''),
            source_type='evidence', source_label=f'{code} · 物证说明',
            source_id=evidence.id, evidence_code=code, include_original=include_original,
        ))
        _add(_scan_text(
            getattr(evidence, 'extracted_text', ''),
            source_type='ocr', source_label=f'{code} · OCR 文本',
            source_id=evidence.id, evidence_code=code, include_original=include_original,
        ))
        _add(_scan_text(
            getattr(evidence, 'ocr_summary', ''),
            source_type='ocr_summary', source_label=f'{code} · OCR 摘要',
            source_id=evidence.id, evidence_code=code, include_original=include_original,
        ))

    # 2. 抽取字段
    from api.models import ExtractedField
    fields = (
        ExtractedField.objects.filter(evidence__case=case)
        .select_related('evidence').order_by('evidence__order', 'id')
    )
    for field in fields:
        _add(_scan_text(
            field.field_value,
            source_type='extracted_field',
            source_label=f'{field.evidence.code} · {field.field_name or "抽取字段"}',
            source_id=field.id, evidence_code=field.evidence.code,
            include_original=include_original,
        ))

    # 3. 时间线
    for node in case.timeline_nodes.order_by('order', 'id'):
        _add(_scan_text(
            node.event, source_type='timeline', source_label='时间线',
            source_id=node.id, include_original=include_original,
        ))

    # 4. 最新文书（best-effort：投诉书优先，其次答辩书）
    try:
        complaint = case.complaint_templates.order_by('-id').first()
        respond = case.respond_templates.order_by('-id').first()
        doc = complaint or respond
        if doc is not None:
            label = '最新投诉书' if complaint is not None else '最新答辩书'
            _add(_scan_text(
                doc.content, source_type='document', source_label=label,
                source_id=doc.id, include_original=include_original,
            ))
    except Exception:
        pass

    return results


# ===== 轻量缓存（仅供页面 GET，见 §17.1；检测确定性，签名失效即可） =====

# 检测规则/覆盖范围版本；调整检测逻辑时 +1 使旧缓存失效。
_SCAN_POLICY_VERSION = 'p1'


def _scan_signature(case):
    """基于廉价聚合查询生成案件内容签名（不读全文）。

    证据用 count + max(updated_at)（auto_now，覆盖描述/OCR/摘要/物证的原地编辑）；
    抽取字段 / 时间线 / 文书用 count + max(id)（覆盖新增与时间线重建）。
    字段/时间线的原地编辑在 TTL 内可能未反映，由 TTL 兜底——属轻量取舍。
    """
    from django.db.models import Count, Max
    from api.models import ExtractedField

    ev = case.evidences.aggregate(c=Count('id'), m=Max('updated_at'))
    ef = ExtractedField.objects.filter(evidence__case=case).aggregate(
        c=Count('id'), m=Max('id')
    )
    tl = case.timeline_nodes.aggregate(c=Count('id'), m=Max('id'))
    cm = case.complaint_templates.aggregate(m=Max('id'))
    rm = case.respond_templates.aggregate(m=Max('id'))
    return '|'.join([
        _SCAN_POLICY_VERSION,
        f"e{ev['c']}:{ev['m']}",
        f"f{ef['c']}:{ef['m']}",
        f"t{tl['c']}:{tl['m']}",
        f"c{cm['m']}",
        f"r{rm['m']}",
    ])


def scan_case_sensitive_info_cached(case):
    """带轻量缓存的文本扫描（页面 GET 用）。

    以案件内容签名为缓存键，内容变化 → 签名变化 → 自动失效；检测确定性，命中缓存与
    重算结果一致（「重新扫描」在内容未变时返回同结果即正确）。TTL 兜底防陈旧。
    直接调用 ``mask_case_sensitive_info`` 仍不走缓存（供测试与受控场景）。
    """
    from django.core.cache import cache

    signature = _scan_signature(case)
    key = f'privacy:scan:{case.id}'
    cached = cache.get(key)
    if isinstance(cached, dict) and cached.get('sig') == signature:
        return cached['items']
    items = mask_case_sensitive_info(case)
    try:
        cache.set(key, {'sig': signature, 'items': items}, timeout=600)
    except Exception:
        pass
    return items
