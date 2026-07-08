# Tasks

## 阶段 A：最小可行泛化（无 migration）

- [x] Task A1: 扩展 OCR 证据分类到 10 类
  - [x] A1.1: 修改 `backend/api/agents/prompts/templates.py` 的 PRECLASSIFY_PROMPT，新增 service_contract/work_record/communication_record/contract_document/medical_record 5 类
  - [x] A1.2: 更新 `backend/api/models.py` 的 Evidence.evidence_category help_text
  - [x] A1.3: 更新前端 `frontend/src/pages/EvidencePage.tsx` 显示新分类标签
  - [x] A1.4: 补充下游 3 处白名单（preclassify_node/classify_node/schemas.py）

- [x] Task A2: 扩展 calculate_compensation 工具到 10 种违规类型
  - [x] A2.1: 在 `backend/api/agents/tools/law_tools.py` 的 `_calculate_compensation_impl` 新增 6 种违规类型：service_breach/false_advertising/personal_info_leak/contract_breach/tort/price_fraud
  - [x] A2.2: 为每种新违规类型实现赔偿计算逻辑（含法律依据引用）
  - [x] A2.3: 更新 docstring + Django check + 工具调用测试通过

- [x] Task A3: Prompt 模板去电商化
  - [x] A3.1: 在 `templates.py` 新增 SCENARIO_DESCRIPTIONS 字典（按 case_type 映射场景描述）
  - [x] A3.2: 修改 EVIDENCE_CHAIN_PROMPT 和 COMPLAINT_REWRITE_PROMPT，使用 {scenario_description} 动态注入
  - [x] A3.3: 修改 evidence_chain_node 和 complaint_node 传入 scenario_description 参数
  - [x] A3.4: 验证现有电商场景输出不退化（Django check + 工作流编译通过）

- [x] Task A4: 扩展 case_similarity 工具的场景维度
  - [x] A4.1: 在 case_similarity 工具新增 `scenario` 参数（service/medical/labor）
  - [x] A4.2: 实现场景关键词匹配逻辑
  - [x] A4.3: Django check 通过 + 工具调用测试通过

## 阶段 B：完整泛化（含 migration）

- [x] Task B1: 数据库模型扩展
  - [x] B1.1: Case 模型新增 `case_mode` 字段（complain/respond，默认 complain）
  - [x] B1.2: PlatformRule 模型新增 `rule_type` 字段（platform/regulatory/industry）
  - [x] B1.3: PlatformRule.platform choices 扩展（新增 meituan/eleme/ctrip/keelage/classin/labor_arbitration/court_small/medical_dispute）
  - [x] B1.4: 新增 RespondTemplate 模型（与 ComplaintTemplate 结构相同，type=respond）
  - [x] B1.5: 生成 migration（0010_case_case_mode_platformrule_rule_type_and_more）
  - [x] B1.6: 更新 Django admin 注册 RespondTemplate

- [~] Task B2: 新增 10 部法律知识库（抓取+解析完成，导入待 MySQL 启动）
  - [x] B2.1: 联网抓取 10 部法律官方原文（服务4部完整+医疗1部完整+2部部分+劳动3部完整）
  - [x] B2.2: 扩展 `parse_law_data.py` 的 FILE_CATEGORY_MAP + LAW_KEYWORDS_MAP
  - [x] B2.3: 扩展 LawArticle.CATEGORY_CHOICES 新增 service/medical/labor 分类
  - [x] B2.4: 运行解析脚本生成新 JSON（2260条，含新增614条）
  - [ ] B2.5: 运行 `import_law_articles --file=...` 导入新法条到 MySQL（需 MySQL 启动）
  - [ ] B2.6: 运行 `--force-embed` 为新法条生成 embedding 向量索引（需 MySQL + PG 启动）
  - [ ] B2.7: 每部抽检 3 条与官方原文逐字校验

- [x] Task B3: 反向维权流程实现
  - [x] B3.1: 创建 `backend/api/agents/nodes/respond_complaint_node.py`
  - [x] B3.2: 实现 respond_complaint_node 逻辑：复用 evidence_chain + 生成反证答辩书
  - [x] B3.3: 在 templates.py 新增 RESPOND_COMPLAINT_PROMPT
  - [x] B3.4: 在 graph.py 新增条件分支 + state.py 新增 case_mode 字段
  - [x] B3.5: complaint_node 与 respond_complaint_node 通过 add_conditional_edges 路由
  - [x] B3.6: respond_complaint_node 绑定 7 个法律工具 + 主动预检索

- [x] Task B4: 法律工具扩展适配
  - [x] B4.1: `lookup_law` 工具的 category 参数新增 service/medical/labor 选项
  - [x] B4.2: `lookup_platform_rule` 工具支持新平台代码（meituan/eleme/ctrip 等）
  - [x] B4.3: `calculate_compensation` 新增 wage_arrears（拖欠工资）违规类型
  - [x] B4.4: `jurisdiction_determine` 工具扩展医疗/劳动渠道
  - [x] B4.5: Django check + 工具调用测试通过

- [x] Task B5: 前端 UI 支持
  - [x] B5.1: CaseListPage 新增案件模式选择（维权投诉/商家反证）
  - [x] B5.2: EvidencePage 显示新证据分类标签（A1.3 已完成）
  - [x] B5.3: 新增 RespondPage.tsx 反证书展示页
  - [x] B5.4: 更新路由配置 + AppLayout 侧边栏动态切换
  - [x] B5.5: 后端 CaseSerializer 新增 case_mode 字段

- [x] Task B6: 阶段 B 集成测试
  - [x] B6.1: Django check 无错误
  - [x] B6.2: 工作流编译验证（complain + respond 两种模式节点齐全）
  - [x] B6.3: 7 个法律工具 + 11 种违规类型全部可调用
  - [ ] B6.4: 端到端测试（需 MySQL + PG 启动后执行）

# Task Dependencies

- Task A2 依赖 Task A1（赔偿计算需要新分类）
- Task A3 依赖 Task A1（Prompt 需要新分类）
- Task A5 依赖 Task A1-A4
- Task B1 独立（数据库改动）
- Task B2 独立（法律数据抓取，可并行）
- Task B3 依赖 Task B1（需要 case_mode 字段）
- Task B4 依赖 Task B1, B2（需要新法律分类）
- Task B5 依赖 Task B1, B3
- Task B6 依赖 Task B1-B5

# Parallelizable Work

- Task A1, A2, A3, A4 可并行（同阶段独立改动）
- Task B1, B2 可并行（数据库 vs 法律数据）
- Task B3, B4 可部分并行（B4 工具扩展不依赖 B3 节点实现）
