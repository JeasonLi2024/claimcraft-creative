# -*- coding: utf-8 -*-
"""质量门服务。

按四业务阶段实现质量规则，返回 `QualityReport`。
阻塞时调用方应使用 `interrupt()` 暂停 graph（不抛异常）。

四阶段（对齐设计文档 5.2 节）：
1. `material_understanding`（材料理解）：preclassify + ocr + classify
   - OCR 成功率 ≥ 0.8
   - 分类平均置信度 ≥ 0.7
   - 无证据被分类为 `"other"`
2. `fact_checking`（事实核对）：extract + review
   - 字段完整率 ≥ 0.6
   - 低置信度字段数 ≤ 10（或经人工校正后 = 0）
   - 校正后无必填字段为空
3. `case_organization`（案件组织）：evidence_chain
   - 引用覆盖率 ≥ 0.8（链中引用证据数 / 总证据数）
   - 时间断点数 ≤ 3（相邻事件间隔 > 7 天视为断点）
4. `document_generation`（文书生成）：complaint / respond_complaint
   - 法条引用真实存在（占位，Task 4.2 实现 `LawRetriever`）
   - 金额一致性（占位，Task 4.2 实现）
   - 文书内容非空

接入说明：
- SubTask 2.3.2（节点调用本服务）：本任务仅创建服务，节点接入在 Task 2.2 完成。
  节点可在 Task 1.2 已有 `quality` 基础上，调用本服务重新评估完整质量报告。
- SubTask 2.3.3（`warnings + errors` 统一为 `issues: list[Issue]`）：已在 Task 1.2 完成
  （节点返回 `issues` 字段，合并自 `warnings + errors`），此处不再重复实现。
- SubTask 2.3.4（`interrupt()` 暂停 graph）：`should_block_on_quality` 返回 `True` 时，
  调用方应在节点中使用 `interrupt()` 暂停 graph（不抛异常，对齐 Task 0.4 错误处理 4 层策略）。

约束：
- 不依赖 DB：服务函数纯计算，调用方负责传入已完成节点的结果数据。
- 不引入新依赖：仅使用标准库 + Django + Pydantic。
- 占位实现：法条验证 + 金额一致性在 Task 4.2 完整实现，本服务用占位参数
  （`legal_references_valid` / `amount_consistent` 默认 `None`，不触发 issue）。
"""
from datetime import datetime
from typing import Literal

from api.agents.schemas import Issue, QualityReport


QualityStatus = Literal["pass", "warn", "fail"]


def _build_report(
    issues: list[Issue],
    coverage: float,
    stage: str,
    details: dict,
) -> QualityReport:
    """根据 issues 列表计算 score + status，构造 `QualityReport`。

    评分规则：
    - 每个 issue 扣 0.1 分
    - 每个 blocking issue 额外扣 0.2 分
    - score 裁剪到 [0.0, 1.0]

    状态规则：
    - 任意 blocking issue → `fail`
    - 仅 warning / info issue → `warn`
    - 无 issue → `pass`
    """
    blocking_count = sum(1 for i in issues if i.severity == "blocking")
    score = 1.0 - (len(issues) * 0.1) - (blocking_count * 0.2)
    score = max(0.0, min(1.0, score))
    status: QualityStatus = "fail" if blocking_count > 0 else ("warn" if issues else "pass")

    return QualityReport(
        score=score,
        coverage=max(0.0, min(1.0, coverage)),
        status=status,
        blocking_issues=[i for i in issues if i.severity == "blocking"],
        details=details,
    )


def evaluate_material_understanding(
    preclassify_results: list[dict],
    ocr_results: list[dict],
    classify_results: list[dict],
) -> QualityReport:
    """评估材料理解阶段质量。

    Args:
        preclassify_results: 预分类结果（占位，目前未直接参与规则，后续可扩展）。
        ocr_results: OCR 结果列表，每项应含 `ocr_status`（`"done"` / `"success"` 视为成功）。
        classify_results: 分类结果列表，每项应含 `confidence` 与 `evidence_category`。

    Returns:
        `QualityReport`：`coverage` = OCR 成功率；`details` 含三项指标。
    """
    issues: list[Issue] = []

    # 规则 1：OCR 成功率 ≥ 0.8
    total_evidence = max(len(ocr_results), 1)
    ocr_success_count = sum(
        1
        for r in ocr_results
        if r.get("ocr_status") == "done" or r.get("ocr_status") == "success"
    )
    ocr_success_rate = ocr_success_count / total_evidence
    if ocr_success_rate < 0.8:
        issues.append(Issue(
            code="material.ocr_low_success_rate",
            message=f"OCR 成功率 {ocr_success_rate:.0%} 低于阈值 80%",
            severity="blocking" if ocr_success_rate < 0.5 else "warning",
            stage="material_understanding",
            recoverable=True,
        ))

    # 规则 2：分类平均置信度 ≥ 0.7
    avg_confidence = 0.0
    if classify_results:
        avg_confidence = sum(r.get("confidence", 0) for r in classify_results) / len(classify_results)
        if avg_confidence < 0.7:
            issues.append(Issue(
                code="material.low_classify_confidence",
                message=f"分类平均置信度 {avg_confidence:.2f} 低于阈值 0.70",
                severity="warning",
                stage="material_understanding",
                recoverable=True,
            ))

    # 规则 3：无证据被分类为 "other"
    other_count = sum(1 for r in classify_results if r.get("evidence_category") == "other")
    if other_count > 0:
        issues.append(Issue(
            code="material.uncategorized_evidence",
            message=f"{other_count} 个证据被分类为 other",
            severity="warning",
            stage="material_understanding",
            recoverable=True,
        ))

    return _build_report(
        issues=issues,
        coverage=ocr_success_rate,
        stage="material_understanding",
        details={
            "ocr_success_rate": ocr_success_rate,
            "avg_classify_confidence": avg_confidence,
            "other_count": other_count,
        },
    )


def evaluate_fact_checking(
    extract_results: list[dict],
    review_decision: dict | None = None,
) -> QualityReport:
    """评估事实核对阶段质量。

    Args:
        extract_results: 字段抽取结果列表，每项应含 `fields` 列表
            （`field_value` / `confidence`）。
        review_decision: 人工复核决策（可选），含 `corrections` 列表。

    Returns:
        `QualityReport`：`coverage` = 字段完整率；`details` 含三项指标。
    """
    issues: list[Issue] = []

    # 规则 1：字段完整率 ≥ 0.6
    total_fields = 0
    filled_fields = 0
    low_confidence_count = 0
    for er in extract_results:
        for f in er.get("fields", []):
            total_fields += 1
            if f.get("field_value"):
                filled_fields += 1
            if f.get("confidence", 1.0) < 0.7:
                low_confidence_count += 1

    field_completeness = filled_fields / max(total_fields, 1)
    if field_completeness < 0.6:
        issues.append(Issue(
            code="fact.low_field_completeness",
            message=f"字段完整率 {field_completeness:.0%} 低于阈值 60%",
            severity="blocking" if field_completeness < 0.3 else "warning",
            stage="fact_checking",
            recoverable=True,
        ))

    # 规则 2：低置信度字段数 ≤ 10
    if low_confidence_count > 10:
        issues.append(Issue(
            code="fact.too_many_low_confidence",
            message=f"低置信度字段数 {low_confidence_count} 超过阈值 10",
            severity="warning",
            stage="fact_checking",
            recoverable=True,
        ))

    # 规则 3：校正后无必填字段为空（如 review_decision 存在）
    if review_decision:
        corrections = review_decision.get("corrections", [])
        # 简化：仅检查校正数量
        if not corrections and low_confidence_count > 0:
            issues.append(Issue(
                code="fact.uncorrected_low_confidence",
                message=f"仍有 {low_confidence_count} 个低置信度字段未校正",
                severity="warning",
                stage="fact_checking",
                recoverable=True,
            ))

    return _build_report(
        issues=issues,
        coverage=field_completeness,
        stage="fact_checking",
        details={
            "field_completeness": field_completeness,
            "low_confidence_count": low_confidence_count,
            "total_fields": total_fields,
        },
    )


def evaluate_case_organization(
    evidence_chain: list[dict],
    total_evidence_count: int,
) -> QualityReport:
    """评估案件组织阶段质量。

    Args:
        evidence_chain: 证据链节点列表，每项应含 `evidence_codes`（list[str]）
            和可选 `datetime`（ISO 8601 字符串）。
        total_evidence_count: 案件总证据数（用于计算引用覆盖率）。

    Returns:
        `QualityReport`：`coverage` = 引用覆盖率；`details` 含三项指标。
    """
    issues: list[Issue] = []

    # 规则 1：引用覆盖率 ≥ 0.8
    chain_evidence_codes: set[str] = set()
    for node in evidence_chain:
        for code in node.get("evidence_codes", []):
            chain_evidence_codes.add(code)
    coverage = len(chain_evidence_codes) / max(total_evidence_count, 1)
    if coverage < 0.8:
        issues.append(Issue(
            code="case.low_coverage",
            message=f"证据链引用覆盖率 {coverage:.0%} 低于阈值 80%",
            severity="warning",
            stage="case_organization",
            recoverable=True,
        ))

    # 规则 2：时间断点数 ≤ 3
    timestamps: list[datetime] = []
    for node in evidence_chain:
        ts_str = node.get("datetime")
        if ts_str:
            try:
                timestamps.append(datetime.fromisoformat(ts_str))
            except (ValueError, TypeError):
                pass
    timestamps.sort()
    gaps = 0
    for i in range(1, len(timestamps)):
        delta = timestamps[i] - timestamps[i - 1]
        if delta.days > 7:
            gaps += 1
    if gaps > 3:
        issues.append(Issue(
            code="case.too_many_time_gaps",
            message=f"证据链时间断点 {gaps} 超过阈值 3",
            severity="warning",
            stage="case_organization",
            recoverable=True,
        ))

    return _build_report(
        issues=issues,
        coverage=coverage,
        stage="case_organization",
        details={
            "coverage": coverage,
            "time_gaps": gaps,
            "chain_length": len(evidence_chain),
        },
    )


def evaluate_document_generation(
    complaint_draft: dict | None,
    legal_references_valid: bool | None = None,  # 占位，Task 4.2 实现
    amount_consistent: bool | None = None,  # 占位，Task 4.2 实现
) -> QualityReport:
    """评估文书生成阶段质量。

    Args:
        complaint_draft: 文书草稿 dict，应含 `content` 字符串。
        legal_references_valid: 法条引用是否真实存在。
            `None` = 未校验（占位，不触发 issue）；`False` = 验证失败。
            Task 4.2 实现 `LawRetriever` 后由调用方传入。
        amount_consistent: 文书金额是否与抽取字段一致。
            `None` = 未校验（占位，不触发 issue）；`False` = 验证失败。
            Task 4.2 完整实现后由调用方传入。

    Returns:
        `QualityReport`：`coverage` = 1.0（文书已生成）或 0.0（未生成）。
    """
    issues: list[Issue] = []

    # 规则 1：文书内容非空
    if not complaint_draft or not complaint_draft.get("content"):
        issues.append(Issue(
            code="document.empty_content",
            message="文书内容为空",
            severity="blocking",
            stage="document_generation",
            recoverable=True,
        ))

    # 规则 2：法条引用真实存在（占位，Task 4.2 实现 LawRetriever）
    if legal_references_valid is False:
        issues.append(Issue(
            code="document.invalid_legal_reference",
            message="文书引用的法条不存在",
            severity="blocking",
            stage="document_generation",
            recoverable=True,
        ))

    # 规则 3：金额一致性（占位，Task 4.2 实现）
    if amount_consistent is False:
        issues.append(Issue(
            code="document.amount_inconsistent",
            message="文书金额与抽取字段不一致",
            severity="blocking",
            stage="document_generation",
            recoverable=True,
        ))

    return _build_report(
        issues=issues,
        coverage=1.0 if (complaint_draft and complaint_draft.get("content")) else 0.0,
        stage="document_generation",
        details={
            "has_content": bool(complaint_draft and complaint_draft.get("content")),
            "legal_references_valid": legal_references_valid,
            "amount_consistent": amount_consistent,
        },
    )


def should_block_on_quality(quality: QualityReport) -> bool:
    """根据质量报告判断是否应阻塞（调用方使用 `interrupt()` 暂停 graph）。

    Args:
        quality: 质量报告。

    Returns:
        `True` 如质量 `status == "fail"`（blocking issues 存在）；
        `False` 如 `status == "pass"` 或 `"warn"`。

    调用方约定（对齐 Task 0.4 错误处理 4 层策略 + Task 2.3.4）：
    - 返回 `True` 时，节点应使用 `langgraph.types.interrupt()` 暂停 graph
      （不抛异常），等待用户介入或局部重跑后 resume。
    - 返回 `False` 时，节点正常返回 partial update dict，工作流继续推进。
    """
    return quality.status == "fail"
