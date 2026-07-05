# -*- coding: utf-8 -*-
"""LangExtract 维权场景少样本示例与配置读取。

通过高质量示例约束 langextract 输出：
- extraction_class：字段名（订单号/金额/手机号/地址/时间/承诺话术/邮箱/物流单号/退款金额/商家名称）
- extraction_text：字段值的原文片段（必须 verbatim 出现在 text 中）
- attributes：额外信息（confidence, normalized_value）

底层模型：Qwen3 系列（通过 OpenAI 兼容接口调用，配置见 .env 的 LANGEXTRACT_*）
官方文档：https://github.com/google/langextract

注意：
- 每个 extraction_text 必须与示例 text 中的字符串完全一致（verbatim）
- 示例按字段出现顺序排列
- 涵盖 3 类典型证据：商品订单、聊天截图、物流跟踪
"""
import os


# ============================================================
# LangExtract 配置读取（全部从 .env 读取，运行时生效）
# ============================================================

def get_api_key() -> str:
    """获取 LangExtract 调用的 API Key。"""
    return os.environ.get("LANGEXTRACT_API_KEY", "").strip()


def get_base_url() -> str:
    """获取 OpenAI 兼容接口地址。"""
    return os.environ.get("LANGEXTRACT_BASE_URL", "").strip()


def get_provider() -> str:
    """获取 LangExtract 内部 provider 路由（OpenAI 兼容接口固定为 openai）。"""
    return (os.environ.get("LANGEXTRACT_PROVIDER", "") or "openai").strip()


def get_model_id() -> str:
    """获取 langextract 使用的模型 ID（Qwen3 系列）。"""
    return os.environ.get("LANGEXTRACT_MODEL", "").strip() or "Qwen/Qwen3-32B"


def get_extraction_passes() -> int:
    """获取提取轮数（提高召回率）。"""
    try:
        return int(os.environ.get("LANGEXTRACT_PASSES", "1") or "1")
    except ValueError:
        return 1


# LangExtract 提取任务的 prompt 描述（可从 .env 的 LANGEXTRACT_PROMPT 覆盖）
# 按官方推荐格式：明确字段类别 + verbatim 要求 + 属性要求
_DEFAULT_PROMPT_DESCRIPTION = (
    "从维权证据文本中提取关键字段，用于消费者维权投诉场景。\n"
    "字段类别（extraction_class）包括：\n"
    "  - 订单号：电商平台订单编号（如 2025061012345678）\n"
    "  - 金额：实付金额、商品价格、退款金额等（保留数字和单位，如 699元）\n"
    "  - 手机号：买家、商家、物流的联系电话（11 位数字）\n"
    "  - 地址：收货地址、寄件地址等完整地址\n"
    "  - 时间：下单时间、发货时间、物流时间、聊天时间等（保留原始格式）\n"
    "  - 承诺话术：商家对发货/退款/售后的承诺原文\n"
    "  - 邮箱：电子邮箱地址\n"
    "  - 物流单号：快递运单号（如 SF1234567890123）\n"
    "  - 退款金额：单独的退款数额（保留数字和单位）\n"
    "  - 商家名称：店铺/商家的名称\n"
    "要求：\n"
    "1. 每个 extraction_text 必须与原文完全一致（verbatim），不要改写或推断\n"
    "2. 按字段在文本中的出现顺序输出\n"
    "3. 金额字段保留数字和单位（如 699元），时间字段保留原始格式\n"
    "4. 为每个字段提供 attributes：\n"
    "   - confidence（0-1，抽取置信度）\n"
    "   - normalized_value（归一化值，如金额归一为数字字符串 699，时间归一为 ISO 8601）"
)


def get_prompt_description() -> str:
    """获取 LangExtract 提取任务的 prompt 描述。

    优先级：.env 中 LANGEXTRACT_PROMPT > 内置默认 _DEFAULT_PROMPT_DESCRIPTION
    """
    custom = os.environ.get('LANGEXTRACT_PROMPT', '').strip()
    return custom or _DEFAULT_PROMPT_DESCRIPTION


# 向后兼容：模块级常量（动态读取 .env）
# 注意：此常量在模块加载时求值，运行时修改 .env 不会更新
# 推荐使用 get_prompt_description() 函数
PROMPT_DESCRIPTION = get_prompt_description()


def is_langextract_available() -> bool:
    """检查 langextract 是否可用（依赖已安装且 API Key 已配置）。"""
    try:
        import langextract  # noqa: F401
    except ImportError:
        return False
    return bool(get_api_key())


# ============================================================
# 少样本示例（按官方 ExampleData 格式，覆盖 3 类典型证据）
# ============================================================

def _build_examples():
    """构造维权场景的少样本示例列表。

    Returns:
        list[lx.data.ExampleData]
    """
    try:
        import langextract as lx
    except ImportError:
        return []

    examples = []

    # ===== 示例 1：商品订单截图 =====
    examples.append(lx.data.ExampleData(
        text=(
            "订单详情\n"
            "订单号：2025061012345678\n"
            "下单时间：2025-06-10 09:20:15\n"
            "商家名称：数码专营店\n"
            "实付金额：699元\n"
            "收货地址：北京市朝阳区建国路88号\n"
            "联系电话：13812345678"
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="订单号",
                extraction_text="2025061012345678",
                attributes={"confidence": 0.95, "normalized_value": "2025061012345678"},
            ),
            lx.data.Extraction(
                extraction_class="时间",
                extraction_text="2025-06-10 09:20:15",
                attributes={"confidence": 0.9, "normalized_value": "2025-06-10T09:20:15"},
            ),
            lx.data.Extraction(
                extraction_class="商家名称",
                extraction_text="数码专营店",
                attributes={"confidence": 0.9},
            ),
            lx.data.Extraction(
                extraction_class="金额",
                extraction_text="699元",
                attributes={"confidence": 0.95, "normalized_value": "699"},
            ),
            lx.data.Extraction(
                extraction_class="地址",
                extraction_text="北京市朝阳区建国路88号",
                attributes={"confidence": 0.85},
            ),
            lx.data.Extraction(
                extraction_class="手机号",
                extraction_text="13812345678",
                attributes={"confidence": 0.95},
            ),
        ],
    ))

    # ===== 示例 2：聊天截图（含商家承诺）=====
    examples.append(lx.data.ExampleData(
        text=(
            "客服小美 09:45\n"
            "亲，48小时内发货哦\n"
            "买家 09:46\n"
            "好的，那我等发货通知\n"
            "客服小美 09:47\n"
            "嗯嗯，有问题随时联系：13987654321"
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="承诺话术",
                extraction_text="48小时内发货",
                attributes={"confidence": 0.9},
            ),
            lx.data.Extraction(
                extraction_class="时间",
                extraction_text="09:45",
                attributes={"confidence": 0.7, "normalized_value": "2025-06-10T09:45"},
            ),
            lx.data.Extraction(
                extraction_class="时间",
                extraction_text="09:46",
                attributes={"confidence": 0.7, "normalized_value": "2025-06-10T09:46"},
            ),
            lx.data.Extraction(
                extraction_class="手机号",
                extraction_text="13987654321",
                attributes={"confidence": 0.95},
            ),
        ],
    ))

    # ===== 示例 3：物流跟踪 =====
    examples.append(lx.data.ExampleData(
        text=(
            "物流详情\n"
            "物流单号：SF1234567890123\n"
            "2025-06-11 14:30  已揽收\n"
            "2025-06-12 08:15  到达北京分拣中心\n"
            "2025-06-12 15:20  派送中，请联系：13700001234\n"
            "收件地址：北京市海淀区中关村大街1号"
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="物流单号",
                extraction_text="SF1234567890123",
                attributes={"confidence": 0.95},
            ),
            lx.data.Extraction(
                extraction_class="时间",
                extraction_text="2025-06-11 14:30",
                attributes={"confidence": 0.9, "normalized_value": "2025-06-11T14:30"},
            ),
            lx.data.Extraction(
                extraction_class="时间",
                extraction_text="2025-06-12 08:15",
                attributes={"confidence": 0.9, "normalized_value": "2025-06-12T08:15"},
            ),
            lx.data.Extraction(
                extraction_class="手机号",
                extraction_text="13700001234",
                attributes={"confidence": 0.95},
            ),
            lx.data.Extraction(
                extraction_class="地址",
                extraction_text="北京市海淀区中关村大街1号",
                attributes={"confidence": 0.85},
            ),
        ],
    ))

    return examples


def get_examples():
    """获取维权场景少样本示例（懒加载，避免 import 失败时整个模块崩溃）。"""
    return _build_examples()
