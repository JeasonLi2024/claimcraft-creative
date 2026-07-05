# -*- coding: utf-8 -*-
"""HITL 人工校正节点（async，聚合版）：收集所有证据的低置信度字段，一次性 interrupt。

重构说明（v4 异步化）：
- def → async def，支持节点级 timeout
- Django ORM 调用用 sync_to_async 包装
- @traceable 装饰器

重构说明（多证据工作流）：
- 从单证据 interrupt 改为聚合所有证据低置信度字段一次性 interrupt
- resume 后用人工校正结果覆盖 DB（按 evidence_id + field_name 定位）
- 跳转目标从 timeline 改为 evidence_chain

基于 langgraph-human-in-the-loop skill：
- interrupt(value) 暂停图执行
- Command(resume=value) 恢复
- interrupt 前的代码必须幂等（resume 时整个节点重新执行）

幂等性保障：
- interrupt() 前不做任何 DB 写入
- 仅在 resume 后用人工校正结果覆盖 ExtractedField 表
"""
import logging
from typing import Any, Literal

from asgiref.sync import sync_to_async
from langgraph.types import Command, interrupt, Overwrite

from api.agents.state import CaseWorkflowState

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def deco(fn):
            return fn
        return args[0] if args and callable(args[0]) else deco

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.7


@traceable(name="人工校正节点", run_type="chain")
async def review_node(state: CaseWorkflowState) -> Command[Literal["evidence_chain"]]:
    """聚合 HITL（async）：收集所有证据的低置信度字段，一次性 interrupt。

    流程：
    1. 遍历 evidence_extract_results，收集所有 confidence < 0.7 的字段
    2. 若有低置信度字段，调用 interrupt() 暂停
    3. 前端展示校正 UI，用户校正后调用 POST /api/cases/<id>/run-workflow/
       传 resume={"corrections": [{evidence_id, field_name, field_value}]}
    4. resume 后用人工校正结果覆盖 DB
    5. 重建 evidence_extract_results（含校正后字段）
    6. 跳转 evidence_chain 节点
    """
    case_id = state["case_id"]
    extract_results = state.get("evidence_extract_results", [])

    # 1. 收集所有低置信度字段
    fields_to_review = []
    for er in extract_results:
        for f in er.get("fields", []):
            if f.get("confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD:
                fields_to_review.append({
                    "evidence_id": er["evidence_id"],
                    "evidence_code": er["evidence_code"],
                    "field_name": f.get("field_name", ""),
                    "field_value": f.get("field_value", ""),
                    "confidence": f.get("confidence", 0.0),
                })

    # 2. 若无低置信度字段，直接跳转 evidence_chain
    if not fields_to_review:
        logger.info(f"案件 {case_id} 无低置信度字段，跳过 HITL")
        return Command(update={}, goto="evidence_chain")

    # 3. 调用 interrupt 暂停（resume 时整个节点重新执行）
    #    interrupt 前不做任何 DB 写入（幂等性）
    logger.info(
        f"案件 {case_id} 有 {len(fields_to_review)} 个低置信度字段，触发聚合 HITL"
    )
    human_input = interrupt({
        "case_id": case_id,
        "fields_to_review": fields_to_review,
        "message": f"共 {len(fields_to_review)} 个低置信度字段需要校正",
    })

    # ===== 以下代码仅在 resume 后执行 =====

    errors = []

    # 4. 解析人工校正结果
    if not isinstance(human_input, dict):
        human_input = {"corrections": []}

    corrections = human_input.get("corrections", [])

    # 5. 持久化校正结果到 DB（按 evidence_id + field_name 定位更新）
    if corrections:
        from api.models import Evidence, ExtractedField
        for correction in corrections:
            evidence_id = correction.get("evidence_id")
            field_name = correction.get("field_name")
            new_value = correction.get("field_value")
            if evidence_id and field_name and new_value is not None:
                try:
                    await sync_to_async(lambda eid=evidence_id, fn=field_name, nv=new_value:
                        ExtractedField.objects.filter(
                            evidence_id=eid, field_name=fn
                        ).update(field_value=nv, confidence=1.0)
                    )()
                except Exception as e:
                    logger.error(f"持久化校正结果失败: {e}", exc_info=True)
                    errors.append(f"持久化校正结果失败: {e}")
        logger.info(f"案件 {case_id} 人工校正完成，已更新 {len(corrections)} 个字段")

    # 6. 重建 evidence_extract_results（从 DB 读取最新字段）
    updated_results = []
    for er in extract_results:
        try:
            from api.models import Evidence
            evidence = await sync_to_async(Evidence.objects.get)(pk=er["evidence_id"])
            fields_list = await sync_to_async(list)(evidence.extracted_fields.all())
            corrected_fields = [
                {
                    "field_name": f.field_name,
                    "field_value": f.field_value,
                    "confidence": f.confidence,
                    "source": "review" if f.confidence == 1.0 else "original",
                }
                for f in fields_list
            ]
        except Evidence.DoesNotExist:
            corrected_fields = er.get("fields", [])
            errors.append(f"证据 {er['evidence_id']} 不存在，使用原字段")

        updated_results.append({
            "evidence_id": er["evidence_id"],
            "evidence_code": er["evidence_code"],
            "fields": corrected_fields,
            "needs_human_review": False,
        })

    return Command(
        update={
            # evidence_extract_results 声明了 add reducer（累积追加），
            # 但 review_node 需要替换整个列表为校正后的结果。
            # 用 Overwrite 包装实现「替换而非追加」，避免下游读到双倍字段。
            "evidence_extract_results": Overwrite(updated_results),
            "needs_human_review": False,
            "review_decision": human_input,
            "errors": errors,  # 保持 add 累积语义（记录所有节点的错误）
        },
        goto="evidence_chain",
    )
