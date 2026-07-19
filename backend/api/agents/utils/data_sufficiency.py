# -*- coding: utf-8 -*-
"""投诉/反证文书生成前的输入数据充分性评估（Gate 3，input-quality-guard）。

由 complaint_node / respond_complaint_node 共用，避免对称重复实现。

设计目的（对齐 docs/input-quality-guard-spec.md 第 1.5 节）：
- Gate 2 已在 extract_node 拦截「全 other + 零字段」最严重情形；
- Gate 3 作为纵深防御，评估投诉文书生成前的数据充分性，在数据稀疏时把
  「稀疏数据告知段落」注入 LLM 重写 prompt，明确要求 LLM 如实声明数据局限
  而非捏造，并在质量报告 / 文书详情中记录充分性等级供前端 Banner 提示。
"""
from typing import Any


# 稀疏数据告知段落模板（追加到 LLM 重写 prompt 末尾，不修改既有 prompt 模板）
SPARSE_DATA_NOTICE_TEMPLATE = """
【重要提示 - 输入数据说明】
当前可用的证据字段有限（{fields_count} 个），事件时间线节点数 {chain_count} 个，案件描述长度 {desc_len} 字。

在此情况下，你的写作要求：
1. 仅使用上述已提供的信息，不得根据案件类型或常见场景推测、补充或编造任何事实
2. 对于无法从现有信息中确认的内容，使用“据当事人陈述”或“根据现有资料”等限定语
3. 如果某项诉求缺乏证据支撑，明确在文书中注明“尚待补充证据”而非凭空生成
4. 文书长度应与实际信息量相符，不要为了格式完整而填充虚假内容
"""


def assess_data_sufficiency(
    all_fields: list[dict],
    evidence_chain: list[dict],
    case_description: str,
    acknowledged_low_quality: bool = False,
) -> dict[str, Any]:
    """评估文书生成前的输入数据充分性。

    评分（满分 1.0）：
    - 字段维度：有效字段 ≥3 → 0.4；>0 → 0.2；0 → 缺失
    - 时间线维度：证据链节点 ≥2 → 0.3；==1 → 0.15；0 → 缺失
    - 描述维度：案件描述 ≥50 字 → 0.3；≥20 字 → 0.15；<20 字 → 缺失

    等级：score ≥ 0.6 sufficient / ≥ 0.3 sparse / else critically_sparse。

    Args:
        all_fields: 聚合后的全部抽取字段
        evidence_chain: 证据链节点列表
        case_description: 案件描述文本
        acknowledged_low_quality: 用户是否已在 Gate 2 确认低质量继续（信息性参数，
            不参与评分，仅供调用方决策与记录）

    Returns:
        {"score": float, "level": str, "missing_dimensions": list[str]}
    """
    score = 0.0
    missing: list[str] = []

    field_count = len(all_fields or [])
    if field_count >= 3:
        score += 0.4
    elif field_count > 0:
        score += 0.2
    else:
        missing.append("证据字段（订单号/金额/时间等）")

    chain_count = len(evidence_chain or [])
    if chain_count >= 2:
        score += 0.3
    elif chain_count == 1:
        score += 0.15
    else:
        missing.append("事件时间线")

    desc_len = len((case_description or "").strip())
    if desc_len >= 50:
        score += 0.3
    elif desc_len >= 20:
        score += 0.15
    else:
        missing.append("案件描述（过于简短）")

    if score >= 0.6:
        level = "sufficient"
    elif score >= 0.3:
        level = "sparse"
    else:
        level = "critically_sparse"

    return {
        "score": round(score, 2),
        "level": level,
        "missing_dimensions": missing,
    }


def build_sparse_data_notice(
    fields_count: int, chain_count: int, desc_len: int
) -> str:
    """构造稀疏数据告知段落（供 prompt 追加）。"""
    return SPARSE_DATA_NOTICE_TEMPLATE.format(
        fields_count=fields_count,
        chain_count=chain_count,
        desc_len=desc_len,
    )
