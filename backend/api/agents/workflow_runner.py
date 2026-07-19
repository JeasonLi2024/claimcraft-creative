# -*- coding: utf-8 -*-
"""工作流后台运行器：消费 astream_events(v2) 写入 EventDepot 并通知。

参考 spec 第 5.4 节。采用生产者-消费者解耦模式：
- WorkflowRunner 作为生产者在后台运行
- 每次 astream_events 产生输出 → SSEEventMapper 过滤映射 → EventDepot.persist → NotifyEmitter.notify
- SSE 端点作为消费者从 EventDepot 读取事件推送给前端

后台任务执行方式：优先复用当前事件循环；若调用方在同步线程中，
则投递到专用后台事件循环线程。
- 适合 DRF 同步视图 + ASGI/SSE 混合部署
- _task_registry: dict[thread_id, Future] 管理运行中的后台任务
- 进程崩溃则任务丢失，依赖 checkpointer 恢复

HITL 流程：
- review_node 触发 interrupt() 后，astream_events 自然结束，任务从注册表移除
- CaseWorkflowResumeView 调用 start_in_background(resume=...) 新建任务
- 复用同一 thread_id，LangGraph 从 checkpointer 恢复中断前状态

已对齐 `langgraph-human-in-the-loop` skill（Task 0.2 验证结论）：
- resume 使用 `Command(resume=...)` 而非普通 dict（见 run_and_persist 内 line 158），
  确保从 checkpointer 中断点恢复而非从头执行。
- 普通 dict 会导致 graph 从最新 checkpoint 恢复但表现为 stuck（无 interrupt_id 关联，
  graph 无法定位到 `interrupt()` 调用点）；`Command(resume=...)` 正确关联到
  `interrupt()` 调用点，节点从中断后第一行恢复执行。
- 三处调用点均已使用 `Command(resume=...)`：
  * workflow_runner.py: run_and_persist 内 astream_events（本文件 line 158）
  * views.py: CaseWorkflowRunView 内 workflow.ainvoke（line 2264）
  * graph.py: build_case_workflow docstring 示例（line 25）
- resumePausedWorkflow（views.py line 2783）通过 start_in_background(resume=...)
  委托 WorkflowRunner，内部已统一使用 Command(resume=...)，无需重复修改。
- resume payload 构造符合规范：
  * HITL 审核恢复：`{"corrections": [...]}`（list[dict]，旧格式）或
    `{"submitted_values": {"correction_0": "...", ...}}`（新格式，对齐 Task 2.2.1
    的 form_schema 字段命名）
  * 阶段暂停恢复：`{"interrupt_type": "stage_pause", "paused_after": ..., "state_updates": {...}}`
    （旧格式，build_stage_resume_payload 仍输出此结构；stage_gate_node resume
    代码仅取 state_updates 字段，兼容新旧两种 interrupt_type）

Task 2.2.4 新增（统一介入事件持久化）：
- run_and_persist 在 astream_events 结束后、区分 stage_pause / waiting_review 之前，
  统一遍历 snapshot.interrupts，对含 `intervention_id` 的 payload 持久化
  `intervention.created` SSE 事件（含 intervention_id / type / kind / required /
  stage / reason / base_revision / form_schema / initial_values / impact）。
- 该事件覆盖 quality_review 与 user_pause 两类介入，让前端 InterventionPanel
  根据 form_schema 动态渲染统一面板。
- 不修改 resume 逻辑：Command(resume=...) 已正确（Task 0.2 验证），仅新增事件持久化。
"""
import asyncio
import logging
import os
import threading
from concurrent.futures import Future
from datetime import datetime, timezone
from typing import Any, Optional

from asgiref.sync import sync_to_async
from langgraph.types import Command

from api.agents.graph import build_case_workflow
from api.agents.notify_emitter import NotifyEmitter
from api.agents.sse_event_depot import EventDepot
from api.agents.sse_event_mapper import SSEEventMapper
from api.services.case_lifecycle_service import (
    complete_processing,
    fail_processing,
    mark_paused,
    mark_waiting_review,
)
from api.services.workflow_pause_service import (
    interrupt_value,
    is_stage_pause_interrupt_value,
    snapshot_interrupts,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """返回当前 UTC 时间（naive，与 graph.py 风格一致）。"""
    return datetime.utcnow()


def _utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _parse_run_id_from_thread_id(thread_id: str) -> Optional[int]:
    """从 thread_id (case-{case_id}-run-{run_id}) 解析 run_id。

    Task 3.1：thread_id 与 WorkflowRun.thread_id 同步，可反查 run_id。
    """
    try:
        return int(thread_id.rsplit('-run-', 1)[1])
    except (IndexError, ValueError):
        return None


@sync_to_async
def _update_workflow_run(run_id: int, **fields):
    """更新 WorkflowRun 字段（使用 update 限定，避免覆盖其他字段）。

    Task 3.1：在 astream_events 循环内同步 revision / current_stage / current_node /
    progress 到 WorkflowRun；在结束分支同步 status + finished_at / error_message。
    """
    from api.models import WorkflowRun
    WorkflowRun.objects.filter(pk=run_id).update(**fields)


@sync_to_async
def _create_workflow_run(
    case_id: int,
    selected_evidence_ids: list,
    run_options: dict,
    started_by_id: Optional[int] = None,
):
    """创建 WorkflowRun 记录（首次启动分支使用）。

    返回 WorkflowRun 实例。thread_id 由模型 save() 自动生成。
    """
    from api.models import WorkflowRun, Case
    from django.utils import timezone
    run = WorkflowRun.objects.create(
        case_id=case_id,
        status='running',
        started_at=timezone.now(),
        selected_evidence_ids=selected_evidence_ids or [],
        run_options=run_options or {},
        started_by_id=started_by_id,
    )
    # 同步设置 Case.active_workflow_run 双写兼容
    Case.objects.filter(pk=case_id).update(active_workflow_run=run)
    return run


@sync_to_async
def _mark_artifacts_readonly(workflow_run_id: int) -> int:
    """将指定 WorkflowRun 的所有 WorkflowArtifact 标记为只读（迁移失败回退）。

    Task 5.2.3：当 state schema 迁移失败时，保留旧产物但禁止编辑，
    在 metadata 中写入 ``{"readonly": True, "readonly_reason": "state_schema_migration_failed"}``。

    Args:
        workflow_run_id: WorkflowRun ID

    Returns:
        被标记的产物数量
    """
    from api.models import WorkflowArtifact
    artifacts = list(
        WorkflowArtifact.objects.filter(workflow_run_id=workflow_run_id)
    )
    for artifact in artifacts:
        metadata = dict(artifact.metadata or {})
        metadata["readonly"] = True
        metadata["readonly_reason"] = "state_schema_migration_failed"
        artifact.metadata = metadata
        artifact.save(update_fields=["metadata"])
    return len(artifacts)


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

    # 类级任务注册表：thread_id → Future（运行中的后台任务）
    _task_registry: dict[str, Future[Any]] = {}
    _background_loop: asyncio.AbstractEventLoop | None = None
    _background_loop_thread: threading.Thread | None = None
    _background_loop_lock = threading.Lock()
    _task_registry_lock = threading.Lock()

    @classmethod
    def _run_background_loop(cls, loop: asyncio.AbstractEventLoop) -> None:
        """在线程内启动专用事件循环。"""
        asyncio.set_event_loop(loop)
        loop.run_forever()

    @classmethod
    def _ensure_background_loop(cls) -> asyncio.AbstractEventLoop:
        """确保存在可投递协程的后台事件循环。"""
        with cls._background_loop_lock:
            if cls._background_loop is not None and cls._background_loop.is_running():
                return cls._background_loop

            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=cls._run_background_loop,
                args=(loop,),
                name="workflow-runner-loop",
                daemon=True,
            )
            thread.start()
            cls._background_loop = loop
            cls._background_loop_thread = thread
            logger.info("已启动 WorkflowRunner 后台事件循环线程")
            return loop

    async def run_and_persist(
        self,
        case_id: int,
        thread_id: str,
        initial_state: dict | None = None,
        resume: dict | None = None,
        fork_config: dict | None = None,
    ) -> None:
        """后台任务入口：消费 astream_events 写入 EventDepot + 通知。

        与 SSE 端点解耦：本方法只负责生产事件，不关心是否有 SSE 客户端连接。

        Task 3.1：在首次启动分支创建 WorkflowRun 记录并注入 workflow_run_id 到
        initial_state；resume 分支从 thread_id 反查 run_id 并更新 status=running。
        astream_events 循环内同步 revision / current_stage / current_node / progress
        到 WorkflowRun；结束分支同步 status + finished_at / error_message。

        Task 3.3：新增 fork_config 参数，支持 RetryService 局部重跑 fork 启动。
        - fork_config 非空时：WorkflowRun 已由 RetryService 创建，此处仅反查 run_id
          并同步 status=running，使用 fork_config 作为 config 传 None 给 astream_events
          （对齐 langgraph-persistence skill 的 graph.invoke(None, fork_config) 模式）
        - fork_config 与 initial_state / resume 三者互斥

        Args:
            case_id: 案件 ID
            thread_id: LangGraph checkpointer 线程 ID
            initial_state: 首次启动时的工作流初始状态（与 resume / fork_config 互斥）
            resume: HITL 恢复时的人工校正数据（与 initial_state / fork_config 互斥）
            fork_config: RetryService fork 出的 config（与 initial_state / resume 互斥）
        """
        depot = EventDepot()
        emitter = NotifyEmitter()
        workflow_start_time = _utcnow()
        run_id: Optional[int] = None

        try:
            if fork_config:
                # Task 3.3：fork 启动分支 — WorkflowRun 已由 RetryService 创建
                # 从 fork_config 提取 thread_id（覆盖原 thread_id 参数）
                fork_thread_id = (
                    fork_config.get("configurable", {}).get("thread_id", thread_id)
                    if isinstance(fork_config, dict) else thread_id
                )
                thread_id = fork_thread_id
                run_id = _parse_run_id_from_thread_id(thread_id)
                if run_id is not None:
                    try:
                        await _update_workflow_run(
                            run_id,
                            status='running',
                            error_message='',
                        )
                    except Exception as run_err:
                        logger.warning(
                            f"fork 启动时更新 WorkflowRun 失败 (run_id={run_id}): {run_err}"
                        )
                eid = await depot.persist(thread_id, "workflow.start", {
                    "thread_id": thread_id,
                    "case_id": case_id,
                    "run_id": run_id,
                    "forked": True,
                    "started_at": _utcnow_iso(),
                })
                await emitter.notify(thread_id, eid)
            elif not resume:
                # 1. 首次启动：持久化 workflow.start 事件 + 创建 WorkflowRun
                # 注入工作流版本常量到 initial state（Task 1.1.3）
                # 仅在首次启动（非 resume）分支注入，使每个 WorkflowRun 都能记录
                # 其启动时的版本快照；resume 时版本已持久化在 checkpointer，不覆盖。
                from api.agents.version import WorkflowVersion
                if initial_state is None:
                    initial_state = {}
                initial_state = {**WorkflowVersion.to_initial_state(), **initial_state}

                # 新 API 会预先创建 WorkflowRun 并把 ID 注入 initial_state；旧调用
                # 路径没有该字段时，仍由 runner 创建，避免一轮流程产生两条运行记录。
                selected_evidence_ids = list(initial_state.get("evidence_ids", []) or [])
                run_options = {
                    k: v for k, v in (initial_state or {}).items()
                    if k in ("case_mode", "template_type")
                }
                run_id = initial_state.get("workflow_run_id")
                try:
                    if run_id is not None:
                        from api.models import WorkflowRun
                        run = await sync_to_async(WorkflowRun.objects.get)(
                            pk=run_id,
                            case_id=case_id,
                        )
                        thread_id = run.thread_id
                        await _update_workflow_run(
                            run.id,
                            status='running',
                            started_at=workflow_start_time,
                            error_message='',
                        )
                    else:
                        run = await _create_workflow_run(
                            case_id=case_id,
                            selected_evidence_ids=selected_evidence_ids,
                            run_options=run_options,
                        )
                        run_id = run.id
                        initial_state["workflow_run_id"] = run_id
                        thread_id = run.thread_id
                except Exception as run_err:
                    logger.error(
                        f"初始化 WorkflowRun 失败 (case={case_id}): {run_err}",
                        exc_info=True,
                    )
                    run_id = None

                # Task 5.1.6：读取用户偏好注入 run_options（跨运行记忆）
                # 优先用 WorkflowRun.started_by_id；若为 None（旧调用路径未传入）
                # 回退到 Case.owner_id。Store 不可用时静默降级，不阻塞主流程。
                try:
                    user_id_for_prefs: Optional[int] = None
                    if run_id is not None:
                        user_id_for_prefs = getattr(run, "started_by_id", None)
                    if user_id_for_prefs is None:
                        from api.models import Case as _CaseModel
                        case_owner_id = await sync_to_async(
                            lambda: _CaseModel.objects.filter(pk=case_id)
                            .values_list("owner_id", flat=True)
                            .first()
                        )()
                        user_id_for_prefs = case_owner_id
                    if user_id_for_prefs is not None:
                        from api.agents.graph import _get_store
                        from api.services.user_preference_service import (
                            _RuntimeStub,
                            get_user_preferences_all,
                        )
                        store = _get_store()
                        runtime_stub = _RuntimeStub(store)
                        user_prefs = await sync_to_async(
                            get_user_preferences_all
                        )(runtime_stub, str(user_id_for_prefs))
                        if user_prefs:
                            run_options = {**run_options, **user_prefs}
                            # 同步更新 WorkflowRun.run_options 让偏好持久化（便于审计/前端展示）
                            if run_id is not None:
                                await _update_workflow_run(
                                    run_id, run_options=run_options,
                                )
                except Exception as pref_err:
                    logger.debug(
                        f"读取用户偏好失败 (case={case_id}): {pref_err}"
                    )

                # P7：全新运行初次启动前清理复用同一 thread_id 的历史残留事件，
                # 避免旧运行（如开发环境重置主库致 run_id 重排）事件被回放污染本次流。
                # 仅在此 fresh-start 分支调用；fork / resume 复用 thread_id 不得清理。
                try:
                    await depot.clear_thread(thread_id)
                except Exception as clear_err:
                    logger.debug(
                        f"清理历史事件失败 (thread={thread_id}): {clear_err}"
                    )

                eid = await depot.persist(thread_id, "workflow.start", {
                    "thread_id": thread_id,
                    "case_id": case_id,
                    "run_id": run_id,
                    "evidence_ids": (initial_state or {}).get("evidence_ids", []),
                    "started_at": _utcnow_iso(),
                })
                await emitter.notify(thread_id, eid)
            else:
                # Task 3.1：resume 分支从 thread_id 反查 run_id，更新 status=running
                run_id = _parse_run_id_from_thread_id(thread_id)
                if run_id is not None:
                    try:
                        await _update_workflow_run(
                            run_id,
                            status='running',
                            error_message='',
                        )
                    except Exception as run_err:
                        logger.warning(
                            f"resume 时更新 WorkflowRun 失败 (run_id={run_id}): {run_err}"
                        )

                if resume.get("interrupt_type") == "stage_pause":
                    eid = await depot.persist(thread_id, "workflow.resumed", {
                        "paused_after": resume.get("paused_after"),
                        "run_id": run_id,
                        "ts": _utcnow_iso(),
                    })
                else:
                    corrections = resume.get("corrections", []) if isinstance(resume, dict) else []
                    eid = await depot.persist(thread_id, "review.resumed", {
                        "applied_corrections": corrections,
                        "corrections_count": len(corrections),
                        "run_id": run_id,
                        "ts": _utcnow_iso(),
                    })
                await emitter.notify(thread_id, eid)

            # 2. 构建 workflow + config
            workflow = build_case_workflow()
            config = {"configurable": {"thread_id": thread_id}}

            # Task 5.2.3：resume 分支检查 state_schema_version 兼容性
            # 加载 checkpoint 后若版本不一致，尝试链式迁移；迁移失败则保留旧产物
            # 为只读（metadata.readonly=True）并返回提示「此运行基于旧版本，建议重新发起」。
            if resume:
                try:
                    from api.agents.version import (
                        MigrationError as _MigrationErr,
                    )
                    from api.agents.version import (
                        WorkflowVersion as _WorkflowVersion,
                    )
                    from api.agents.version import migrate_state as _migrate_state

                    snapshot = await workflow.aget_state(config)
                    checkpoint_values = (
                        snapshot.values if snapshot and snapshot.values else {}
                    )
                    checkpoint_version = checkpoint_values.get(
                        "state_schema_version"
                    )
                    current_version = _WorkflowVersion.STATE_SCHEMA_VERSION

                    if (
                        checkpoint_version is not None
                        and checkpoint_version != current_version
                    ):
                        try:
                            migrated_state = _migrate_state(
                                dict(checkpoint_values),
                                int(checkpoint_version),
                                int(current_version),
                            )
                            # 写回迁移后的 state 到 checkpoint
                            await workflow.aupdate_state(config, migrated_state)
                            migration_eid = await depot.persist(
                                thread_id, "workflow.state_migrated", {
                                    "from_version": checkpoint_version,
                                    "to_version": current_version,
                                    "run_id": run_id,
                                    "ts": _utcnow_iso(),
                                }
                            )
                            await emitter.notify(thread_id, migration_eid)
                            logger.info(
                                f"State schema 迁移成功 (thread={thread_id}, "
                                f"v{checkpoint_version}→v{current_version})"
                            )
                        except _MigrationErr as mig_err:
                            logger.error(
                                f"State schema 迁移失败 (thread={thread_id}, "
                                f"v{checkpoint_version}→v{current_version}): {mig_err}"
                            )
                            # 标记旧产物为只读
                            if run_id is not None:
                                try:
                                    await _mark_artifacts_readonly(run_id)
                                except Exception as mark_err:
                                    logger.warning(
                                        f"标记产物只读失败 (run_id={run_id}): {mark_err}"
                                    )
                                # 同步 WorkflowRun 状态为 failed
                                try:
                                    from django.utils import timezone as _tz
                                    await _update_workflow_run(
                                        run_id,
                                        status='failed',
                                        finished_at=_tz.now(),
                                        error_message=(
                                            f"State schema 迁移失败: {mig_err}"
                                        )[:2000],
                                    )
                                except Exception as run_err:
                                    logger.warning(
                                        f"标记 WorkflowRun failed 失败 "
                                        f"(run_id={run_id}): {run_err}"
                                    )
                            fail_eid = await depot.persist(
                                thread_id, "workflow.migration_failed", {
                                    "message": "此运行基于旧版本，建议重新发起",
                                    "from_version": checkpoint_version,
                                    "to_version": current_version,
                                    "error": str(mig_err)[:500],
                                    "run_id": run_id,
                                    "ts": _utcnow_iso(),
                                }
                            )
                            await emitter.notify(thread_id, fail_eid)
                            return
                except Exception as state_err:
                    # 降级：checkpoint 加载或版本检查失败时不阻塞 resume，
                    # 让 LangGraph 自行处理（可能因 schema 不兼容而失败，但至少尝试）
                    logger.warning(
                        f"加载 checkpoint 检查 schema 版本失败 "
                        f"(thread={thread_id}): {state_err}"
                    )

            # 3. 消费 astream_events（v2 协议）
            # HITL 恢复必须使用 Command(resume=...)（对齐 langgraph-human-in-the-loop skill）。
            # 普通 dict 会导致 graph 从最新 checkpoint 恢复但表现为 stuck（无 interrupt_id 关联）；
            # Command(resume=...) 正确关联到 interrupt() 调用点，节点从中断后第一行恢复执行。
            #
            # Task 3.3：fork_config 启动（RetryService 局部重跑）
            # 对齐 langgraph-persistence skill 的 graph.invoke(None, fork_config) 模式：
            # 传 None 给 input，使用 fork_config 作为 config 从 fork 点恢复执行。
            if fork_config:
                stream = workflow.astream_events(
                    None, config=fork_config, version="v2"
                )
            elif resume:
                stream = workflow.astream_events(
                    Command(resume=resume), config=config, version="v2"
                )
            else:
                stream = workflow.astream_events(
                    initial_state, config=config, version="v2"
                )

            mapper = SSEEventMapper()
            token_parts: list[str] = []
            token_started_at: float | None = None
            token_limit = max(1, int(os.environ.get("SSE_TOKEN_BATCH_SIZE", "50")))
            token_interval = max(0.05, float(os.environ.get("SSE_TOKEN_BATCH_INTERVAL", "0.5")))

            async def flush_tokens() -> None:
                nonlocal token_started_at
                if not token_parts:
                    return
                eid = await depot.persist(thread_id, "complaint.token", {
                    "delta": "".join(token_parts),
                    "node": mapper.current_node,
                    "run_id": run_id,
                })
                token_parts.clear()
                token_started_at = None
                await emitter.notify(thread_id, eid)

            async for raw_event in stream:
                try:
                    sse_events = await mapper.map(raw_event)
                except Exception as map_err:
                    logger.warning(
                        f"映射事件失败 (thread={thread_id}): {map_err}",
                        exc_info=True,
                    )
                    continue

                # Task 3.1：同步 mapper 当前进度字段到 WorkflowRun（每个事件节流一次）
                if run_id is not None:
                    try:
                        progress_fields = {}
                        if hasattr(mapper, 'current_revision') and mapper.current_revision is not None:
                            progress_fields['revision'] = mapper.current_revision
                        if hasattr(mapper, 'current_stage') and mapper.current_stage:
                            progress_fields['current_stage'] = mapper.current_stage
                        if mapper.current_node:
                            progress_fields['current_node'] = mapper.current_node
                        if hasattr(mapper, 'current_progress') and mapper.current_progress is not None:
                            progress_fields['progress'] = mapper.current_progress
                        if progress_fields:
                            await _update_workflow_run(run_id, **progress_fields)
                    except Exception as sync_err:
                        logger.debug(
                            f"同步 WorkflowRun 进度失败 (run_id={run_id}): {sync_err}"
                        )

                for sse_event in sse_events:
                    if sse_event.type == "complaint.token":
                        if token_started_at is None:
                            token_started_at = asyncio.get_running_loop().time()
                        token_parts.append(str(sse_event.payload.get("delta", "")))
                        elapsed = asyncio.get_running_loop().time() - token_started_at
                        if len(token_parts) >= token_limit or elapsed >= token_interval:
                            await flush_tokens()
                        continue
                    await flush_tokens()
                    # 注入 run_id 到 SSE 事件 payload（Task 3.1 统一信封）
                    sse_payload = dict(sse_event.payload)
                    if run_id is not None and 'run_id' not in sse_payload:
                        sse_payload['run_id'] = run_id
                    eid = await depot.persist(thread_id, sse_event.type, sse_payload)
                    await emitter.notify(thread_id, eid)

            await flush_tokens()

            # 4. 区分阶段暂停、HITL 审核中断与图真正结束。
            snapshot = await workflow.aget_state(config)
            interrupts = snapshot_interrupts(snapshot)

            # Task 2.2.4: 统一持久化 intervention.created SSE 事件
            # 对所有含 intervention_id 的 interrupt payload 推送 intervention.created，
            # 让前端 InterventionPanel 根据 form_schema 动态渲染（覆盖 quality_review
            # 与 user_pause 两类介入）。本块仅做事件持久化，不影响后续 stage_pause /
            # waiting_review / completed 分支判定。
            for item in interrupts:
                payload = interrupt_value(item)
                if isinstance(payload, dict) and "intervention_id" in payload:
                    intervention_eid = await depot.persist(
                        thread_id, "intervention.created", {
                            "intervention_id": payload["intervention_id"],
                            "intervention_type": payload.get("interrupt_type"),
                            "intervention_kind": payload.get("intervention_kind"),
                            "required": payload.get("required"),
                            "stage": payload.get("stage"),
                            "reason": payload.get("reason"),
                            "base_revision": payload.get("base_revision"),
                            "form_schema": payload.get("form_schema"),
                            "initial_values": payload.get("initial_values"),
                            "impact": payload.get("impact"),
                            "thread_id": thread_id,
                            "case_id": case_id,
                            "run_id": run_id,
                            "ts": _utcnow_iso(),
                        }
                    )
                    await emitter.notify(thread_id, intervention_eid)

            # 输入质量门 Gate 2：用户在 extract_node 选择终止（abort）时，节点已
            # Command(goto=END) 跳过文书生成并写入 workflow_aborted_by_user=True。
            # 此处优先检测该标记并 fail_processing，给出精确失败信息，避免落入
            # 「未生成有效文稿」的通用 complete_processing 失败分支。
            final_values = snapshot.values if snapshot and snapshot.values else {}
            if final_values.get("workflow_aborted_by_user"):
                abort_message = (
                    "用户主动终止：证据质量不足，请重新上传证据后再次启动工作流"
                )
                try:
                    await sync_to_async(fail_processing, thread_sensitive=True)(
                        case_id, abort_message
                    )
                except Exception as state_err:
                    logger.error(
                        f"同步用户终止失败状态异常 (case={case_id}): {state_err}"
                    )
                if run_id is not None:
                    try:
                        from django.utils import timezone as _tz
                        await _update_workflow_run(
                            run_id,
                            status='failed',
                            finished_at=_tz.now(),
                            error_message=abort_message,
                        )
                    except Exception as run_err:
                        logger.warning(
                            f"标记 WorkflowRun failed（用户终止）失败 "
                            f"(run_id={run_id}): {run_err}"
                        )
                abort_eid = await depot.persist(thread_id, "workflow.error", {
                    "message": abort_message,
                    "node": "extract",
                    "run_id": run_id,
                    "recoverable": False,
                    "aborted_by_user": True,
                    "ts": _utcnow_iso(),
                })
                await emitter.notify(thread_id, abort_eid)
                logger.info(
                    f"工作流被用户终止 (thread={thread_id}, case={case_id}, "
                    f"run_id={run_id})"
                )
                return

            stage_pause = next(
                (
                    interrupt_value(item)
                    for item in interrupts
                    if is_stage_pause_interrupt_value(interrupt_value(item))
                ),
                None,
            )
            if stage_pause:
                # 兼容新旧 payload：旧 payload 用 paused_after，新 payload（Task 2.2.2）用 stage
                paused_after = (
                    stage_pause.get("paused_after")
                    or stage_pause.get("stage", "")
                )
                changed = await sync_to_async(mark_paused, thread_sensitive=True)(case_id, paused_after)
                # Task 3.1：同步 WorkflowRun 状态为 waiting_user（替代旧 pausing/paused）
                if run_id is not None:
                    try:
                        from django.utils import timezone as _tz
                        await _update_workflow_run(
                            run_id,
                            status='waiting_user',
                            current_stage=paused_after or '',
                        )
                    except Exception as run_err:
                        logger.warning(
                            f"标记 WorkflowRun waiting_user 失败 (run_id={run_id}): {run_err}"
                        )
                if changed:
                    paused_eid = await depot.persist(thread_id, "workflow.paused", {
                        **stage_pause,
                        "thread_id": thread_id,
                        "case_id": case_id,
                        "run_id": run_id,
                        "ts": _utcnow_iso(),
                    })
                    await emitter.notify(thread_id, paused_eid)
                return

            if snapshot.next:
                await sync_to_async(mark_waiting_review, thread_sensitive=True)(case_id)
                # Task 3.1：同步 WorkflowRun 状态为 waiting_user
                if run_id is not None:
                    try:
                        await _update_workflow_run(
                            run_id,
                            status='waiting_user',
                        )
                    except Exception as run_err:
                        logger.warning(
                            f"标记 WorkflowRun waiting_user 失败 (run_id={run_id}): {run_err}"
                        )
                waiting_eid = await depot.persist(thread_id, "workflow.waiting_review", {
                    "thread_id": thread_id,
                    "case_id": case_id,
                    "run_id": run_id,
                    "next_nodes": list(snapshot.next),
                    "ts": _utcnow_iso(),
                })
                await emitter.notify(thread_id, waiting_eid)
                return

            # 5. 图真正结束后校验数据库中的文稿产物，再推进案件生命周期
            completion = await sync_to_async(complete_processing, thread_sensitive=True)(
                case_id, thread_id=thread_id
            )
            if completion.case.workflow_status != 'succeeded':
                # Task 3.1：同步 WorkflowRun 状态为 failed
                if run_id is not None:
                    try:
                        from django.utils import timezone as _tz
                        await _update_workflow_run(
                            run_id,
                            status='failed',
                            finished_at=_tz.now(),
                            error_message=completion.case.workflow_error or '工作流未生成有效文稿',
                        )
                    except Exception as run_err:
                        logger.warning(
                            f"标记 WorkflowRun failed 失败 (run_id={run_id}): {run_err}"
                        )
                raise RuntimeError(completion.case.workflow_error or '工作流未生成有效文稿')
            total_duration_ms = int(
                (_utcnow() - workflow_start_time).total_seconds() * 1000
            )
            # Task 3.1：同步 WorkflowRun 状态为 succeeded
            if run_id is not None:
                try:
                    from django.utils import timezone as _tz
                    await _update_workflow_run(
                        run_id,
                        status='succeeded',
                        finished_at=_tz.now(),
                        progress=1.0,
                    )
                except Exception as run_err:
                    logger.warning(
                        f"标记 WorkflowRun succeeded 失败 (run_id={run_id}): {run_err}"
                    )
            final_eid = await depot.persist(thread_id, "workflow.complete", {
                "thread_id": thread_id,
                "case_id": case_id,
                "run_id": run_id,
                "total_duration_ms": total_duration_ms,
                "errors": [],
                "ts": _utcnow_iso(),
            })
            await emitter.notify(thread_id, final_eid)
            logger.info(
                f"工作流完成 (thread={thread_id}, case={case_id}, "
                f"run_id={run_id}, duration={total_duration_ms}ms)"
            )

        except Exception as e:
            # 不可恢复的致命错误：同步案件工作流状态并写入事件
            try:
                await sync_to_async(fail_processing, thread_sensitive=True)(case_id, str(e))
            except Exception as state_err:
                logger.error(f"同步工作流失败状态异常 (case={case_id}): {state_err}")
            # Task 3.1：同步 WorkflowRun 状态为 failed
            if run_id is not None:
                try:
                    from django.utils import timezone as _tz
                    await _update_workflow_run(
                        run_id,
                        status='failed',
                        finished_at=_tz.now(),
                        error_message=str(e)[:2000],
                    )
                except Exception as run_err:
                    logger.warning(
                        f"标记 WorkflowRun failed 失败 (run_id={run_id}): {run_err}"
                    )
            logger.error(
                f"工作流运行失败 (thread={thread_id}, case={case_id}, "
                f"run_id={run_id}): {e}",
                exc_info=True,
            )
            try:
                error_eid = await depot.persist(thread_id, "workflow.error", {
                    "message": str(e)[:500],
                    "node": None,
                    "run_id": run_id,
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
            # 任务结束，从注册表移除；仅删除当前协程对应的已完成条目。
            with self._task_registry_lock:
                task = self._task_registry.get(thread_id)
                if task is not None and task.done():
                    self._task_registry.pop(thread_id, None)

    def start_in_background(
        self,
        case_id: int,
        thread_id: str,
        initial_state: dict | None = None,
        resume: dict | None = None,
        fork_config: dict | None = None,
    ) -> Future[Any]:
        """启动后台任务（不阻塞调用方）。

        若同一 thread_id 已有运行中的任务，先取消旧任务（避免重复运行）。

        Args:
            case_id: 案件 ID
            thread_id: LangGraph checkpointer 线程 ID
            initial_state: 首次启动的初始状态（与 resume / fork_config 互斥）
            resume: HITL 恢复的校正数据（与 initial_state / fork_config 互斥）
            fork_config: RetryService fork 出的 config（Task 3.3，与
                initial_state / resume 互斥；非空时使用 fork_config 作为 config
                传 None 给 astream_events，从 fork 点恢复执行）

        Returns:
            Future 对象
        """
        with self._task_registry_lock:
            old_task = self._task_registry.get(thread_id)
            if old_task is not None and not old_task.done():
                raise RuntimeError(f"工作流任务正在运行 (thread={thread_id})")

        coro = self.run_and_persist(
            case_id=case_id,
            thread_id=thread_id,
            initial_state=initial_state,
            resume=resume,
            fork_config=fork_config,
        )
        try:
            loop = asyncio.get_running_loop()
            task: Future[Any] = loop.create_task(coro)
        except RuntimeError:
            loop = self._ensure_background_loop()
            task = asyncio.run_coroutine_threadsafe(
                coro,
                loop,
            )
        with self._task_registry_lock:
            self._task_registry[thread_id] = task

        # 任务结束回调：确保从注册表清理
        def _on_done(t: Future[Any]) -> None:
            with self._task_registry_lock:
                if self._task_registry.get(thread_id) is t:
                    self._task_registry.pop(thread_id, None)
            if t.cancelled():
                logger.debug(f"后台任务已取消 (thread={thread_id})")
                return
            exc = t.exception()
            if exc is not None:
                logger.error(f"后台任务异常退出 (thread={thread_id}): {exc}")

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
