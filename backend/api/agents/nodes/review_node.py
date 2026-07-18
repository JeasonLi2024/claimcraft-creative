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

幂等性保障（Task 0.3 + Task 2.2 验证结论，对齐 langgraph-human-in-the-loop skill）：
- interrupt() 前调用 `intervention_service.create_intervention`（Task 2.1 实现），
  内部使用 `WorkflowIntervention.objects.update_or_create`（按
  `case + intervention_type + stage + base_revision` 幂等），resume 时节点从头
  重新执行不会创建重复介入记录。
- interrupt() 后使用 `ExtractedField.objects.filter(...).update(...)`（幂等 update
  而非 create），故 resume 重复执行不会创建重复 ExtractedField。
- 中断 payload 统一为 `{interrupt_type, intervention_id, intervention_kind, required,
  stage, reason, base_revision, form_schema, initial_values, impact}` 结构
  （Task 2.2.1 规范化），全部 JSON 可序列化（无 datetime / model 实例）。
- 向后兼容：payload 保留 `case_id / fields_to_review / message` 旧字段；
  resume 时支持 `submitted_values`（新格式）与 `corrections`（旧格式）两种输入。

Task 2.4 升级（用户确认字段 + state 字段）：
- resume 时持久化校正结果同步设置 `user_confirmed=True / confirmed_at=now`
- 同步将校正字段合并到 state["user_confirmed_fields"]（自定义 merge_dict reducer，
  按 `{evidence_id}:{field_name}` 作为 key 合并，不整体覆盖）
"""
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from asgiref.sync import sync_to_async
from django.utils import timezone as django_timezone
from langgraph.types import Command, interrupt, Overwrite

from api.agents.state import CaseWorkflowState
from api.agents.schemas import QualityReport
from api.agents.utils.node_result_builder import (
    build_node_result,
    convert_string_errors_to_dicts,
    make_node_partial_update,
)
from api.services.intervention_service import create_intervention

try:
    from langgraph.runtime import Runtime
except ImportError:  # pragma: no cover - langgraph 应已安装
    Runtime = object  # type: ignore[misc,assignment]

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
async def review_node(state: CaseWorkflowState, runtime: Runtime = None) -> Command[Literal["evidence_chain"]]:
    """聚合 HITL（async）：收集所有证据的低置信度字段，一次性 interrupt。

    流程：
    1. 遍历 evidence_extract_results，收集所有 confidence < 0.7 的字段
    2. 若有低置信度字段：
       a. 调用 `create_intervention` 幂等创建 WorkflowIntervention 记录
          （intervention_type=quality_review）
       b. 调用 interrupt() 暂停，payload 统一结构含 intervention_id
    3. 前端展示校正 UI，用户校正后调用 POST /api/cases/<id>/run-workflow/
       传 resume={"submitted_values": {"correction_0": "...", ...}}
       或旧格式 resume={"corrections": [{evidence_id, field_name, field_value}]}
    4. resume 后用人工校正结果覆盖 DB（幂等 update）
    5. 重建 evidence_extract_results（含校正后字段）
    6. 跳转 evidence_chain 节点
    """
    case_id = state["case_id"]
    extract_results = state.get("evidence_extract_results", [])
    start_time = datetime.now(timezone.utc)

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

    # 2. 若无低置信度字段，直接跳转 evidence_chain（发送 review.skipped 通知）
    if not fields_to_review:
        logger.info(f"案件 {case_id} 无低置信度字段，跳过 HITL")
        # 通过 get_stream_writer 发送 review.skipped 自定义事件
        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
            if writer:
                writer({"event_type": "review.skipped", "message": "无需人工校正，跳过审核"})
        except Exception:
            pass  # 非 LangGraph 运行上下文，静默跳过
        node_result = build_node_result(
            node_name="review",
            data={"fields_to_review": 0, "skipped": True},
            quality=QualityReport(
                score=1.0,
                coverage=1.0,
                status="pass",
                blocking_issues=[],
                details={"skipped": True, "reason": "no_low_confidence"},
            ),
            warnings=[],
            errors=[],
            provenance=[],
            start_time=start_time,
            model_calls=0,
        )
        partial = make_node_partial_update(
            node_name="review",
            stage="fact_checking",
            progress=0.55,
            state=state,
            node_result=node_result,
            legacy_fields={},
        )
        return Command(update=partial, goto="evidence_chain")

    # 3. 构造统一 form_schema / initial_values / impact + 幂等创建 WorkflowIntervention
    #    create_intervention 使用 update_or_create（Task 2.1 实现），
    #    resume 时节点从头重新执行不会创建重复记录（对齐 Task 0.3 + Task 2.2.3）
    logger.info(
        f"案件 {case_id} 有 {len(fields_to_review)} 个低置信度字段，触发聚合 HITL"
    )
    base_revision = state.get("revision", 0)
    form_schema = {
        "fields": [
            {
                "name": f"correction_{i}",
                "label": f"{f['evidence_code']} - {f['field_name']}",
                "type": "evidence_link",
                "required": True,
                "initial_value": f["field_value"],
                "evidence_id": f["evidence_id"],
            }
            for i, f in enumerate(fields_to_review)
        ]
    }
    initial_values = {"fields_to_review": fields_to_review}
    impact = {
        "downstream_nodes": ["evidence_chain", "complaint"],
        "rerun_required": True,
    }

    intervention = await sync_to_async(create_intervention)(
        workflow_run_id=state.get("workflow_run_id"),
        case_id=case_id,  # 兼容回退（如 workflow_run_id 未设置）
        intervention_type="quality_review",
        stage="extract",
        base_revision=base_revision,
        form_schema=form_schema,
        initial_values=initial_values,
        impact=impact,
    )

    # 4. 调用 interrupt 暂停（resume 时整个节点重新执行）
    #    payload 统一结构（Task 2.2.1）+ 向后兼容旧字段（case_id / fields_to_review / message）
    payload = {
        # 统一字段（Task 2.2.1）
        "interrupt_type": "quality_review",
        "intervention_id": intervention.id,
        "intervention_kind": "quality_review",
        "required": True,
        "stage": "extract",
        "reason": f"共 {len(fields_to_review)} 个低置信度字段需要校正",
        "base_revision": base_revision,
        "form_schema": form_schema,
        "initial_values": initial_values,
        "impact": impact,
        # 向后兼容字段（旧前端消费）
        "case_id": case_id,
        "fields_to_review": fields_to_review,
        "message": f"共 {len(fields_to_review)} 个低置信度字段需要校正",
    }
    human_input = interrupt(payload)

    # ===== 以下代码仅在 resume 后执行 =====

    errors = []

    # 5. 解析人工校正结果（支持新旧两种格式）
    if not isinstance(human_input, dict):
        human_input = {}

    # 旧格式：human_input = {"corrections": [{evidence_id, field_name, field_value}, ...]}
    corrections = list(human_input.get("corrections", []))

    # 新格式：human_input = {"submitted_values": {"correction_0": "new_value", ...}}
    #         根据 form_schema 字段名映射回 corrections 结构
    submitted_values = human_input.get("submitted_values") or {}
    if not corrections and isinstance(submitted_values, dict) and submitted_values:
        for i, f in enumerate(fields_to_review):
            key = f"correction_{i}"
            if key in submitted_values:
                new_value = submitted_values[key]
                if new_value is not None and new_value != f["field_value"]:
                    corrections.append({
                        "evidence_id": f["evidence_id"],
                        "field_name": f["field_name"],
                        "field_value": new_value,
                    })

    # Task 5.1.5：resume 后记录用户的介入策略选择到 Store（跨运行持久化）
    # 对齐 spec.md Scenario: User preference persists across runs
    try:
        from api.services.user_preference_service import save_user_preference
        # 从 state 获取用户 ID（owner_id 通过 case 反查；此处优先用 workflow_run.started_by）
        user_id_for_pref = None
        workflow_run_id_for_pref = state.get("workflow_run_id")
        if workflow_run_id_for_pref:
            try:
                from api.models import WorkflowRun
                workflow_run = await sync_to_async(WorkflowRun.objects.filter(pk=workflow_run_id_for_pref).first)()
                if workflow_run and workflow_run.started_by_id:
                    user_id_for_pref = workflow_run.started_by_id
            except Exception:
                pass
        # 回退：从 case 查 owner_id
        if not user_id_for_pref:
            try:
                from api.models import Case
                case = await sync_to_async(Case.objects.filter(pk=case_id).first)()
                if case and case.owner_id:
                    user_id_for_pref = case.owner_id
            except Exception:
                pass

        # 记录用户的介入策略（如 "critical_only" / "review_all"）
        strategy = (
            human_input.get("strategy")
            if isinstance(human_input, dict)
            else None
        )
        if not strategy and corrections:
            # 推断策略：有校正视为 critical_only（仅校正低置信度项）
            strategy = "critical_only"
        if user_id_for_pref and strategy:
            save_user_preference(
                runtime, str(user_id_for_pref),
                "last_intervention_strategy", strategy,
            )
    except Exception as pref_err:
        logger.debug(f"记录用户介入策略偏好失败（忽略）: {pref_err}")

    # 6. 持久化校正结果到 DB（按 evidence_id + field_name 定位更新，幂等 update）
    # Task 2.4：同步设置 user_confirmed=True + confirmed_at=now，并构造 state 增量
    user_confirmed_updates: dict[str, dict] = {}
    confirmed_at_iso = django_timezone.now().isoformat()
    if corrections:
        from api.models import Evidence, ExtractedField
        confirmed_at_now = django_timezone.now()
        for correction in corrections:
            evidence_id = correction.get("evidence_id")
            field_name = correction.get("field_name")
            new_value = correction.get("field_value")
            if evidence_id and field_name and new_value is not None:
                try:
                    await sync_to_async(lambda eid=evidence_id, fn=field_name, nv=new_value, ts=confirmed_at_now:
                        ExtractedField.objects.filter(
                            evidence_id=eid, field_name=fn
                        ).update(
                            field_value=nv,
                            confidence=1.0,
                            user_confirmed=True,
                            confirmed_at=ts,
                        )
                    )()
                except Exception as e:
                    logger.error(f"持久化校正结果失败: {e}", exc_info=True)
                    errors.append(f"持久化校正结果失败: {e}")
                # 追加到 state["user_confirmed_fields"]（merge_dict reducer 按 key 合并）
                # TODO: 从 state / config 取真实 user_id，当前占位为 "user"
                user_confirmed_updates[f"{evidence_id}:{field_name}"] = {
                    "evidence_id": evidence_id,
                    "field_name": field_name,
                    "confirmed_at": confirmed_at_iso,
                    "confirmed_by": "user",
                }
        logger.info(f"案件 {case_id} 人工校正完成，已更新 {len(corrections)} 个字段")

    # 7. 重建 evidence_extract_results（从 DB 读取最新字段）
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

    # 构造 NodeResult + partial update（含 node_result / revision / issues 等）
    error_dicts = convert_string_errors_to_dicts(errors, stage="review")
    # provenance: 每个校正字段一项
    provenance = [
        {
            "node": "review",
            "evidence_id": c.get("evidence_id"),
            "field_name": c.get("field_name"),
            "source_ref": f"review:{c.get('evidence_code', '')}:{c.get('field_name', '')}",
            "ts": start_time.isoformat(),
        }
        for c in corrections
    ]
    # 校正后字段质量（用户校正后置信度均为 1.0）
    node_result = build_node_result(
        node_name="review",
        data={
            "fields_to_review": len(fields_to_review),
            "corrections_applied": len(corrections),
            "intervention_id": intervention.id,
        },
        quality=QualityReport(
            score=1.0,
            coverage=1.0,
            status="pass",
            blocking_issues=[],
            details={"corrections_applied": len(corrections)},
        ),
        warnings=[],
        errors=error_dicts,
        provenance=provenance,
        start_time=start_time,
        model_calls=0,
    )
    partial = make_node_partial_update(
        node_name="review",
        stage="fact_checking",
        progress=0.55,
        state=state,
        node_result=node_result,
        legacy_fields={
            # evidence_extract_results 声明了 add reducer（累积追加），
            # 但 review_node 需要替换整个列表为校正后的结果。
            # 用 Overwrite 包装实现「替换而非追加」，避免下游读到双倍字段。
            "evidence_extract_results": Overwrite(updated_results),
            "needs_human_review": False,
            "review_decision": human_input,
            "errors": error_dicts,  # 保持 add 累积语义（记录所有节点的错误）
            # Task 2.4：用户已校正字段合并到 state（merge_dict reducer 按 key 合并）
            "user_confirmed_fields": user_confirmed_updates,
        },
    )
    return Command(update=partial, goto="evidence_chain")
