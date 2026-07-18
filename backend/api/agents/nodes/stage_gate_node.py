# -*- coding: utf-8 -*-
"""工作流业务节点边界的安全暂停门。

幂等性保障（Task 0.3 + Task 2.2 验证结论，对齐 langgraph-human-in-the-loop skill）：
- interrupt() 前调用 `intervention_service.create_intervention`（Task 2.1 实现），
  内部使用 `WorkflowIntervention.objects.update_or_create`（按
  `case + intervention_type + stage + base_revision` 幂等），resume 时节点从头
  重新执行不会创建重复介入记录。
- interrupt() 前的只读检查 `Case.objects.filter(...).exists()`（幂等，无副作用）。
- interrupt() payload 统一为 `{interrupt_type, intervention_id, intervention_kind,
  required, stage, reason, base_revision, form_schema, initial_values, impact}` 结构
  （Task 2.2.2 规范化），全部 JSON 可序列化（无 datetime / model 实例）。
- interrupt() 后仅返回 `state_updates`（dict），无任何 DB 写入。
- 向后兼容：payload 保留 `paused_after / editable_scope / message` 旧字段；
  resume 时仅取 `state_updates`，兼容旧格式 `interrupt_type=stage_pause` 的 resume 值。
"""
from __future__ import annotations

from asgiref.sync import sync_to_async
from langgraph.types import interrupt

from api.models import Case
from api.services.intervention_service import create_intervention
from api.services.workflow_pause_service import (
    build_stage_pause_payload,
    get_stage_editable_scope,
)

try:
    from langgraph.runtime import Runtime
except ImportError:  # pragma: no cover - langgraph 应已安装
    Runtime = object  # type: ignore[misc,assignment]

import logging
logger = logging.getLogger(__name__)


# 各 stage_gate 之后的下游业务节点（用于 impact.downstream_nodes）。
# 与 graph.py 中 stage_gate_after_<paused_after> 的下游边一一对应。
_NEXT_NODE_MAP: dict[str, list[str]] = {
    "preclassify": ["ocr"],
    "ocr": ["classify"],
    "classify": ["extract"],
    # extract 后条件分支：needs_human_review → review，否则 → evidence_chain
    "extract": ["review", "evidence_chain"],
    "review": ["evidence_chain"],
    # evidence_chain 后条件分支：case_mode → complaint / respond_complaint
    "evidence_chain": ["complaint", "respond_complaint"],
    "complaint": [],
    "respond_complaint": [],
}


def make_stage_gate(paused_after: str):
    """创建绑定业务节点名的阶段门，并在恢复时回写用户修改后的状态。"""

    async def stage_gate(state: dict, runtime: Runtime = None) -> dict:
        case_id = state.get('case_id')
        if not case_id:
            return {}

        pause_requested = await sync_to_async(
            Case.objects.filter(pk=case_id, workflow_pause_requested=True).exists,
            thread_sensitive=True,
        )()
        if not pause_requested:
            return {}

        # 构造统一 form_schema / initial_values / impact + 幂等创建 WorkflowIntervention
        # create_intervention 使用 update_or_create（Task 2.1 实现），
        # resume 时节点从头重新执行不会创建重复记录（对齐 Task 0.3 + Task 2.2.3）
        base_revision = state.get("revision", 0)
        next_nodes = _NEXT_NODE_MAP.get(paused_after, [])
        form_schema = {
            "fields": [
                {
                    "name": "notes",
                    "label": "备注（可选）",
                    "type": "textarea",
                    "required": False,
                }
            ]
        }
        impact = {
            "downstream_nodes": next_nodes,
            "rerun_required": False,
        }

        intervention = await sync_to_async(create_intervention)(
            workflow_run_id=state.get("workflow_run_id"),
            case_id=case_id,  # 兼容回退（如 workflow_run_id 未设置）
            intervention_type="user_pause",
            stage=paused_after,
            base_revision=base_revision,
            form_schema=form_schema,
            initial_values={},
            impact=impact,
        )

        # payload 统一结构（Task 2.2.2）+ 向后兼容旧字段（paused_after / editable_scope / message）
        legacy_payload = build_stage_pause_payload(paused_after)
        payload = {
            # 统一字段（Task 2.2.2）
            "interrupt_type": "user_pause",
            "intervention_id": intervention.id,
            "intervention_kind": "user_pause",
            "required": False,
            "stage": paused_after,
            "reason": f"用户在 {paused_after} 阶段后请求暂停",
            "base_revision": base_revision,
            "form_schema": form_schema,
            "initial_values": {},
            "impact": impact,
            # 向后兼容字段（旧前端消费）
            "paused_after": paused_after,
            "editable_scope": legacy_payload.get("editable_scope", get_stage_editable_scope(paused_after)),
            "message": legacy_payload.get("message", f"已在 {paused_after} 节点完成后安全暂停，可修改阶段产物后继续。"),
        }
        resume_value = interrupt(payload)

        # Task 5.1.5：resume 后记录用户的介入策略选择到 Store（跨运行持久化）
        # 对齐 spec.md Scenario: User preference persists across runs
        if runtime is not None and isinstance(resume_value, dict):
            try:
                from api.services.user_preference_service import save_user_preference
                # 解析用户介入策略
                strategy = resume_value.get("strategy")
                if not strategy:
                    # stage_pause resume 默认记录为 "manual_pause"
                    strategy = "manual_pause"
                # 解析 user_id：优先 workflow_run.started_by，回退 case.owner_id
                user_id_for_pref = None
                workflow_run_id_for_pref = state.get("workflow_run_id")
                if workflow_run_id_for_pref:
                    try:
                        from api.models import WorkflowRun
                        workflow_run = await sync_to_async(
                            WorkflowRun.objects.filter(pk=workflow_run_id_for_pref).first
                        )()
                        if workflow_run and workflow_run.started_by_id:
                            user_id_for_pref = workflow_run.started_by_id
                    except Exception:
                        pass
                if not user_id_for_pref:
                    try:
                        case = await sync_to_async(Case.objects.filter(pk=case_id).first)()
                        if case and case.owner_id:
                            user_id_for_pref = case.owner_id
                    except Exception:
                        pass
                if user_id_for_pref and strategy:
                    save_user_preference(
                        runtime, str(user_id_for_pref),
                        "last_intervention_strategy", strategy,
                    )
            except Exception as pref_err:
                logger.debug(f"记录用户介入策略偏好失败（忽略）: {pref_err}")

        # resume 后：从 resume_value 取 state_updates 作为节点 update（保留现有逻辑）
        # 兼容旧格式 resume_value = {"interrupt_type": "stage_pause", "state_updates": {...}}
        if not isinstance(resume_value, dict):
            return {}
        state_updates = resume_value.get('state_updates')
        return state_updates if isinstance(state_updates, dict) else {}

    stage_gate.__name__ = f'stage_gate_after_{paused_after}'
    return stage_gate
