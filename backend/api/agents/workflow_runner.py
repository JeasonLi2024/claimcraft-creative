# -*- coding: utf-8 -*-
"""工作流后台运行器：消费 astream_events(v2) 写入 EventDepot 并通知。

参考 spec 第 5.4 节。采用生产者-消费者解耦模式：
- WorkflowRunner 作为生产者在后台运行
- 每次 astream_events 产生输出 → SSEEventMapper 过滤映射 → EventDepot.persist → NotifyEmitter.notify
- SSE 端点作为消费者从 EventDepot 读取事件推送给前端

后台任务执行方式（spec 选项 A）：asyncio.create_task + 全局任务注册表
- 适合单进程 ASGI 部署（uvicorn workers）
- _task_registry: dict[thread_id, asyncio.Task] 管理运行中的任务
- 进程崩溃则任务丢失，依赖 checkpointer 恢复

HITL 流程：
- review_node 触发 interrupt() 后，astream_events 自然结束，任务从注册表移除
- CaseWorkflowResumeView 调用 start_in_background(resume=...) 新建任务
- 复用同一 thread_id，LangGraph 从 checkpointer 恢复中断前状态
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command

from api.agents.graph import build_case_workflow
from api.agents.notify_emitter import NotifyEmitter
from api.agents.sse_event_depot import EventDepot
from api.agents.sse_event_mapper import SSEEventMapper

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """返回当前 UTC 时间（naive，与 graph.py 风格一致）。"""
    return datetime.utcnow()


def _utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


class WorkflowRunner:
    """工作流后台运行器：消费 astream_events，写入 EventDepot。

    用法：
        runner = WorkflowRunner()
        runner.start_in_background(case_id=1, thread_id="case-1-123",
                                    initial_state={...})
        # 或 HITL 恢复：
        runner.start_in_background(case_id=1, thread_id="case-1-123",
                                    resume={"corrections": [...]})
    """

    # 类级任务注册表：thread_id → asyncio.Task（运行中的后台任务）
    _task_registry: dict[str, asyncio.Task] = {}

    async def run_and_persist(
        self,
        case_id: int,
        thread_id: str,
        initial_state: dict | None = None,
        resume: dict | None = None,
    ) -> None:
        """后台任务入口：消费 astream_events 写入 EventDepot + 通知。

        与 SSE 端点解耦：本方法只负责生产事件，不关心是否有 SSE 客户端连接。

        Args:
            case_id: 案件 ID
            thread_id: LangGraph checkpointer 线程 ID
            initial_state: 首次启动时的工作流初始状态（与 resume 互斥）
            resume: HITL 恢复时的人工校正数据（与 initial_state 互斥）
        """
        depot = EventDepot()
        emitter = NotifyEmitter()
        workflow_start_time = _utcnow()

        try:
            # 1. 首次启动：持久化 workflow.start 事件
            if not resume:
                eid = await depot.persist(thread_id, "workflow.start", {
                    "thread_id": thread_id,
                    "case_id": case_id,
                    "evidence_ids": (initial_state or {}).get("evidence_ids", []),
                    "started_at": _utcnow_iso(),
                })
                await emitter.notify(thread_id, eid)
            else:
                # HITL 恢复：持久化 review.resumed 事件
                corrections = resume.get("corrections", []) if isinstance(resume, dict) else []
                eid = await depot.persist(thread_id, "review.resumed", {
                    "applied_corrections": corrections,
                    "corrections_count": len(corrections),
                    "ts": _utcnow_iso(),
                })
                await emitter.notify(thread_id, eid)

            # 2. 构建 workflow + config
            workflow = build_case_workflow()
            config = {"configurable": {"thread_id": thread_id}}

            # 3. 消费 astream_events（v2 协议）
            if resume:
                stream = workflow.astream_events(
                    Command(resume=resume), config=config, version="v2"
                )
            else:
                stream = workflow.astream_events(
                    initial_state, config=config, version="v2"
                )

            mapper = SSEEventMapper()
            async for raw_event in stream:
                try:
                    sse_events = await mapper.map(raw_event)
                except Exception as map_err:
                    logger.warning(
                        f"映射事件失败 (thread={thread_id}): {map_err}",
                        exc_info=True,
                    )
                    continue

                for sse_event in sse_events:
                    eid = await depot.persist(
                        thread_id, sse_event.type, sse_event.payload
                    )
                    await emitter.notify(thread_id, eid)

            # 4. 区分 HITL 中断与图真正结束，避免把等待校正误判为完成
            snapshot = await workflow.aget_state(config)
            if snapshot.next:
                from asgiref.sync import sync_to_async
                from api.services.case_lifecycle_service import mark_waiting_review

                await sync_to_async(mark_waiting_review, thread_sensitive=True)(case_id)
                waiting_eid = await depot.persist(thread_id, "workflow.waiting_review", {
                    "thread_id": thread_id,
                    "case_id": case_id,
                    "next_nodes": list(snapshot.next),
                    "ts": _utcnow_iso(),
                })
                await emitter.notify(thread_id, waiting_eid)
                return

            # 5. 图真正结束后校验数据库中的文稿产物，再推进案件生命周期
            from asgiref.sync import sync_to_async
            from api.services.case_lifecycle_service import complete_processing

            completion = await sync_to_async(complete_processing, thread_sensitive=True)(
                case_id, thread_id=thread_id
            )
            if completion.case.workflow_status != 'succeeded':
                raise RuntimeError(completion.case.workflow_error or '工作流未生成有效文稿')
            total_duration_ms = int(
                (_utcnow() - workflow_start_time).total_seconds() * 1000
            )
            final_eid = await depot.persist(thread_id, "workflow.complete", {
                "thread_id": thread_id,
                "case_id": case_id,
                "total_duration_ms": total_duration_ms,
                "errors": [],
                "ts": _utcnow_iso(),
            })
            await emitter.notify(thread_id, final_eid)
            logger.info(
                f"工作流完成 (thread={thread_id}, case={case_id}, "
                f"duration={total_duration_ms}ms)"
            )

        except Exception as e:
            # 不可恢复的致命错误：同步案件工作流状态并写入事件
            try:
                from asgiref.sync import sync_to_async
                from api.services.case_lifecycle_service import fail_processing
                await sync_to_async(fail_processing, thread_sensitive=True)(case_id, str(e))
            except Exception as state_err:
                logger.error(f"同步工作流失败状态异常 (case={case_id}): {state_err}")
            logger.error(
                f"工作流运行失败 (thread={thread_id}, case={case_id}): {e}",
                exc_info=True,
            )
            try:
                error_eid = await depot.persist(thread_id, "workflow.error", {
                    "message": str(e)[:500],
                    "node": None,
                    "recoverable": False,
                    "ts": _utcnow_iso(),
                })
                await emitter.notify(thread_id, error_eid)
            except Exception as persist_err:
                logger.error(
                    f"写入 workflow.error 事件失败 (thread={thread_id}): {persist_err}",
                    exc_info=True,
                )
        finally:
            # 任务结束，从注册表移除
            self._task_registry.pop(thread_id, None)

    def start_in_background(
        self,
        case_id: int,
        thread_id: str,
        initial_state: dict | None = None,
        resume: dict | None = None,
    ) -> asyncio.Task:
        """启动后台任务（不阻塞调用方）。

        若同一 thread_id 已有运行中的任务，先取消旧任务（避免重复运行）。

        Args:
            case_id: 案件 ID
            thread_id: LangGraph checkpointer 线程 ID
            initial_state: 首次启动的初始状态（与 resume 互斥）
            resume: HITL 恢复的校正数据（与 initial_state 互斥）

        Returns:
            asyncio.Task 对象
        """
        # 取消同 thread_id 的旧任务（如有）
        old_task = self._task_registry.get(thread_id)
        if old_task is not None and not old_task.done():
            old_task.cancel()
            logger.warning(f"取消同 thread_id 旧任务 (thread={thread_id})")

        task = asyncio.create_task(
            self.run_and_persist(
                case_id=case_id,
                thread_id=thread_id,
                initial_state=initial_state,
                resume=resume,
            )
        )
        self._task_registry[thread_id] = task

        # 任务结束回调：确保从注册表清理
        def _on_done(t: asyncio.Task) -> None:
            self._task_registry.pop(thread_id, None)
            if t.cancelled():
                logger.debug(f"后台任务已取消 (thread={thread_id})")
            elif t.exception():
                logger.error(
                    f"后台任务异常退出 (thread={thread_id}): {t.exception()}"
                )

        task.add_done_callback(_on_done)
        return task

    @classmethod
    def is_running(cls, thread_id: str) -> bool:
        """检查指定 thread_id 是否有运行中的后台任务。"""
        task = cls._task_registry.get(thread_id)
        return task is not None and not task.done()

    @classmethod
    def get_running_thread_ids(cls) -> list[str]:
        """获取所有运行中的 thread_id 列表（调试/监控用）。"""
        return [
            tid for tid, task in cls._task_registry.items()
            if not task.done()
        ]
