# 工作流阶段暂停与用户参与 Spec

> 本阶段聚焦于让用户深度参与工作流执行过程：在每个业务阶段完成后可手动暂停、修改阶段产物、安全回写状态后继续执行；同时对前端展示与后端性能进行优化。

## Why
当前工作流以全自动方式一次性跑完，用户无法在中间环节介入纠正。实际维权场景中：
- 证据分类/OCR 结果需要人工校验
- 抽取字段低置信度时需要修正
- 投诉文稿的语气/内容需要微调
- 时间线链条需要人工补全
用户需要"看得见、停得住、改得了、能继续"的工作流参与能力。

## What Changes

### 数据模型（已有骨架，需补齐）
- Case.workflow_pause_requested 已落盘
- Case.workflow_paused_after 已落盘
- Case.workflow_status 新增 pausing/paused 状态 已落盘
- 待补充：数据库迁移文件未生成，需确保 makemigrations + migrate 成功

### 后端 LangGraph 阶段门（核心缺口）
- 当前 graph.py 未集成阶段门节点
- 需在每个业务节点后插入 stage_gate 条件边
- stage_gate 逻辑：检查 pause_requested 则 interrupt()，False 直接进入下一节点
- 低置信度审核仍走 interrupt()，但 interrupt_type 为 low_confidence，与 stage_pause 区分

### 后端 API（部分完成，需闭环）
- POST /api/cases/<id>/workflow/pause/ 视图骨架已有
- POST /api/cases/<id>/workflow/resume/ 已扩展支持 stage_pause 类型恢复
- POST /api/cases/<id>/workflow/cancel/ 未实现
- GET /api/cases/<id>/workflow/state/ 未实现
- WorkflowRunner 未集成 mark_paused 与 stage_pause 中断检测
- WorkflowRunner 恢复时未使用 build_stage_resume_payload 构建状态回写

### 后端阶段编辑服务（基本完成）
- workflow_pause_service.py 已实现完整的编辑校验与状态回写构建器

### 后端 SSE 事件协议（部分完成）
- workflow.pause_requested / paused / resumed 已定义
- workflow.cancelled 未定义
- complaint.token 逐 token 持久化 性能问题未解决

### 前端状态管理（大部分完成，需补齐）
- case-store.ts 已扩展暂停相关状态与 action
- case-store.ts 缺少 workflow.cancelled 处理与获取可编辑范围 action

### 前端 UI 组件（关键缺口）
- StagePausePanel.tsx 空文件，已被 ProductStream.tsx 引用，会导致构建失败
- 缺少：阶段可编辑字段表单、产物预览、继续/取消操作按钮

### 前端 API 层（部分完成）
- api.ts 缺少 cancelWorkflow 和 getWorkflowState

### 性能优化（未落地）
- complaint.token 批量持久化、checkpoint 节流、事件回放分批

## Impact
- Affected specs: add-t1-product-closure, add-image-ocr-dynamic-generation
- Affected code: 见上方各节列出的文件清单

## ADDED Requirements

### Requirement: LangGraph 阶段门节点
系统 SHALL 在每个业务节点后插入 stage_gate 条件边，检查暂停请求并在节点边界安全中断。
#### Scenario: 用户请求暂停后，当前阶段节点完成即暂停
- GIVEN 工作流正在运行且用户已请求暂停
- WHEN 当前业务节点执行完成
- THEN stage_gate 检测到暂停请求，调用 interrupt() 传递阶段暂停 payload
- AND 工作流状态变为 paused，前端收到 workflow.paused SSE 事件
#### Scenario: 未请求暂停时阶段门放行
- WHEN 当前业务节点执行完成且未请求暂停
- THEN stage_gate 直接进入下一节点
#### Scenario: 低置信度审核中断与阶段暂停共存
- WHEN 低置信度中断优先触发
- THEN 用户修正后恢复，stage_gate 再次检查暂停请求，在下一个节点边界暂停

### Requirement: 阶段产物编辑与状态回写
系统 SHALL 允许用户在暂停态修改当前阶段允许编辑的字段，并将修改安全回写到 LangGraph checkpoint 和数据库。
#### Scenario: 暂停态修改证据分类
- WHEN 用户在 classify 节点暂停后修改 evidence_category
- THEN 数据库更新，恢复后 checkpoint 同步覆盖
#### Scenario: 暂停态修改抽取字段
- WHEN 用户在 extract/review 节点暂停后修改 field_value
- THEN ExtractedField 更新（confidence=1.0），恢复后 checkpoint 同步
#### Scenario: 不允许修改范围外的字段
- WHEN 用户尝试修改不可编辑的字段
- THEN 后端返回 400 错误

### Requirement: 工作流取消
系统 SHALL 允许用户在暂停态取消工作流。
#### Scenario: 暂停态取消工作流
- WHEN 用户在暂停态点击"取消工作流"
- THEN 状态变为 idle，清除暂停标记，前端收到 workflow.cancelled 事件

### Requirement: 工作流当前状态查询
系统 SHALL 提供 API 返回当前工作流的可编辑范围与阶段产物快照。
#### Scenario: 前端恢复暂停态
- WHEN 用户刷新页面时工作流处于 paused 状态
- THEN 前端获取可编辑范围和产物数据，渲染编辑面板

### Requirement: 阶段暂停交互面板
前端 SHALL 在工作流暂停时展示阶段编辑面板。
#### Scenario: 暂停态展示编辑面板
- THEN StagePausePanel 展示：暂停阶段名称、可编辑字段表单、"继续工作流"/"取消工作流"按钮
#### Scenario: 编辑并继续
- WHEN 用户修改字段后点击"继续工作流"
- THEN 调用 resumePausedWorkflow API 传递 edits，工作流恢复运行

## MODIFIED Requirements
### Requirement: 工作流恢复（扩展阶段暂停恢复）
原：仅支持 waiting_review 态恢复。现：新增 paused 态恢复，恢复时可选携带阶段编辑数据。
### Requirement: 工作流状态展示（扩展暂停态）
原：状态仅 idle/running/waiting_review/succeeded/failed。现：新增 pausing 和 paused 状态展示。

## Performance Requirements
### Requirement: SSE Token 流批量持久化
将 complaint.token 从逐 token 持久化改为批量持久化（每 500ms 或 50 token）。
### Requirement: LangGraph Checkpoint 节流
配置 checkpoint 写入节流，避免每次回调都触发 DB 写入。
### Requirement: 事件回放分批处理
restoreWorkflow 对大量历史事件分批应用，避免阻塞 UI。
