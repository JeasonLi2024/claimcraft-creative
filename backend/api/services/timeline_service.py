# -*- coding: utf-8 -*-
"""时间线相关业务逻辑。"""
from datetime import datetime

from api.models import TimelineNode


def get_sorted_timeline(case):
    """返回按 datetime 排序的时间线节点列表。"""
    return list(case.timeline_nodes.order_by('datetime'))


def rebuild_timeline(case):
    """从证据时间字段自动重建时间线，保留手动节点。"""
    # 1. 删除旧自动节点
    case.timeline_nodes.filter(auto_generated=True).delete()
    # 2. 从证据 source_time 生成节点
    new_nodes = []
    for evidence in case.evidences.all():
        if evidence.source_time:
            node = TimelineNode.objects.create(
                case=case,
                datetime=evidence.source_time,
                event=f'[{evidence.code}] {evidence.description}',
                related_evidence_codes=evidence.code,
                auto_generated=True
            )
            new_nodes.append(node)
        # 从抽取的时间字段生成
        time_fields = evidence.extracted_fields.filter(field_name='时间')
        for tf in time_fields:
            try:
                dt = datetime.strptime(tf.field_value.strip()[:19], '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                try:
                    dt = datetime.strptime(tf.field_value.strip()[:16], '%Y-%m-%d %H:%M')
                except (ValueError, TypeError):
                    continue
            node = TimelineNode.objects.create(
                case=case,
                datetime=dt,
                event=f'[{evidence.code}] 抽取时间: {tf.field_value}',
                related_evidence_codes=evidence.code,
                auto_generated=True
            )
            new_nodes.append(node)
    # 3. 合并手动+自动，按时间排序
    all_nodes = case.timeline_nodes.all().order_by('datetime')
    return list(all_nodes)
