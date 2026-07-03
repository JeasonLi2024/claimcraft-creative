# -*- coding: utf-8 -*-
"""证据相关业务逻辑。"""
from api.models import Evidence


def generate_next_evidence_code(case):
    """根据案件现有证据数量生成下一个编号。

    查询该 case 的 evidences 数量，返回 f"E{count+1}"。
    """
    count = case.evidences.count()
    return f'E{count + 1}'
