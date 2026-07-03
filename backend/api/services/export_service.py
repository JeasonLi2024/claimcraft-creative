# -*- coding: utf-8 -*-
"""导出文本生成相关业务逻辑。"""
from api.services import complaint_service, timeline_service, mask_service


def generate_export_text(case, template_type='platform', masked=False):
    """组装导出文本。

    包含：
    1. 投诉文本（调用 complaint_service）
    2. 证据清单（列出所有证据编号、类型、描述）
    3. 时间线（按时间排序列出所有节点）

    如果 masked=True，对证据描述调用 mask_text。

    返回纯文本字符串。
    """
    lines = []

    # 1. 投诉文本
    complaint = complaint_service.generate_complaint(case, template_type)
    lines.append('=' * 60)
    lines.append('一、投诉文本')
    lines.append('=' * 60)
    if complaint:
        lines.append(f'【标题】{complaint["title"]}')
        lines.append('')
        lines.append('【正文】')
        lines.append(complaint['content'])
    else:
        lines.append(f'（未找到模板类型：{template_type}）')
    lines.append('')

    # 2. 证据清单
    lines.append('=' * 60)
    lines.append('二、证据清单')
    lines.append('=' * 60)
    evidences = case.evidences.order_by('order', 'id')
    for ev in evidences:
        desc = ev.description
        if masked:
            desc = mask_service.mask_text(desc)
        sensitive_flag = '（含敏感信息）' if ev.has_sensitive_info else ''
        lines.append(
            f'[{ev.code}] 类型：{ev.evidence_type}{sensitive_flag}'
        )
        lines.append(f'    时间：{ev.source_time.strftime("%Y-%m-%d %H:%M")}')
        lines.append(f'    描述：{desc}')
        lines.append('')

    # 3. 时间线
    lines.append('=' * 60)
    lines.append('三、时间线')
    lines.append('=' * 60)
    timeline_nodes = timeline_service.get_sorted_timeline(case)
    for node in timeline_nodes:
        dt_str = node.datetime.strftime('%Y-%m-%d %H:%M')
        related = f'（关联证据：{node.related_evidence_codes}）' if node.related_evidence_codes else ''
        lines.append(f'[{dt_str}] {node.event}{related}')
        lines.append('')

    return '\n'.join(lines)
