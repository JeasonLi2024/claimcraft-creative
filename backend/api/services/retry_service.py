# -*- coding: utf-8 -*-
"""工作流局部重跑服务（Task 3.3，对齐 langgraph-persistence skill）。

使用 LangGraph Time Travel 实现：
- graph.aget_state_history(config) 找到 from_stage 对应的历史 checkpoint
- graph.aupdate_state(past.config, fork_state) fork 新分支
- graph.invoke(None, fork_config) 从 fork 点恢复执行（由 WorkflowRunner 后台启动）

重要（对齐 langgraph-persistence skill 的 Time Travel 模式 + Overwrite reducer 规则）：
- update_state 会穿过 reducer，对 list 字段必须使用 Overwrite 包装避免追加
- fork 出的新运行使用新 thread_id（由 LangGraph 在 aupdate_state 时生成，
  回写到新 WorkflowRun.thread_id 替代默认 case-{case_id}-run-{id}）
- 下游产物自动标记为 stale（通过 artifact_service.mark_artifacts_stale 传播）
- preserve_user_confirmed=True 时保留 user_confirmed_fields（merge_dict reducer 不替换）

参考 langgraph-persistence skill 的 Time Travel 模式：
    states = list(graph.get_state_history(config))
    past = states[-2]  # 倒数第二个 checkpoint
    fork_config = graph.update_state(past.config, {"messages": ["edited"]})
    result = graph.invoke(None, fork_config)

参考 Overwrite reducer 规则（langgraph-persistence skill fix-update-state-with-reducers）：
    # State with reducer: items: Annotated[list, operator.add]
    # 直接传 list 会被 reducer 追加
    graph.update_state(config, {"items": ["C"]})  # Result: ["A", "B", "C"] - Appended!
    # 用 Overwrite 替换
    graph.update_state(config, {"items": Overwrite(["C"])})  # Result: ["C"] - Replaced
"""
import logging
from typing import Optional

from asgiref.sync import sync_to_async
from django.db import transaction

from api.agents.artifact_service import mark_artifacts_stale
from api.agents.graph import build_case_workflow
from api.models import WorkflowArtifact, WorkflowRun

logger = logging.getLogger(__name__)


# 阶段 → checkpoint 标识节点名映射（用于在 state history 中找到对应 checkpoint）
# 节点完成后 state 中 current_node 字段会写入此值
# 与 graph.py build_case_workflow 节点顺序对齐
STAGE_TO_LAST_NODE = {
    'material_understanding': 'classify',   # preclassify + ocr + classify 完成
    'fact_checking': 'review',              # extract + review 完成（review 走过则进入 evidence_chain）
    'case_organization': 'evidence_chain',  # evidence_chain 完成
    'document_generation': 'complaint',     # complaint 完成（默认 complain 模式）
}


class RetryService:
    """局部重跑服务（基于 LangGraph Time Travel）。

    使用 graph.aget_state_history + aupdate_state + Overwrite 实现：
    1. 找到源运行 thread_id 中 current_node == target_node 的 checkpoint
    2. 用 Overwrite 清空下游 list 字段（避免 reducer 追加旧数据）
    3. fork 出新 thread_id，创建新 WorkflowRun 记录 fork 关系
    4. 标记源运行下游产物为 stale（递归传播）
    5. 启动 WorkflowRunner 后台从 fork_config 恢复执行
    """

    async def retry_from_stage(
        self,
        source_run_id: int,
        from_stage: str,
        preserve_user_confirmed: bool = True,
        fork_state_overrides: Optional[dict] = None,
        started_by_id: Optional[int] = None,
    ) -> WorkflowRun:
        """从指定阶段 fork 出新运行并恢复执行。

        Args:
            source_run_id: 源运行 ID
            from_stage: 从哪个业务阶段重跑
                (material_understanding / fact_checking / case_organization / document_generation)
            preserve_user_confirmed: 是否保留 user_confirmed_fields（默认 True）
            fork_state_overrides: 额外的 state 覆盖（如指定新模板类型等）
            started_by_id: 发起人 ID

        Returns:
            新创建的 WorkflowRun（已 fork 启动）

        Raises:
            WorkflowRun.DoesNotExist: 源运行不存在
            ValueError: from_stage 无效或源运行状态不允许重跑
            RuntimeError: 找不到对应 checkpoint 或 fork 失败
        """
        # 1. 校验源运行
        source_run = await sync_to_async(self._get_source_run)(source_run_id)
        if source_run.status not in ('failed', 'succeeded', 'waiting_user'):
            raise ValueError(
                f'源运行状态 {source_run.status} 不允许重跑'
                f'（需 failed/succeeded/waiting_user）'
            )

        if from_stage not in STAGE_TO_LAST_NODE:
            raise ValueError(f'无效的 from_stage: {from_stage}')

        target_node = STAGE_TO_LAST_NODE[from_stage]

        # 2. 构建 graph（复用 build_case_workflow，含 PostgresSaver）
        workflow = build_case_workflow()
        source_config = {"configurable": {"thread_id": source_run.thread_id}}

        # 3. 获取 state history 找到目标 checkpoint
        #    对齐 langgraph-persistence skill：
        #    states = list(graph.get_state_history(config))
        try:
            state_history = []
            async for state in workflow.aget_state_history(source_config):
                state_history.append(state)
                # 取足够多的 checkpoint 即可，避免无限累积
                if len(state_history) >= 200:
                    break
        except Exception as e:
            logger.error(
                f"获取 state history 失败 (run={source_run_id}): {e}",
                exc_info=True,
            )
            raise RuntimeError(f"获取 state history 失败: {e}")

        # 找到 current_node == target_node 的最新 checkpoint
        # state.values 是当前 state 的快照，current_node 由节点返回写入
        target_checkpoint = None
        for state in state_history:
            state_values = state.values or {}
            current_node = state_values.get('current_node', '')
            if current_node == target_node:
                target_checkpoint = state
                break

        if target_checkpoint is None:
            raise RuntimeError(
                f'未找到 from_stage={from_stage} (node={target_node}) 对应的 checkpoint'
            )

        # 4. 准备 fork_state
        #    对齐 langgraph-persistence skill fix-update-state-with-reducers：
        #    列表字段使用 Overwrite([]) 替换，避免 add reducer 追加
        #    merge_dict reducer 字段（user_confirmed_fields）用 Overwrite({}) 替换
        from langgraph.types import Overwrite

        fork_state: dict = {}

        # 重置下游字段（清空列表，等待重新生成）
        # 列表字段使用 Overwrite([]) 替换，避免 add reducer 追加
        downstream_list_fields = self._get_downstream_list_fields(from_stage)
        for field in downstream_list_fields:
            fork_state[field] = Overwrite([])

        # 重置标量字段（覆盖，无 reducer）
        target_values = target_checkpoint.values or {}
        fork_state['revision'] = target_values.get('revision', 0)
        fork_state['current_stage'] = from_stage
        fork_state['current_node'] = ''
        fork_state['progress'] = self._get_stage_base_progress(from_stage)

        # 重置 stale_artifact_ids（自定义 dedup_add reducer：用 Overwrite 替换）
        fork_state['stale_artifact_ids'] = Overwrite([])

        # 保留 user_confirmed_fields（preserve_user_confirmed=True 不替换）
        # merge_dict 是合并 reducer，传空 dict 不会清空，需用 Overwrite({}) 才能清空
        if not preserve_user_confirmed:
            fork_state['user_confirmed_fields'] = Overwrite({})

        # 应用额外覆盖
        if fork_state_overrides:
            for k, v in fork_state_overrides.items():
                # 用户传 list 直接覆盖时也用 Overwrite 包装
                # 避免被 add reducer 追加到旧值
                if isinstance(v, list):
                    fork_state[k] = Overwrite(v)
                elif isinstance(v, dict) and k == 'user_confirmed_fields':
                    # dict 字段使用 merge_dict reducer，传新 dict 会合并；
                    # 若要整体替换则用 Overwrite 包装（保留默认 merge 行为）
                    fork_state[k] = Overwrite(v)
                else:
                    fork_state[k] = v

        # 5. 在 DB 创建新 WorkflowRun（fork 出的）
        #    对齐 spec：parent_run 指向源运行，thread_id 由 save() 自动生成
        #    使用事务确保原子性（创建 run + fork state + 标记 stale）
        new_run = await sync_to_async(self._create_fork_run)(
            source_run=source_run,
            started_by_id=started_by_id,
        )

        # 6. fork state（对齐 langgraph-persistence skill）
        #    fork_config = graph.update_state(past.config, fork_state)
        #    使用 aupdate_state 异步版本（节点是 async def）
        try:
            fork_config = await workflow.aupdate_state(
                target_checkpoint.config, fork_state, as_node=target_node
            )
        except Exception as e:
            logger.error(
                f"update_state fork 失败 (run={source_run_id}): {e}",
                exc_info=True,
            )
            # 清理已创建的 WorkflowRun
            await sync_to_async(new_run.delete)()
            raise RuntimeError(f"fork state 失败: {e}")

        # 7. 将 fork_config 中的 thread_id 回写到新 WorkflowRun
        #    （覆盖默认生成的 case-{case_id}-run-{id}）
        #    对齐 spec：每个 WorkflowRun 拥有独立 thread_id
        fork_thread_id = (
            fork_config.get("configurable", {}).get("thread_id")
            if isinstance(fork_config, dict) else None
        )
        if fork_thread_id and fork_thread_id != new_run.thread_id:
            await sync_to_async(WorkflowRun.objects.filter(pk=new_run.id).update)(
                thread_id=fork_thread_id
            )
            new_run.thread_id = fork_thread_id

        # 8. 标记源运行下游产物为 stale（artifact_service.mark_artifacts_stale 传播）
        downstream_artifact_ids = await sync_to_async(self._get_downstream_artifact_ids)(
            source_run_id, from_stage
        )
        if downstream_artifact_ids:
            marked_count = await sync_to_async(mark_artifacts_stale)(
                source_run_id, downstream_artifact_ids, reason='retry_forked'
            )
            logger.info(
                f"已标记 {marked_count} 个下游产物为 stale "
                f"(source_run={source_run_id}, from_stage={from_stage})"
            )

        # 9. 更新 Case.active_workflow_run 指向新运行
        await sync_to_async(self._update_case_active_run)(
            source_run.case_id, new_run.id
        )

        # 10. 启动新运行的 WorkflowRunner（异步后台执行）
        #     使用新 thread_id，invoke(None, fork_config) 在 runner 内部完成
        #     注意：此处不直接 await invoke，而是通过 WorkflowRunner 后台启动
        from api.agents.workflow_runner import WorkflowRunner

        runner = WorkflowRunner()
        runner.start_in_background(
            case_id=source_run.case_id,
            thread_id=new_run.thread_id,  # 新 thread_id（已回写为 fork_thread_id）
            initial_state=None,
            resume=None,
            fork_config=fork_config,  # Task 3.3 新参数：fork 出的 config
        )

        logger.info(
            f"已启动 fork 运行 (source_run={source_run_id}, new_run={new_run.id}, "
            f"from_stage={from_stage}, thread_id={new_run.thread_id})"
        )

        return new_run

    # ------------------------------------------------------------------ #
    # 辅助方法（同步，由 sync_to_async 包装）
    # ------------------------------------------------------------------ #

    def _get_source_run(self, source_run_id: int) -> WorkflowRun:
        """获取源 WorkflowRun（带 select_related case）。"""
        return WorkflowRun.objects.select_related('case').get(pk=source_run_id)

    def _create_fork_run(
        self,
        source_run: WorkflowRun,
        started_by_id: Optional[int],
    ) -> WorkflowRun:
        """创建新 WorkflowRun 记录，parent_run 指向源运行。

        thread_id 由模型 save() 自动生成（case-{case_id}-run-{new_id}），
        后续若 LangGraph fork 返回不同 thread_id 则回写覆盖。

        使用事务确保 run 创建 + 状态字段一致性。
        """
        with transaction.atomic():
            new_run = WorkflowRun.objects.create(
                case=source_run.case,
                parent_run=source_run,
                workflow_version=source_run.workflow_version,
                state_schema_version=source_run.state_schema_version,
                policy_version=source_run.policy_version,
                prompt_bundle_version=source_run.prompt_bundle_version,
                status='queued',
                selected_evidence_ids=source_run.selected_evidence_ids,
                run_options=source_run.run_options,
                started_by_id=started_by_id or source_run.started_by_id,
            )
        return new_run

    def _get_downstream_list_fields(self, from_stage: str) -> list[str]:
        """获取 from_stage 及之后阶段对应的 state 列表字段（需要清空等待重新生成）。

        对齐 CaseWorkflowState 中 Annotated[list, add] 字段定义。
        注意：from_stage 本身的字段也需清空（因为该阶段要重新执行）。
        """
        # 阶段 → 累积列表字段映射（对应 CaseWorkflowState 中的 list 字段）
        all_stages_fields = {
            'material_understanding': [
                'evidence_preclassify_results',
                'evidence_ocr_results',
                'evidence_classify_results',
            ],
            'fact_checking': [
                'evidence_extract_results',
                'errors',
                'warnings',
                'issues',
                'provenance',
            ],
            'case_organization': [
                'evidence_chain',
                'evidence_chain_tool_calls',
            ],
            'document_generation': [
                'complaint_tool_calls',
            ],
        }
        stage_order = [
            'material_understanding',
            'fact_checking',
            'case_organization',
            'document_generation',
        ]
        try:
            start_idx = stage_order.index(from_stage)
        except ValueError:
            return []
        downstream: list[str] = []
        for stage in stage_order[start_idx:]:
            downstream.extend(all_stages_fields.get(stage, []))
        return downstream

    def _get_stage_base_progress(self, from_stage: str) -> float:
        """获取 from_stage 的基础进度（用于重置 run.progress）。

        4 阶段等分总体进度 0.0-1.0：
        - material_understanding: 0.0
        - fact_checking: 0.25
        - case_organization: 0.5
        - document_generation: 0.75
        """
        progress_map = {
            'material_understanding': 0.0,
            'fact_checking': 0.25,
            'case_organization': 0.5,
            'document_generation': 0.75,
        }
        return progress_map.get(from_stage, 0.0)

    def _get_downstream_artifact_ids(
        self, source_run_id: int, from_stage: str
    ) -> list[int]:
        """获取源运行中下游阶段的 current artifact IDs。

        下游 = from_stage 本身 + 之后所有阶段（这些会被重新生成，旧版本标 stale）。
        仅返回 status='current' 的产物（已 superseded / stale 的不重复标记）。
        """
        stage_order = [
            'material_understanding',
            'fact_checking',
            'case_organization',
            'document_generation',
        ]
        try:
            start_idx = stage_order.index(from_stage)
        except ValueError:
            return []
        downstream_stages = stage_order[start_idx:]
        return list(
            WorkflowArtifact.objects.filter(
                workflow_run_id=source_run_id,
                stage__in=downstream_stages,
                status='current',
            ).values_list('id', flat=True)
        )

    def _update_case_active_run(self, case_id: int, run_id: int) -> None:
        """更新 Case.active_workflow_run 指向新运行。"""
        from api.models import Case
        Case.objects.filter(pk=case_id).update(active_workflow_run_id=run_id)
