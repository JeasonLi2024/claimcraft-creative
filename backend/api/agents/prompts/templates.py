# -*- coding: utf-8 -*-
"""LLM prompt 模板常量。

集中管理 4 套 prompt：OCR 纠错 / 字段抽取 / 事件分类 / 投诉重写。
使用 .format() 占位符，调用方传入 {variable_name}。
"""

# 场景描述字典（按 case_type 映射场景描述，用于 prompt 动态注入）
SCENARIO_DESCRIPTIONS = {
    "shopping": "网购交易纠纷场景（商品质量/虚假宣传/物流问题/退换货等）",
    "service": "服务违约场景（家装/维修/培训/家政等服务未按约定履行）",
    "secondhand": "二手交易纠纷场景（二手商品质量/描述不符/退款等）",
    "other": "一般维权场景（合同纠纷/侵权责任/价格欺诈等）",
}

# ===== OCR 后纠错 prompt =====
OCR_CORRECTION_PROMPT = """你是 OCR 后纠错助手。以下是 OCR 识别结果，可能存在错字（如"兀"→"元"、"0"→"O"、"巳"→"已"）。
请基于案件上下文修正明显错误，保持原始结构（换行/标点），不要增删信息。

案件描述：{case_description}

OCR 原文：
{raw_text}

仅输出修正后的纯文本，不要任何解释："""

# ===== 字段抽取 prompt（JSON Mode）=====
EXTRACT_FIELDS_PROMPT = """你是维权证据字段抽取助手。从以下 OCR 文本中抽取结构化字段。

OCR 文本：
{text}

案件类型：{case_type}

抽取规则：
1. 同一字段可有多值（如多个手机号）
2. 金额归一为数字字符串（如 "699 元" → "699"）
3. 时间归一为 ISO 8601 格式（如 "2025-06-10 09:20"）
4. OCR 错字需推断原值（如 "699 兀" → "699 元"）
5. confidence 取值 0.0-1.0，模糊推断 ≤ 0.6，明确匹配 ≥ 0.85

请输出符合 JSON Schema 的 JSON。"""

# 字段抽取 JSON Schema
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "字段名：订单号/金额/手机号/地址/时间/承诺话术/邮箱/银行卡/车牌/商品名/物流单号/退款金额/商家名称"
                    },
                    "field_value": {"type": "string"},
                    "confidence": {"type": "number"}
                },
                "required": ["field_name", "field_value", "confidence"]
            }
        }
    },
    "required": ["fields"]
}

# ===== 时间线事件分类 prompt =====
TIMELINE_CLASSIFY_PROMPT = """你是事件分类助手。将以下事件归入最匹配的类别。

事件文本：{event}

可选类别（仅输出其中一个）：
- 下单：购买行为、订单创建
- 付款：支付、转账、退款到账
- 发货：物流、揽收、配送
- 沟通：客服对话、咨询、协商
- 退款：退款申请、退款成功
- 承诺：商家承诺发货/退款/赔偿
- 违约：超时未发货、虚假发货、拒绝退款
- 其他：无法归入以上类别

仅输出类别名称（一个词），不要其他文本："""

# ===== 投诉重写 prompt（v10 增强版：预检索法条 + 工具调用）=====
COMPLAINT_REWRITE_PROMPT = """你是投诉材料撰写助手。基于以下骨架和事实，重写一份语气{tone}、
逻辑清晰的投诉正文。保留骨架中的关键信息（订单号、金额、时间），
增强事实陈述和诉求论证，不要添加未提供的事实。
当前案件场景：{scenario_description}

语气要求：
- restrained：克制、客观、陈述事实
- firm：坚定、有理有据、明确诉求
- legal：法律化、引用条款

骨架（Jinja2 渲染后）：
{skeleton}

事实字段（JSON）：
{facts_json}

时间线事件（JSON）：
{timeline_json}

{law_articles_section}

{tools_section}

写作要求：
1. 仅输出重写后的投诉正文（不要标题，不要解释）
2. 引用法律条文时必须使用工具查询，不得编造法条
3. 涉及赔偿金额时必须使用 calculate_compensation 工具计算，确保金额准确
4. 引用法条前必须调用 validate_legal_citation 工具验证法条真实性
5. 引用法条格式：根据《法律名称》第X条规定，...
6. 若工具查询结果为空，不得引用具体法条，仅做事实陈述"""


# ===== Tools 启用时的 prompt 片段（v10 新增，7 个工具）=====
TOOLS_ENABLED_SECTION = """可用工具（7 个，按需调用提升专业性）：
- lookup_law(keyword, category)：查询法律条文（RAG 向量语义检索）
- lookup_precedent(scenario)：查询类似维权判例
- lookup_platform_rule(platform, issue)：查询电商平台投诉规则
- calculate_compensation(violation_type, amount)：计算法定赔偿金额
- validate_legal_citation(law_name, article_number)：校验法条引用是否真实存在（防幻觉）
- jurisdiction_determine(case_type, amount, issue_description)：确定管辖法院/投诉受理部门
- case_similarity(case_description, case_type, scenario, top_k)：检索相似历史案件，scenario 可按场景过滤（service/medical/labor/其他）

调用建议：
- 涉及欺诈/食品安全/质量问题→必查 calculate_compensation
- 需要法律依据支撑→查 lookup_law
- 引用法条前→必查 validate_legal_citation 验证真实性
- 需要参考类似案例→查 lookup_precedent 或 case_similarity
- 涉及平台投诉→查 lookup_platform_rule
- 需要建议投诉渠道→查 jurisdiction_determine"""


TOOLS_DISABLED_SECTION = "（工具集未启用，仅基于已有事实重写，不引用具体法条）"""


# ===== 证据分类 prompt（新增）=====
EVIDENCE_CLASSIFY_PROMPT = """你是维权证据材料分类助手。请根据以下 OCR 识别文本，判断该证据属于哪种类型。

证据编号：{evidence_code}
OCR 文本：
{ocr_text}

可选类别：
- chat_screenshot（聊天截图）：即时通讯对话、客服沟通记录
- product_order（商品订单）：订单详情页、商品购买页、订单确认
- logistics_tracking（物流跟踪）：物流信息、快递追踪、配送状态
- payment_record（支付凭证）：付款截图、转账记录、支付成功页
- other（其他）：无法归入以上类别

请输出符合 JSON Schema 的结构化分类结果。"""


# ===== 证据链构造 prompt（v10 增强版：注入 RAG 检索的法条 + 工具调用）=====
EVIDENCE_CHAIN_PROMPT = """你是维权证据链构造助手。基于以下多份证据的 OCR 摘要和抽取字段，构造完整的证据时间链。
当前案件场景：{scenario_description}

案件描述：{case_description}

证据列表（含分类和字段）：
{evidences_json}

{law_articles_section}

{tools_section}

构造要求：
1. 按时间顺序排列所有事件
2. 每个事件关联对应的证据编号（evidence_codes）
3. 事件类别从以下选择：下单/付款/发货/沟通/退款/承诺/违约/其他
4. 推断缺失时间时在 summary 中说明
5. chain_order 从 0 开始递增
6. 若事件涉嫌违法，在 summary 中引用相关法律条文（法条名+条文编号）
7. 违约事件需说明违反的具体法律依据

工具调用要求（重要）：
- 若需查询更多法条支撑证据链，调用 lookup_law 工具
- 若需验证某法条是否真实存在，调用 validate_legal_citation 工具
- 若需参考类似案例，调用 lookup_precedent 工具
- 若涉及赔偿计算，调用 calculate_compensation 工具
- 若需确定管辖法院，调用 jurisdiction_determine 工具

输出格式（JSON）：
{{
  "nodes": [
    {{
      "datetime": "ISO8601时间或空字符串",
      "event": "事件描述",
      "category": "下单/付款/发货/沟通/退款/承诺/违约/其他",
      "evidence_codes": ["E1", "E2"],
      "chain_order": 0,
      "summary": "事件摘要，含法律依据引用"
    }}
  ]
}}

仅输出 JSON，不要其他文本。"""


# ===== 法条注入 prompt 片段（v10 新增）=====
LAW_ARTICLES_SECTION_TEMPLATE = """相关法律条文（RAG 检索结果，供引用）：
{law_articles_json}

法律引用要求：
- 仅引用上述检索到的法条，不得编造法条
- 引用格式：根据《{law_name}》{article_number}规定，...
- 若事件涉及欺诈/食品安全/质量问题，必须引用对应法条"""


LAW_ARTICLES_EMPTY_SECTION = "（RAG 未检索到相关法条，可按常识构造证据链，但不引用具体法律条文）"


# ===== 投诉重写法条注入片段（v10 新增）=====
COMPLAINT_LAW_ARTICLES_SECTION_TEMPLATE = """相关法律条文（RAG 检索结果，供引用）：
{law_articles_json}

法律引用要求：
- 仅引用上述检索到的法条，不得编造法条
- 引用前必须使用 validate_legal_citation 工具验证法条真实性
- 引用格式：根据《{law_name}》{article_number}规定，...
- 若涉及欺诈/食品安全/质量问题，必须引用对应法条"""


COMPLAINT_LAW_ARTICLES_EMPTY_SECTION = "（RAG 未检索到相关法条，可按事实陈述，但不引用具体法律条文）"


# ===== 按证据类型区分的 OCR 识别 prompt（v9 新增）=====
OCR_PROMPT_BY_CATEGORY = {
    "chat_screenshot": (
        "请识别这张聊天截图中的所有对话内容，按「发言人 时间\\n内容」格式逐条输出，"
        "保留原始换行和标点。仅输出识别到的文字，不要解释。"
    ),
    "product_order": (
        "请识别这张订单详情截图，按表格结构输出 Markdown，包含：订单号/下单时间/"
        "商家名称/商品名称/数量/单价/实付金额/收货地址/联系电话。仅输出识别到的文字，不要解释。"
    ),
    "logistics_tracking": (
        "请识别这张物流跟踪截图，按时间顺序逐条输出物流轨迹，格式：时间 状态 详情。"
        "包含物流单号和联系电话。仅输出识别到的文字，不要解释。"
    ),
    "payment_record": (
        "请识别这张支付凭证截图，输出 Markdown 表格，包含：交易流水号/支付方式/"
        "付款时间/付款金额/收款方/备注。仅输出识别到的文字，不要解释。"
    ),
    "invoice": (
        "请识别这张发票图片，按结构化 Markdown 输出，包含：发票代码/发票号码/"
        "开票日期/购买方/销售方/货物或应税劳务名称/金额/税率/税额/"
        "价税合计(大写)/价税合计(小写)。仅输出识别到的文字，不要解释。"
    ),
}


# ===== 视觉预分类+摘要 prompt（v9 新增）=====
PRECLASSIFY_PROMPT = """请分析这张维权证据图片，输出 JSON：
{
  "evidence_category": "chat_screenshot|product_order|logistics_tracking|payment_record|invoice|service_contract|work_record|communication_record|contract_document|medical_record|other",
  "summary": "100-200字的图片内容摘要，包含关键信息（人物/时间/金额/事件）",
  "confidence": 0.0-1.0
}

分类说明：
- chat_screenshot：聊天截图（电商/服务通用，即时通讯对话、客服沟通记录）
- product_order：商品订单（电商，订单详情页、商品购买页）
- logistics_tracking：物流跟踪（电商，物流信息、快递追踪）
- payment_record：支付凭证（全场景，付款截图、转账记录、支付成功页）
- invoice：发票（全场景，增值税普通/专用发票、电子发票）
- service_contract：服务合同/协议（服务/医疗场景，如家装合同、维修协议、培训合同）
- work_record：施工/服务记录（服务/医疗场景，如施工现场照片、维修记录、诊疗记录）
- communication_record：沟通记录（全场景，如邮件截图、电话录音转文字、微信沟通）
- contract_document：合同文件（全场景，如纸质合同扫描、电子合同截图）
- medical_record：医疗记录（医疗场景，如病历、检查报告、医疗费用清单）
- other：无法归入以上类别

仅输出 JSON，不要其他内容。"""


# ===== 反证答辩书 prompt（v10 新增 - 反向维权）=====
RESPOND_COMPLAINT_PROMPT = """你是商家反证答辩书撰写助手。基于以下骨架和事实，撰写一份语气{tone}、
逻辑清晰的反证答辩书。作为商家回应消费者投诉，澄清事实、反驳不实指控。

当前案件场景：{scenario_description}

语气要求：
- restrained：客观陈述事实
- firm：坚定反驳不实指控
- legal：法律化答辩

答辩书骨架（Jinja2 渲染后）：
{skeleton}

事实字段（JSON）：
{facts_json}

时间线事件（JSON）：
{timeline_json}

{law_articles_section}

{tools_section}

写作要求：
1. 仅输出答辩书正文
2. 引用法律条文时必须使用工具查询，不得编造法条
3. 引用法条前必须调用 validate_legal_citation 工具验证真实性
4. 答辩书结构：事实澄清 → 证据反驳 → 法律依据 → 诉求说明
5. 针对消费者每项指控逐一回应
6. 若工具查询结果为空，仅做事实陈述，不引用具体法条"""
