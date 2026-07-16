# Tasks

## Task 1: 后端数据库迁移补齐
- [ ] SubTask 1.1: 执行 python manage.py makemigrations 生成 workflow_pause_requested / workflow_paused_after / workflow_status 扩展的迁移文件
- [ ] SubTask 1.2: 执行 python manage.py migrate 应用迁移并验证新字段可读写
- [ ] SubTask 1.3: 验证现有 Case 记录的 workflow_status 默认值正确（idle），workflow_pause_requested=False，workflow_paused_after=''

## Task 2: 后端 LangGraph 阶段门节点实现
- [ ] SubTask 2.1: 新建 backend/api/agents/nodes/stage_gate_node.py 实现 stage_gate 函数：
  - 接收 state 参数，读取 case_id
  - 查询 Case.workflow_pause_requested
  - 若 True：调用 interrupt(build_stage_pause_payload(current_node_name))
  - 若 False：直接 return None（放行）
- [ ] SubTask 2.2: 修改 backend/api/agents/graph.py 的 build_case_workflow：
  - 在每个业务节点之后插入条件边到 stage_gate
  - stage_gate 返回 None 时自动进入下一节点；interrupt 时挂起
  - 使用 compile(interrupt_before=[...]) 或条件边方式集成
- [ ] SubTask 2.3: 确保 stage_gate 不影响现有 low_confidence 审核中断逻辑（两种 interrupt_type 区分）

## Task 3: 后端 WorkflowRunner 集成暂停检测与恢复
- [ ] SubTask 3.1: 修改 backend/api/agents/workflow_runner.py：
  - 在 astream_events 循环中检测 on_custom_event 或 on_interrupt 类事件
  - 当检测到 stage_pause 中断时调用 case_lifecycle_service.mark_paused(case_id, node_name)
  - 通过 EventDepot 发送 workflow.paused SSE 事件
- [ ] SubTask 3.2: 修改 resume 逻辑：
  - 区分 waiting_review 恢复和 paused 恢复
  - paused 恢复时读取 edits 参数，调用 build_stage_resume_payload(case, edits) 构建状态回写
  - 使用 Command(resume=resume_payload) 恢复 graph 执行
  - 调用 clear_pause_boundary 清除暂停标记
  - 通过 EventDepot 发送 workflow.resumed SSE 事件
- [ ] SubTask 3.3: 处理并发安全：同一 case 不能同时有多个 runner 实例

## Task 4: 后端 API 补齐（cancel + state）
- [ ] SubTask 4.1: 新增 CaseWorkflowCancelView（POST /api/cases/<id>/workflow/cancel/）：
  - 仅允许 paused/idle 状态下调用
  - 调用 lifecycle service 将状态置为 idle，清除暂停标记
  - 返回 200 及新状态
- [ ] SubTask 4.2: 新增 CaseWorkflowStateView（GET /api/cases/<id>/workflow/state/）：
  - 返回 {workflow_status, workflow_paused_after, editable_scope, stage_products}
  - editable_scope 从 STAGE_EDITABLE_SCOPES[paused_after] 获取
  - stage_products 根据当前暂停阶段从 DB 快照获取
- [ ] SubTask 4.3: 在 urls.py 注册两条新路由
- [ ] SubTask 4.4: 更新 serializers.py 暴露新字段（如需要）

## Task 5: 后端 SSE 事件协议完善
- [ ] SubTask 5.1: 在 workflow-events EventType 中新增 workflow.cancelled 类型
- [ ] SubTask 5.2: 在 sse-client.ts 的 EVENT_TYPES 列表中加入 workflow.cancelled
- [ ] SubTask 5.3: 在 sse_event_mapper.py 中区分暂停相关事件
- [ ] SubTask 5.4: 在 lifecycle service 取消/失败等路径中发送 workflow.cancelled 事件

## Task 6: 前端 StagePausePanel 组件实现
- [ ] SubTask 6.1: 实现 frontend/src/components/workflow/StagePausePanel.tsx：
  - props: caseId
  - 从 store 读取 pauseData（含 paused_after 和 editable_scope）
  - 展示暂停阶段名称和说明文字
  - 根据 editable_scope 动态渲染表单（evidences/extracted_fields/timeline_nodes/document）
  - 底部按钮：继续工作流 / 取消工作流
  - 加载态/错误态处理
- [ ] SubTask 6.2: 表单预填充：从 GET /api/cases/<id>/workflow/state/ 获取当前产物数据作为初始值
- [ ] SubTask 6.3: 表单校验：字段长度限制与必填项（参考 LIMITS 配置）

## Task 7: 前端 Store 与 API 补齐
- [ ] SubTask 7.1: 在 case-store.ts 新增 cancelWorkflow action
- [ ] SubTask 7.2: 在 case-store.ts 新增 fetchWorkflowState action
- [ ] SubTask 7.3: 在 case-store.ts applySSEEvent 中增加 workflow.cancelled 分支
- [ ] SubTask 7.4: 在 api.ts 新增 cancelWorkflow 和 getWorkflowState 方法

## Task 8: 前端 WorkflowStreamPanel 暂停交互完善
- [ ] SubTask 8.1: 完善 WorkflowStreamPanel.tsx 的暂停按钮逻辑（running 显示/pausing 提示/paused 隐藏）
- [ ] SubTask 8.2: 页面刷新恢复：当 workflow_status=paused 时自动 fetchWorkflowState 并渲染 StagePausePanel
- [ ] SubTask 8.3: NodeTrack.tsx paused 状态视觉优化（高亮当前暂停节点）

## Task 9: 性能优化实施
- [ ] SubTask 9.1: SSE Token 流批量持久化（缓冲区 + 阈值批量写入 DB）
- [ ] SubTask 9.2: LangGraph Checkpoint 节流配置评估与实施
- [ ] SubTask 9.3: 事件回放分批处理（requestAnimationFrame 或 setTimeout 分批 applySSEEvent）

## Task 10: 验证与测试
- [ ] SubTask 10.1: 后端 Python 语法检查
- [ ] SubTask 10.2: Django 系统检查
- [ ] SubTask 10.3: 迁移验证
- [ ] SubTask 10.4: 前端构建检查（修复 StagePausePanel 空文件问题）
- [ ] SubTask 10.5: 手动冒烟测试路径（5 条核心场景）
- [ ] SubTask 10.6: Git diff 检查无多余空白字符

# Task Dependencies
- Task 1 (迁移) 是所有后端任务的前置
- Task 2 (阶段门) 依赖 Task 1
- Task 3 (Runner) 依赖 Task 1 + Task 2
- Task 4 (API) 依赖 Task 1
- Task 5 (SSE协议) 依赖 Task 4
- Task 6 (StagePausePanel) 可与 Task 2-5 并行开发
- Task 7 (Store/API) 依赖 Task 4
- Task 8 (UI完善) 依赖 Task 6 + Task 7
- Task 9 (性能) 可独立进行，建议在 Task 5 之后
- Task 10 (验证) 依赖所有任务完成
