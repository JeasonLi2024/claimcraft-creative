# -*- coding: utf-8 -*-
"""Pydantic 结构化输出模型。

用于 LangChain with_structured_output()，替代旧版 JSON Mode。
覆盖 3 个 LLM 辅助节点：
- classify_node: ClassifyBatchResult
- extract_node: ExtractResult
- evidence_chain_node: EvidenceChainResult
"""
from typing import Literal

from pydantic import BaseModel, Field


# ===== 证据分类 Schema =====
class EvidenceClassification(BaseModel):
    """单条证据的分类结果。"""
    evidence_category: Literal[
        "chat_screenshot",      # 聊天截图
        "product_order",        # 商品订单
        "logistics_tracking",   # 物流跟踪
        "payment_record",       # 支付凭证
        "other",                # 其他
    ] = Field(description="证据材料类型")
    category_label: str = Field(description="中文类型标签，如 聊天截图/商品订单/物流跟踪/支付凭证/其他")
    confidence: float = Field(ge=0, le=1, description="分类置信度")
    reasoning: str = Field(description="分类依据简述")


class ClassifyBatchResult(BaseModel):
    """批量证据分类结果。"""
    results: list[EvidenceClassification] = Field(description="每条证据的分类结果，列表长度必须等于输入证据数量")


# ===== 字段抽取 Schema =====
class ExtractedFieldItem(BaseModel):
    """单个抽取字段。"""
    field_name: str = Field(
        description="字段名：订单号/金额/手机号/地址/时间/承诺话术/邮箱/物流单号/退款金额/商家名称"
    )
    field_value: str = Field(
        description="字段值（金额归一为数字字符串如 699，时间归一为 ISO 8601 如 2025-06-10 09:20）"
    )
    confidence: float = Field(ge=0, le=1, description="置信度，模糊推断≤0.6，明确匹配≥0.85")


class ExtractResult(BaseModel):
    """单条证据的字段抽取结果。"""
    fields: list[ExtractedFieldItem] = Field(description="抽取的字段列表")


# ===== 证据链 Schema =====
class ChainNode(BaseModel):
    """证据链节点。"""
    datetime: str = Field(description="ISO 8601 时间，如 2025-06-10 09:45")
    event: str = Field(description="事件描述")
    category: Literal["下单", "付款", "发货", "沟通", "退款", "承诺", "违约", "其他"]
    evidence_codes: list[str] = Field(description="关联的证据编号列表，如 ['EV001', 'EV002']")
    chain_order: int = Field(description="链路顺序，从 0 开始递增")


class EvidenceChainResult(BaseModel):
    """证据链构造结果。"""
    nodes: list[ChainNode] = Field(description="按时间排序的证据链节点")
    summary: str = Field(description="证据链整体摘要，含推断缺失时间的说明")
