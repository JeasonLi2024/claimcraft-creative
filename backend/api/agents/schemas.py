# -*- coding: utf-8 -*-
"""Pydantic 结构化输出模型。

用于 LangChain with_structured_output()，替代旧版 JSON Mode。
覆盖 3 个 LLM 辅助节点：
- classify_node: ClassifyBatchResult
- extract_node: ExtractResult
- evidence_chain_node: EvidenceChainResult
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ===== 证据分类 Schema =====
class EvidenceClassification(BaseModel):
    """单条证据的分类结果。"""
    evidence_category: Literal[
        "chat_screenshot",          # 聊天截图
        "product_order",            # 商品订单
        "logistics_tracking",       # 物流跟踪
        "payment_record",           # 支付凭证
        "service_contract",         # 服务合同
        "work_record",             # 施工记录
        "communication_record",    # 沟通记录
        "contract_document",        # 合同文件
        "medical_record",           # 医疗记录
        "other",                    # 其他
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


# ===== 节点统一输出契约（NodeResult，Task 1.1）=====
# 用于 8 个节点（preclassify/ocr/classify/extract/review/evidence_chain/
# complaint/respond_complaint）的统一返回结构。节点返回 partial update dict，
# 其中 node_result 字段存储 NodeResult.model_dump() 的 dict（避免 TypedDict
# 直接依赖 Pydantic 模型导致的循环 import）。
class Metrics(BaseModel):
    """节点执行指标。"""
    duration_ms: int = Field(ge=0, description="节点执行耗时（毫秒）")
    model_calls: int = Field(ge=0, default=0, description="LLM 调用次数")
    api_calls: int = Field(ge=0, default=0, description="外部 API 调用次数")
    tokens_used: int = Field(ge=0, default=0, description="token 消耗")
    retries: int = Field(ge=0, default=0, description="重试次数（RetryPolicy 触发）")


class ProvenanceItem(BaseModel):
    """数据来源追溯项。"""
    node: str = Field(description="产生此项的节点名")
    evidence_id: int | None = Field(default=None, description="关联证据 ID")
    field_name: str | None = Field(default=None, description="关联字段名")
    source_ref: str = Field(description="来源引用标识（如 evidence_code:字段:区域）")
    ts: str = Field(description="ISO 8601 时间戳")


class Warning(BaseModel):
    """警告项。"""
    code: str = Field(description="警告代码，如 ocr.low_confidence")
    message: str = Field(description="警告消息")
    severity: Literal["info", "warning", "blocking"] = Field(default="warning")
    evidence_id: int | None = Field(default=None)
    stage: str | None = Field(default=None)


class Issue(BaseModel):
    """统一问题项（合并自 warnings + errors）。"""
    code: str = Field(description="问题代码")
    message: str = Field(description="问题描述")
    severity: Literal["info", "warning", "blocking"] = Field(description="严重程度")
    evidence_id: int | None = Field(default=None)
    stage: str | None = Field(default=None)
    recoverable: bool = Field(default=True, description="是否可恢复（用户可修复或自动重试）")


class QualityReport(BaseModel):
    """质量报告。"""
    score: float = Field(ge=0, le=1, description="质量分（0-1）")
    coverage: float = Field(ge=0, le=1, default=1.0, description="覆盖率（0-1）")
    status: Literal["pass", "warn", "fail"] = Field(description="质量状态")
    blocking_issues: list[Issue] = Field(default_factory=list, description="阻塞问题列表")
    details: dict = Field(default_factory=dict, description="扩展详情（节点自定义指标）")


class NodeResult(BaseModel):
    """节点统一输出契约（每个节点完成时返回）。"""
    node: str = Field(description="节点名")
    data: dict = Field(default_factory=dict, description="节点主体数据（业务字段）")
    quality: QualityReport = Field(description="质量报告")
    warnings: list[Warning] = Field(default_factory=list)
    errors: list[Issue] = Field(default_factory=list, description="错误列表（升级为 Issue 结构）")
    provenance: list[ProvenanceItem] = Field(default_factory=list)
    metrics: Metrics = Field(description="执行指标")


class DocumentVersion(BaseModel):
    """文书版本（占位，Task 4.1 详细实现）。"""
    document_id: int
    version: int
    content: str
    changelog: str = ""
    created_by_type: Literal["user", "ai"] = "ai"
    created_by_id: int | None = None
    created_at: str = Field(description="ISO 8601 时间戳")
    workflow_version: str = ""


# ===== 工作流介入 Schema（Task 2.1）=====
class WorkflowInterventionSchema(BaseModel):
    """WorkflowIntervention 序列化模型。"""
    id: int
    case_id: int
    intervention_type: Literal[
        "quality_review",
        "user_pause",
        "legal_confirmation",
        "missing_information",
    ]
    stage: str
    status: Literal["pending", "submitted", "cancelled", "expired"]
    base_revision: int
    form_schema: dict
    initial_values: dict
    impact: dict
    submitted_values: dict | None = None
    created_at: datetime
    submitted_at: datetime | None = None
    cancelled_at: datetime | None = None
    expires_at: datetime | None = None

    class Config:
        from_attributes = True  # Pydantic v2 替代 orm_mode

    @classmethod
    def from_model(cls, intervention: "WorkflowIntervention") -> "WorkflowInterventionSchema":
        """从 Django model 构造 Schema。"""
        return cls(
            id=intervention.id,
            case_id=intervention.case_id,
            intervention_type=intervention.intervention_type,
            stage=intervention.stage,
            status=intervention.status,
            base_revision=intervention.base_revision,
            form_schema=intervention.form_schema or {},
            initial_values=intervention.initial_values or {},
            impact=intervention.impact or {},
            submitted_values=intervention.submitted_values,
            created_at=intervention.created_at,
            submitted_at=intervention.submitted_at,
            cancelled_at=intervention.cancelled_at,
            expires_at=intervention.expires_at,
        )
