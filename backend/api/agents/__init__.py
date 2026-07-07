# -*- coding: utf-8 -*-
"""ClaimCraft 案件智能体工作流（多证据聚合版）。

基于 LangGraph 1.0 构建工作流：
    START → preclassify → ocr → classify → extract → [review?] → evidence_chain → complaint → END

使用 PostgresSaver checkpointer 实现案件级状态持久化与 HITL 恢复。

SSE 流式改造（2026-07-07）：
- WorkflowRunner：后台任务，消费 astream_events 写入 EventDepot
- EventDepot：Postgres 表 sse_event_depot，事件保留站，支持断连续传
- SSEEventMapper：astream_events(v2) → SSE 事件过滤映射
- NotifyEmitter：Postgres LISTEN/NOTIFY 封装，通知 SSE 端点有新事件
"""
from api.agents.graph import build_case_workflow
from api.agents.notify_emitter import NotifyEmitter
from api.agents.sse_event_depot import EventDepot
from api.agents.sse_event_mapper import SSEEvent, SSEEventMapper
from api.agents.workflow_runner import WorkflowRunner

__all__ = [
    "build_case_workflow",
    "WorkflowRunner",
    "EventDepot",
    "SSEEventMapper",
    "SSEEvent",
    "NotifyEmitter",
]
