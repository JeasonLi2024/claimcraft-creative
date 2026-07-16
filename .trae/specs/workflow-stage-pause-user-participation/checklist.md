# Checklist

## 后端数据库迁移
- [ ] makemigrations 生成包含 workflow_pause_requested / workflow_paused_after / workflow_status(pausing/paused) 的迁移文件
- [ ] migrate 成功应用迁移
- [ ] 现有 Case 记录默认值正确（idle, False, ''）

## 后端 LangGraph 阶段门
- [ ] stage_gate_node.py 存在且实现 pause_requested 检查逻辑
- [ ] graph.py 在每个业务节点后插入 stage_gate 条件边
- [ ] stage_gate 调用 interrupt() 时 payload 含 interrupt_type=stage_pause 和正确的 paused_after
- [ ] stage_gate 不干扰现有 low_confidence 审核 interrupt
- [ ] compile 配置正确支持新的 interrupt 点

## 后端 WorkflowRunner
- [ ] Runner 能检测 stage_pause 类型中断并调用 mark_paused
- [ ] Runner 通过 EventDepot 发送 workflow.paused 事件
- [ ] Runner resume 路径区分 paused vs waiting_review
- [ ] paused 恢复时使用 build_stage_resume_payload 构建 Command(resume=...)
- [ ] paused 恢复后调用 clear_pause_boundary
- [ ] Runner 通过 EventDepot 发送 workflow.resumed 事件
- [ ] 同一 case 并发 runner 安全（不会重复启动）

## 后端 API
- [ ] POST /api/cases/<id>/workflow/cancel/ 仅接受 paused/idle 状态
- [ ] cancel API 正确将状态置为 idle 并清除暂停标记
- [ ] GET /api/cases/<id>/workflow/state/ 返回完整状态信息
- [ ] state API 返回的 editable_scope 与 STAGE_EDITABLE_SCOPES 一致
- [ ] state API 返回的 stage_products 包含当前阶段的实际数据
- [ ] urls.py 注册了 cancel 和 state 两条路由

## 后端 SSE 事件
- [ ] EventType 含 workflow.cancelled
- [ ] sse-client.ts EVENT_TYPES 含 workflow.cancelled
- [ ] case-store.ts applySSEEvent 处理 workflow.cancelled
- [ ] 取消/失败路径发送 workflow.cancelled 事件

## 前端 StagePausePanel
- [ ] StagePausePanel.tsx 非空文件，导出默认组件
- [ ] 展示暂停阶段名称和说明
- [ ] 根据 editable_scope 动态渲染对应表单字段
- [ ] 表单预填充当前产物数据
- [ ] 继续工作流按钮调用 resumePausedWorkflow 并传递 edits
- [ ] 取消工作流按钮调用 cancelWorkflow
- [ ] 加载态和错误态 UI 反馈
- [ ] npm run build 无编译错误

## 前端 Store 与 API
- [ ] case-store.ts 有 cancelWorkflow action
- [ ] case-store.ts 有 fetchWorkflowState action
- [ ] case-store.ts applySSEEvent 处理 workflow.cancelled
- [ ] api.ts 有 cancelWorkflow 方法
- [ ] api.ts 有 getWorkflowState 方法

## 前端 WorkflowStreamPanel
- [ ] running 状态显示暂停按钮
- [ ] pausing 状态显示等待提示
- [ ] paused 状态隐藏暂停按钮
- [ ] 页面刷新 paused 状态自动恢复编辑面板
- [ ] NodeTrack 高亮暂停节点

## 性能优化
- [ ] complaint.token 事件改为批量持久化（阈值可配）
- [ ] LangGraph checkpoint 写入频率降低（如有配置项）
- [ ] restoreWorkflow 对大量事件分批处理

## 验证
- [ ] py_compile 所有 .py 文件无语法错误
- [ ] django check --deploy 无警告或错误
- [ ] makemigrations/migrate 成功
- [ ] npm run build 无错误
- [ ] 冒烟测试路径 1-5 全部通过
- [ ] git diff --check 无 whitespace 错误
