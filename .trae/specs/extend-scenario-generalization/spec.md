# 场景泛化扩展 Spec

## Why

当前 ClaimCraft 维权材料工坊的实现严重局限于电商交易场景：OCR 证据分类仅 5 类电商专用、赔偿计算仅支持 4 种违规类型、PlatformRule 表仅支持 8 个电商平台、工作流仅支持"用户投诉"单向方向。

依据设计文档 `claimcraft-creative.html` 的完整愿景，产品应覆盖三类用户场景：普通消费者（网购/服务违约/医疗纠纷）、服务类用户（家装/维修/课程）、小微商家反证材料。本次泛化将场景从单一电商扩展到 **电商 + 服务违约 + 医疗纠纷 + 劳动争议** 四类，并新增反向维权（商家反证）流程。

## What Changes

### 阶段 A：最小可行泛化（无 migration）

- 扩展 OCR 证据分类从 5 类到 10 类（新增服务合同/施工记录/沟通记录/合同文件/医疗记录）
- 扩展 `calculate_compensation` 工具从 4 种到 10 种违规类型（新增服务违约/虚假宣传/个人信息泄露/合同违约/侵权责任/价格欺诈）
- Prompt 模板去电商化：根据 `case_type` 动态选择场景描述
- `case_similarity` 工具新增场景维度检索

### 阶段 B：完整泛化（含 migration）

- **BREAKING** Case 模型新增 `case_mode` 字段（complain/respond，默认 complain）
- PlatformRule 表新增 `rule_type` 字段（platform/regulatory/industry），扩展 `platform` choices 支持服务/医疗/劳动渠道
- 新增 10 部法律知识库（服务 4 部 + 医疗 3 部 + 劳动 3 部），全量条款入库 + embedding
- 新增 `respond_complaint_node` 节点 + `RespondTemplate` 模型，支持反向维权流程
- 工作流图新增条件分支：`case_mode=respond` 时走 `respond_complaint_node`
- 新增 `respond_complaint` 投诉模板类型

## Impact

- **Affected specs**: v9-workflow-optimization, v10-rag-tools-design
- **Affected code**:
  - `backend/api/models.py` — Case/PlatformRule 模型扩展，新增 RespondTemplate
  - `backend/api/agents/tools/law_tools.py` — calculate_compensation/case_similarity 扩展
  - `backend/api/agents/prompts/templates.py` — PRECLASSIFY_PROMPT/COMPLAINT_REWRITE_PROMPT 泛化
  - `backend/api/agents/nodes/respond_complaint_node.py` — 新增节点
  - `backend/api/agents/graph.py` — 工作流新增条件分支
  - `backend/api/services/law_data_raw/` — 新增 10 部法律原文
  - `backend/api/management/commands/import_law_articles.py` — 支持新法律分类
  - `frontend/src/pages/EvidencePage.tsx` — 显示新证据分类
  - `frontend/src/pages/CaseCreatePage.tsx` — 支持选择 case_mode

## ADDED Requirements

### Requirement: 多场景证据分类

系统 SHALL 支持以下 10 类证据分类（含场景标签）：

| 分类代码 | 名称 | 适用场景 |
|---------|------|---------|
| chat_screenshot | 聊天截图 | 电商/服务 |
| product_order | 商品订单 | 电商 |
| logistics_tracking | 物流跟踪 | 电商 |
| payment_record | 支付凭证 | 全场景 |
| invoice | 发票 | 全场景 |
| service_contract | 服务合同/协议 | 服务/医疗 |
| work_record | 施工/服务记录 | 服务/医疗 |
| communication_record | 沟通记录(邮件/电话) | 全场景 |
| contract_document | 合同文件 | 全场景 |
| medical_record | 医疗记录 | 医疗 |
| other | 其他 | 全场景 |

#### Scenario: 服务场景证据分类
- **WHEN** 用户上传家装合同照片
- **THEN** preclassify_node 识别为 `service_contract` 类别
- **AND** 生成对应摘要含合同金额、工期、违约条款

### Requirement: 多类型赔偿计算

系统 SHALL 支持以下 10 种违规类型的法定赔偿计算：

| 违规类型 | 法律依据 | 赔偿标准 |
|---------|---------|---------|
| fraud | 消保法第55条 | 退一赔三，最低500元 |
| food_safety | 食安法第148条 | 十倍赔偿，最低1000元 |
| late_delivery | 民法典577条 | 违约责任，按合同约定 |
| quality_issue | 产品质量法40条 | 三包责任 |
| service_breach | 民法典577条 | 服务违约，继续履行/赔偿损失 |
| false_advertising | 广告法第56条 | 虚假宣传，民事赔偿+行政处罚 |
| personal_info_leak | 个保法第69条 | 损害赔偿，推定过错 |
| contract_breach | 民法典577条 | 一般合同违约 |
| tort | 民法典1165条 | 侵权责任，按实际损失 |
| price_fraud | 价格法第40条 | 责令改正，没收违法所得 |

#### Scenario: 服务违约赔偿计算
- **WHEN** 调用 `calculate_compensation(violation_type="service_breach", amount=5000)`
- **THEN** 返回赔偿建议：继续履行 + 赔偿损失（含直接损失和可得利益损失）
- **AND** 引用民法典第577条作为法律依据

### Requirement: 反向维权流程

系统 SHALL 支持反向维权（商家反证）流程，与现有投诉流程并行：

#### Scenario: 商家反证流程
- **WHEN** 用户创建案件时选择 `case_mode=respond`
- **THEN** 工作流执行 preclassify → ocr → classify → extract → evidence_chain → respond_complaint
- **AND** 生成"商家反证答辩书"而非"投诉书"
- **AND** 反证书包含：事实澄清、证据反驳、法律依据、诉求说明

### Requirement: 10 部新法律知识库

系统 SHALL 新增以下 10 部法律到 LawArticle 表（全量条款 + embedding）：

**服务场景（4 部）**：
1. 中华人民共和国消费者权益保护法实施条例（2024年7月1日施行）
2. 家政服务管理办法
3. 互联网广告管理办法（2023年5月1日施行）
4. 明码标价和禁止价格欺诈规定（2022年7月1日施行）

**医疗场景（3 部）**：
5. 医疗纠纷预防和处理条例
6. 医疗事故处理条例
7. 中华人民共和国基本医疗卫生与健康促进法

**劳动场景（3 部）**：
8. 中华人民共和国劳动法
9. 中华人民共和国劳动合同法
10. 中华人民共和国劳动争议调解仲裁法

#### Scenario: 劳动争议法律检索
- **WHEN** 用户描述"工资拖欠"案件
- **THEN** RAG 检索返回劳动合同法第30条（工资支付）、劳动法第91条（拖欠工资法律责任）
- **AND** 赔偿计算工具支持 `violation_type="wage_arrears"`（违法拖欠工资）

### Requirement: PlatformRule 表扩展

系统 SHALL 扩展 PlatformRule 表支持多类处理规则：

- 新增 `rule_type` 字段：platform（平台）/ regulatory（监管）/ industry（行业）
- 扩展 `platform` choices：新增 meituan/eleme/ctrip/keelage/classin（服务类平台）+ labor_arbitration/court_small/medical_dispute（处理渠道）
- 现有 3 条电商数据保留为 `rule_type=platform`

### Requirement: 场景化 Prompt 模板

系统 SHALL 根据 `case_type` 和 `case_mode` 动态选择 prompt 场景描述：

- 保留现有 prompt 模板结构
- 新增 `SCENARIO_DESCRIPTIONS` 字典按 case_type 映射场景描述
- 投诉重写 prompt 支持反证模式（case_mode=respond）

## MODIFIED Requirements

### Requirement: Case 模型

Case 模型新增 `case_mode` 字段：

```python
CASE_MODE_CHOICES = [
    ('complain', '维权投诉'),
    ('respond', '商家反证'),
]
case_mode = models.CharField(
    '案件模式', max_length=20, choices=CASE_MODE_CHOICES,
    default='complain'
)
```

### Requirement: 工作流图

工作流图新增条件分支：

```
evidence_chain → [case_mode=complain] → complaint → END
evidence_chain → [case_mode=respond] → respond_complaint → END
```

## REMOVED Requirements

无（所有改造均为新增或扩展，保持向后兼容）。
