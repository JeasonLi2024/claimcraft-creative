# -*- coding: utf-8 -*-
"""工作流业务节点边界的安全暂停门。"""
from __future__ import annotations

from asgiref.sync import sync_to_async
from langgraph.types import interrupt

from api.models import Case
from api.services.workflow_pause_service import build_stage_pause_payload


def make_stage_gate(paused_after: str):
    """创建绑定业务节点名的阶段门，并在恢复时回写用户修改后的状态。"""

    async def stage_gate(state: dict) -> dict:
        case_id = state.get('case_id')
        if not case_id:
            return {}

        pause_requested = await sync_to_async(
            Case.objects.filter(pk=case_id, workflow_pause_requested=True).exists,
            thread_sensitive=True,
        )()
        if not pause_requested:
            return {}

        resume_value = interrupt(build_stage_pause_payload(paused_after))
        if not isinstance(resume_value, dict):
            return {}
        if resume_value.get('interrupt_type') != 'stage_pause':
            return {}
        state_updates = resume_value.get('state_updates')
        return state_updates if isinstance(state_updates, dict) else {}

    stage_gate.__name__ = f'stage_gate_after_{paused_after}'
    return stage_gate
