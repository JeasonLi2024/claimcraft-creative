# -*- coding: utf-8 -*-
"""LLM prompt 模板常量。

集中管理 4 套 prompt：OCR 纠错 / 字段抽取 / 事件分类 / 投诉重写。
使用 .format() 占位符，调用方传入 {variable_name}。
"""

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

# ===== 投诉重写 prompt =====
COMPLAINT_REWRITE_PROMPT = """你是投诉材料撰写助手。基于以下骨架和事实，重写一份语气{tone}、
逻辑清晰的投诉正文。保留骨架中的关键信息（订单号、金额、时间），
增强事实陈述和诉求论证，不要添加未提供的事实。

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

仅输出重写后的投诉正文（不要标题，不要解释）："""


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


# ===== 证据链构造 prompt（新增）=====
EVIDENCE_CHAIN_PROMPT = """你是维权证据链构造助手。基于以下多份证据的 OCR 文本和抽取字段，构造完整的证据时间链。

案件描述：{case_description}

证据列表（含分类和字段）：
{evidences_json}

构造要求：
1. 按时间顺序排列所有事件
2. 每个事件关联对应的证据编号（evidence_codes）
3. 事件类别从以下选择：下单/付款/发货/沟通/退款/承诺/违约/其他
4. 推断缺失时间时在 summary 中说明
5. chain_order 从 0 开始递增

请输出符合 JSON Schema 的结构化证据链。"""
