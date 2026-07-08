# -*- coding: utf-8 -*-
"""v10 法律工具集（7 个 LangChain @tool）。

供 evidence_chain_node 和 complaint_node 使用，让 LLM 主动调用查询法律条款。

工具列表：
1. lookup_law：按关键词检索法律条文（RAG 向量检索）
2. lookup_precedent：查询类似维权判例（关键词匹配）
3. lookup_platform_rule：查询电商平台投诉规则
4. calculate_compensation：计算法定赔偿金额（退一赔三/十倍赔偿等）
5. validate_legal_citation：校验法条引用是否真实存在（防幻觉）
6. jurisdiction_determine：确定管辖法院/投诉受理部门
7. case_similarity：相似案件检索（基于历史案件库）

设计要点：
- 全部为 async 工具（与 async 节点配合）
- 工具失败时返回错误信息（不抛异常，让 LLM 能继续处理）
- 返回 JSON 字符串（LLM 友好格式）
"""
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def is_tools_enabled() -> bool:
    """Tools 工具集是否启用。"""
    return os.environ.get('TOOLS_ENABLED', 'true').lower() == 'true'


def _get_max_iterations() -> int:
    """单次投诉生成最大工具调用轮数。"""
    return int(os.environ.get('TOOLS_MAX_ITERATIONS', '5'))


# ============================================================
# 工具 1：查询法律条文（RAG 向量检索）
# ============================================================

async def _lookup_law_impl(keyword: str, category: str = "") -> str:
    """查询法律条文的实现。

    Args:
        keyword: 查询关键词（如 "欺诈", "退一赔三", "延迟发货"）
        category: 法律分类（可选，consumer_protection/e-commerce/contract/quality/safety/privacy）

    Returns:
        JSON 字符串，含相关法条列表
    """
    from api.services.rag_service import LawRetriever

    retriever = LawRetriever()
    results = await retriever.retrieve(keyword, category=category, top_k=5)

    if not results:
        return json.dumps({
            "status": "no_results",
            "message": f"未找到与 '{keyword}' 相关的法律条文",
            "keyword": keyword,
            "category": category or "all"
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "keyword": keyword,
        "category": category or "all",
        "count": len(results),
        "law_articles": [
            {
                "law_name": r['law_name'],
                "article_number": r['article_number'],
                "summary": r['summary'],
                "content": r['content'],
                "keywords": r.get('keywords', []),
                "applicable_scenarios": r.get('applicable_scenarios', []),
                "score": round(r['score'], 3)
            }
            for r in results
        ]
    }, ensure_ascii=False, indent=2)


def make_lookup_law_tool():
    """构造 lookup_law 工具（LangChain @tool 装饰）。

    使用函数构造而非装饰器，避免在模块加载时就依赖 LangChain 工具系统。
    """
    from langchain_core.tools import tool

    @tool
    async def lookup_law(keyword: str, category: str = "") -> str:
        """查询法律条文。按关键词检索相关法条（RAG 向量语义检索）。

        当需要引用具体法律条款支撑投诉理由时调用此工具。
        检索范围：消费者权益保护法、电子商务法、民法典合同编、食品安全法、产品质量法。

        Args:
            keyword: 查询关键词或问题描述（如 "欺诈行为", "延迟发货", "食品安全问题"）
            category: 法律分类过滤（可选）：
                - consumer_protection: 消费者权益保护法
                - e-commerce: 电子商务法
                - contract: 民法典合同编
                - quality: 产品质量法
                - safety: 食品安全法
                - privacy: 个人信息保护法
                - service: 服务违约相关法律（消保法实施条例、家政服务管理办法等）
                - medical: 医疗纠纷相关法律（医疗纠纷预防处理条例、医疗事故处理条例等）
                - labor: 劳动争议相关法律（劳动法、劳动合同法等）
                留空=检索全部法律

        Returns:
            JSON 字符串，含相关法条列表（含条文原文、摘要、关键词、相似度评分）
        """
        try:
            return await _lookup_law_impl(keyword, category)
        except Exception as e:
            logger.error(f"lookup_law 工具调用失败: {e}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"法律条文查询失败: {e}",
                "keyword": keyword
            }, ensure_ascii=False)

    return lookup_law


# ============================================================
# 工具 2：查询维权判例（关键词匹配）
# ============================================================

async def _lookup_precedent_impl(scenario: str) -> str:
    """查询类似维权判例的实现。

    当前版本：从内置判例库按关键词匹配（后续可扩展为向量检索）。
    """
    from api.services.law_precedents import get_precedents_by_scenario
    precedents = get_precedents_by_scenario(scenario)

    if not precedents:
        return json.dumps({
            "status": "no_results",
            "message": f"未找到与 '{scenario}' 类似的维权判例",
            "scenario": scenario
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "scenario": scenario,
        "count": len(precedents),
        "precedents": precedents
    }, ensure_ascii=False, indent=2)


def make_lookup_precedent_tool():
    """构造 lookup_precedent 工具。"""
    from langchain_core.tools import tool

    @tool
    async def lookup_precedent(scenario: str) -> str:
        """查询类似维权判例。按场景描述检索相似案例。

        当需要参考类似案例的处理方式和赔偿结果时调用此工具。

        Args:
            scenario: 维权场景描述（如 "商家虚假宣传导致退款", "食品过期索赔十倍"）

        Returns:
            JSON 字符串，含类似判例列表（含案件类型、适用法律、赔偿方式、金额）
        """
        try:
            return await _lookup_precedent_impl(scenario)
        except Exception as e:
            logger.error(f"lookup_precedent 工具调用失败: {e}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"判例查询失败: {e}",
                "scenario": scenario
            }, ensure_ascii=False)

    return lookup_precedent


# ============================================================
# 工具 3：查询平台投诉规则
# ============================================================

async def _lookup_platform_rule_impl(platform: str, issue: str) -> str:
    """查询平台规则的实现。"""
    from api.models import PlatformRule
    from asgiref.sync import sync_to_async

    rules = await sync_to_async(list)(
        PlatformRule.objects.filter(
            platform=platform,
            is_active=True,
        ).filter(
            # 匹配 issue_type 或在 content 中包含 issue 关键词
            issue_type=issue
        )[:5]
    )

    # 如果精确匹配不到，尝试在 content 中模糊匹配
    if not rules:
        rules = await sync_to_async(list)(
            PlatformRule.objects.filter(
                platform=platform,
                is_active=True,
                content__icontains=issue,
            )[:5]
        )

    if not rules:
        # 再尝试 other 平台作为通用规则
        rules = await sync_to_async(list)(
            PlatformRule.objects.filter(
                platform='other',
                is_active=True,
            )[:3]
        )

    if not rules:
        return json.dumps({
            "status": "no_results",
            "message": f"未找到平台 {platform} 关于 {issue} 的规则",
            "platform": platform,
            "issue": issue
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "platform": platform,
        "issue": issue,
        "count": len(rules),
        "rules": [r.to_retrieval_dict() for r in rules]
    }, ensure_ascii=False, indent=2)


def make_lookup_platform_rule_tool():
    """构造 lookup_platform_rule 工具。"""
    from langchain_core.tools import tool

    @tool
    async def lookup_platform_rule(platform: str, issue: str) -> str:
        """查询电商平台投诉规则。获取平台官方处理流程和赔偿标准。

        当需要了解某平台对特定问题的处理规则时调用此工具。

        Args:
            platform: 平台名称（taobao/tmall/jd/pdd/douyin/kuaishou/vipshop/suning/meituan/eleme/ctrip/labor_arbitration/medical_dispute/other）
                - meituan: 美团（外卖/本地服务）
                - eleme: 饿了么
                - ctrip: 携程（旅游服务）
                - labor_arbitration: 劳动仲裁委
                - medical_dispute: 医疗纠纷调解
            issue: 投诉问题（如 late_delivery/counterfeit/quality_issue/refund_dispute）
                或问题描述关键词（如 "延迟发货", "假货", "质量问题"）

        Returns:
            JSON 字符串，含平台规则列表（含赔偿标准、处理流程、规则原文）
        """
        try:
            return await _lookup_platform_rule_impl(platform, issue)
        except Exception as e:
            logger.error(f"lookup_platform_rule 工具调用失败: {e}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"平台规则查询失败: {e}",
                "platform": platform,
                "issue": issue
            }, ensure_ascii=False)

    return lookup_platform_rule


# ============================================================
# 工具 4：计算法定赔偿金额
# ============================================================

async def _calculate_compensation_impl(violation_type: str, amount: float) -> str:
    """计算法定赔偿金额的实现。

    依据真实法律条文计算：
    - fraud（欺诈）：退一赔三，最低 500 元（消保法第55条）
    - food_safety（食品安全）：十倍赔偿，最低 1000 元（食安法第148条）
    - late_delivery（延迟发货）：合同违约，赔偿实际损失（民法典第577条）
    - quality_issue（质量问题）：三包责任，修理/更换/退货（产品质量法第40条）
    - service_breach（服务违约）：继续履行 + 赔偿损失（含可得利益，民法典第577条）
    - false_advertising（虚假宣传）：退一赔三，最低 500 元（广告法第56条 + 消保法第55条）
    - personal_info_leak（个人信息泄露）：按实际损失，最低 1000 元（个保法第69条）
    - contract_breach（一般合同违约）：赔偿损失 + 违约金（民法典第577条）
    - tort（侵权责任）：按实际损失赔偿（民法典第1165条）
    - price_fraud（价格欺诈）：退一赔三，最低 500 元（价格法第40条 + 禁止价格欺诈规定）
    """
    violation_type = violation_type.lower().strip()
    calculations = []

    if violation_type == 'fraud':
        # 消保法第55条：退一赔三，最低500元
        compensation = amount * 3
        if compensation < 500:
            compensation = 500
        calculations.append({
            "law_name": "中华人民共和国消费者权益保护法",
            "article_number": "第五十五条",
            "violation": "欺诈行为",
            "compensation_type": "退一赔三（三倍赔偿）",
            "principal_amount": amount,
            "compensation_amount": round(compensation, 2),
            "total_refund": round(amount + compensation, 2),
            "note": "增加赔偿为价款三倍，不足500元按500元计",
            "legal_basis": "经营者提供商品或者服务有欺诈行为的，应当按照消费者的要求增加赔偿其受到的损失，增加赔偿的金额为消费者购买商品的价款或者接受服务的费用的三倍；增加赔偿的金额不足五百元的，为五百元。"
        })

    elif violation_type == 'food_safety':
        # 食安法第148条：十倍赔偿，最低1000元
        compensation = amount * 10
        if compensation < 1000:
            compensation = 1000
        calculations.append({
            "law_name": "中华人民共和国食品安全法",
            "article_number": "第一百四十八条",
            "violation": "不符合食品安全标准",
            "compensation_type": "十倍赔偿",
            "principal_amount": amount,
            "compensation_amount": round(compensation, 2),
            "total_refund": round(amount + compensation, 2),
            "note": "支付价款十倍赔偿，不足1000元按1000元计",
            "legal_basis": "生产不符合食品安全标准的食品或者经营明知是不符合食品安全标准的食品，消费者除要求赔偿损失外，还可以向生产者或者经营者要求支付价款十倍或者损失三倍的赔偿金；增加赔偿的金额不足一千元的，为一千元。"
        })

    elif violation_type == 'late_delivery':
        # 民法典第577条：违约责任，赔偿实际损失
        calculations.append({
            "law_name": "中华人民共和国民法典",
            "article_number": "第五百七十七条",
            "violation": "延迟发货（违约）",
            "compensation_type": "赔偿实际损失",
            "principal_amount": amount,
            "compensation_amount": "需根据实际损失计算",
            "total_refund": "可要求退还货款 + 实际损失赔偿",
            "note": "违约责任：继续履行/补救措施/赔偿损失。损失含可得利益（民法典第584条）",
            "legal_basis": "当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。"
        })

    elif violation_type == 'quality_issue':
        # 产品质量法第40条：三包责任
        calculations.append({
            "law_name": "中华人民共和国产品质量法",
            "article_number": "第四十条",
            "violation": "产品质量问题",
            "compensation_type": "三包（修理/更换/退货）+ 赔偿损失",
            "principal_amount": amount,
            "compensation_amount": "三包费用由销售者承担",
            "total_refund": "可要求退货退款 + 损失赔偿",
            "note": "销售者应负责修理、更换、退货；造成损失的应赔偿",
            "legal_basis": "售出的产品有下列情形之一的，销售者应当负责修理、更换、退货；给购买产品的消费者造成损失的，销售者应当赔偿损失。"
        })

    elif violation_type == 'service_breach':
        # 民法典第577条：服务违约，继续履行 + 赔偿损失（含可得利益损失）
        direct_loss = amount
        indirect_loss = min(amount * 0.2, 5000)
        compensation = direct_loss + indirect_loss
        calculations.append({
            "violation_type": "service_breach",
            "amount": amount,
            "compensation": round(compensation, 2),
            "compensation_description": f"继续履行服务 + 赔偿损失（直接损失 {direct_loss} 元 + 可得利益损失估算 {round(indirect_loss, 2)} 元，上限 5000 元）",
            "legal_basis": [
                {
                    "law_name": "中华人民共和国民法典",
                    "article_number": "第五百七十七条",
                    "content": "当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。"
                }
            ],
            "recommendations": [
                "要求继续履行服务",
                "解除合同并退款",
                "赔偿损失（含直接损失和可得利益损失）"
            ],
            # 兼容 summary 字段
            "law_name": "中华人民共和国民法典",
            "article_number": "第五百七十七条",
            "compensation_amount": round(compensation, 2)
        })

    elif violation_type == 'false_advertising':
        # 广告法第56条 + 消保法第55条：虚假宣传，退一赔三
        compensation = max(amount * 3, 500)
        calculations.append({
            "violation_type": "false_advertising",
            "amount": amount,
            "compensation": round(compensation, 2),
            "compensation_description": f"构成欺诈则退一赔三（最低 500 元），赔偿金额 {round(compensation, 2)} 元",
            "legal_basis": [
                {
                    "law_name": "中华人民共和国广告法",
                    "article_number": "第五十六条",
                    "content": "违反本法规定，发布虚假广告，欺骗和误导消费者，使购买商品或者接受服务的消费者的合法权益受到损害的，由广告主依法承担民事责任。"
                },
                {
                    "law_name": "中华人民共和国消费者权益保护法",
                    "article_number": "第五十五条",
                    "content": "经营者提供商品或者服务有欺诈行为的，应当按照消费者的要求增加赔偿其受到的损失，增加赔偿的金额为消费者购买商品的价款或者接受服务的费用的三倍；增加赔偿的金额不足五百元的，为五百元。"
                }
            ],
            "recommendations": [
                "要求赔偿（退一赔三）",
                "向市场监督管理部门举报虚假广告行为"
            ],
            "law_name": "中华人民共和国广告法",
            "article_number": "第五十六条",
            "compensation_amount": round(compensation, 2)
        })

    elif violation_type == 'personal_info_leak':
        # 个人信息保护法第69条：损害赔偿推定过错，最低 1000 元
        compensation = max(amount, 1000)
        calculations.append({
            "violation_type": "personal_info_leak",
            "amount": amount,
            "compensation": round(compensation, 2),
            "compensation_description": f"按实际损失赔偿，无法确定时最低 1000 元，赔偿金额 {round(compensation, 2)} 元",
            "legal_basis": [
                {
                    "law_name": "中华人民共和国个人信息保护法",
                    "article_number": "第六十九条",
                    "content": "处理个人信息侵害他人民事权益造成损害，个人信息处理者不能证明自己没有过错的，应当承担损害赔偿等侵权责任。"
                }
            ],
            "recommendations": [
                "要求赔偿损失",
                "要求停止侵害、删除已泄露的个人信息",
                "向网信部门举报"
            ],
            "law_name": "中华人民共和国个人信息保护法",
            "article_number": "第六十九条",
            "compensation_amount": round(compensation, 2)
        })

    elif violation_type == 'contract_breach':
        # 民法典第577条：一般合同违约，赔偿损失 + 违约金
        liquidated_damages = min(amount * 0.1, 1000)
        compensation = amount + liquidated_damages
        calculations.append({
            "violation_type": "contract_breach",
            "amount": amount,
            "compensation": round(compensation, 2),
            "compensation_description": f"继续履行 + 赔偿损失 {amount} 元 + 违约金估算 {round(liquidated_damages, 2)} 元（上限 1000 元）",
            "legal_basis": [
                {
                    "law_name": "中华人民共和国民法典",
                    "article_number": "第五百七十七条",
                    "content": "当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。"
                }
            ],
            "recommendations": [
                "要求继续履行合同",
                "支付违约金",
                "赔偿损失"
            ],
            "law_name": "中华人民共和国民法典",
            "article_number": "第五百七十七条",
            "compensation_amount": round(compensation, 2)
        })

    elif violation_type == 'tort':
        # 民法典第1165条：过错侵权责任，按实际损失赔偿
        compensation = amount
        calculations.append({
            "violation_type": "tort",
            "amount": amount,
            "compensation": round(compensation, 2),
            "compensation_description": f"按实际损失赔偿（医疗费/护理费/误工费等），赔偿金额 {round(compensation, 2)} 元",
            "legal_basis": [
                {
                    "law_name": "中华人民共和国民法典",
                    "article_number": "第一千一百六十五条",
                    "content": "行为人因过错侵害他人民事权益造成损害的，应当承担侵权责任。"
                }
            ],
            "recommendations": [
                "要求赔偿医疗费、护理费、误工费等实际损失",
                "保留追诉权利"
            ],
            "law_name": "中华人民共和国民法典",
            "article_number": "第一千一百六十五条",
            "compensation_amount": round(compensation, 2)
        })

    elif violation_type == 'price_fraud':
        # 价格法第40条 + 禁止价格欺诈规定：退一赔三，最低 500 元
        compensation = max(amount * 3, 500)
        calculations.append({
            "violation_type": "price_fraud",
            "amount": amount,
            "compensation": round(compensation, 2),
            "compensation_description": f"退一赔三（最低 500 元），赔偿金额 {round(compensation, 2)} 元",
            "legal_basis": [
                {
                    "law_name": "中华人民共和国价格法",
                    "article_number": "第四十条",
                    "content": "经营者有本法第十四条所列行为之一的，责令改正，没收违法所得，可以并处违法所得五倍以下的罚款；没有违法所得的，予以警告，可以并处罚款。"
                },
                {
                    "law_name": "明码标价和禁止价格欺诈规定",
                    "article_number": "第十九条",
                    "content": "经营者不得实施下列价格欺诈行为：（一）谎称商品和服务价格为政府定价或者政府指导价；（二）以低价诱骗消费者或者经营者，以高价进行结算。"
                }
            ],
            "recommendations": [
                "要求退还多收价款",
                "向市场监督管理部门举报价格欺诈行为"
            ],
            "law_name": "中华人民共和国价格法",
            "article_number": "第四十条",
            "compensation_amount": round(compensation, 2)
        })

    elif violation_type == "wage_arrears":
        # 拖欠工资
        compensation = amount * 1.5  # 加付50%赔偿金
        calculations.append({
            "compensation_type": "wage_arrears",
            "principal_amount": amount,
            "additional_compensation": amount * 0.5,
            "total_compensation": compensation,
            "compensation_amount": compensation,
            "note": f"拖欠工资 {amount} 元，依据劳动合同法第85条，加付50%赔偿金",
            "legal_basis": "劳动合同法第85条",
            "law_name": "中华人民共和国劳动合同法",
            "article_number": "第八十五条",
            "recommendations": [
                "向劳动行政部门投诉",
                "申请劳动仲裁",
                "要求支付拖欠工资+50%加付赔偿金"
            ],
        })

    else:
        return json.dumps({
            "status": "unknown_violation",
            "message": f"未知的违法类型: {violation_type}",
            "supported_types": [
                "fraud", "food_safety", "late_delivery", "quality_issue",
                "service_breach", "false_advertising", "personal_info_leak",
                "contract_breach", "tort", "price_fraud", "wage_arrears"
            ]
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "violation_type": violation_type,
        "principal_amount": amount,
        "calculations": calculations,
        "summary": f"基于 {calculations[0]['law_name']} {calculations[0]['article_number']}，"
                   f"赔偿金额: {calculations[0]['compensation_amount']}"
    }, ensure_ascii=False, indent=2)


def make_calculate_compensation_tool():
    """构造 calculate_compensation 工具。"""
    from langchain_core.tools import tool

    @tool
    async def calculate_compensation(violation_type: str, amount: float) -> str:
        """计算法定赔偿金额。基于真实法律条文计算赔偿数额。

        当需要计算具体赔偿金额或引用赔偿法律依据时调用此工具。

        Args:
            violation_type: 违法类型：
                - fraud: 欺诈行为（退一赔三，最低500元，依据消保法第55条）
                - food_safety: 食品安全问题（十倍赔偿，最低1000元，依据食安法第148条）
                - late_delivery: 延迟发货（违约责任，依据民法典第577条）
                - quality_issue: 质量问题（三包责任，依据产品质量法第40条）
                - service_breach: 服务违约（继续履行+赔偿损失，依据民法典第577条）
                - false_advertising: 虚假宣传（退一赔三，最低500元，依据广告法第56条+消保法第55条）
                - personal_info_leak: 个人信息泄露（最低1000元，依据个保法第69条）
                - contract_breach: 一般合同违约（赔偿损失+违约金，依据民法典第577条）
                - tort: 侵权责任（按实际损失赔偿，依据民法典第1165条）
                - price_fraud: 价格欺诈（退一赔三，最低500元，依据价格法第40条+禁止价格欺诈规定）
                - wage_arrears: 拖欠工资（加付50%-100%赔偿金，依据劳动合同法第85条）
            amount: 实付金额（元，正数）

        Returns:
            JSON 字符串，含赔偿计算结果和法律依据
        """
        try:
            if amount < 0:
                return json.dumps({
                    "status": "error",
                    "message": "金额不能为负数",
                    "violation_type": violation_type,
                    "amount": amount
                }, ensure_ascii=False)
            return await _calculate_compensation_impl(violation_type, amount)
        except Exception as e:
            logger.error(f"calculate_compensation 工具调用失败: {e}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"赔偿计算失败: {e}",
                "violation_type": violation_type,
                "amount": amount
            }, ensure_ascii=False)

    return calculate_compensation


# ============================================================
# 工具集工厂：一次性获取全部工具
# ============================================================

def get_all_law_tools() -> list:
    """获取全部法律工具（用于 evidence_chain_node 和 complaint_node 绑定）。

    Returns:
        list: 7 个 LangChain tool 实例
    """
    return [
        make_lookup_law_tool(),
        make_lookup_precedent_tool(),
        make_lookup_platform_rule_tool(),
        make_calculate_compensation_tool(),
        make_validate_legal_citation_tool(),
        make_jurisdiction_determine_tool(),
        make_case_similarity_tool(),
    ]


# ============================================================
# 工具 5：校验法条引用是否真实存在（防幻觉）
# ============================================================

async def _validate_legal_citation_impl(law_name: str, article_number: str) -> str:
    """校验法条引用是否真实存在。

    通过 MySQL LawArticle 表查询法条是否存在，防止 LLM 编造法条。
    """
    from api.models import LawArticle
    from asgiref.sync import sync_to_async
    from django.db.models import Q

    # 模糊匹配（支持简写如"消保法"/"消费者权益保护法"）
    query = Q(law_name__icontains=law_name) | Q(law_name__icontains=law_name.replace("中华人民共和国", ""))
    articles = await sync_to_async(list)(
        LawArticle.objects.filter(query).filter(article_number=article_number)[:1]
    )

    if not articles:
        # 尝试不包含"第"和"条"的编号
        clean_num = article_number.replace("第", "").replace("条", "")
        articles = await sync_to_async(list)(
            LawArticle.objects.filter(query).filter(
                article_number__icontains=clean_num
            )[:3]
        )

    if not articles:
        return json.dumps({
            "status": "not_found",
            "message": f"未找到法律 '{law_name}' {article_number}，请勿引用此法条",
            "law_name": law_name,
            "article_number": article_number,
            "suggestion": "请使用 lookup_law 工具查询真实存在的法条"
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "law_name": articles[0].law_name,
        "article_number": articles[0].article_number,
        "chapter": articles[0].chapter,
        "content": articles[0].content,
        "summary": articles[0].summary,
        "is_active": articles[0].is_active,
        "message": "法条存在且有效" if articles[0].is_active else "法条存在但已失效"
    }, ensure_ascii=False, indent=2)


def make_validate_legal_citation_tool():
    """构造 validate_legal_citation 工具。"""
    from langchain_core.tools import tool

    @tool
    async def validate_legal_citation(law_name: str, article_number: str) -> str:
        """校验法条引用是否真实存在。防止引用不存在的法条（法律幻觉）。

        当需要在投诉中引用某条法律时，调用此工具验证法条是否真实存在。
        如果法条不存在，工具会返回 not_found，请改用 lookup_law 查询真实法条。

        Args:
            law_name: 法律名称（如 "消费者权益保护法"、"民法典"、"食品安全法"）
            article_number: 条文编号（如 "第五十五条"、"第一百四十八条"）

        Returns:
            JSON 字符串，含法条是否存在、原文内容、是否现行有效
        """
        try:
            return await _validate_legal_citation_impl(law_name, article_number)
        except Exception as e:
            logger.error(f"validate_legal_citation 工具调用失败: {e}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"法条校验失败: {e}",
                "law_name": law_name,
                "article_number": article_number
            }, ensure_ascii=False)

    return validate_legal_citation


# ============================================================
# 工具 6：确定管辖法院/投诉受理部门
# ============================================================

async def _jurisdiction_determine_impl(
    case_type: str, amount: float, issue_description: str = ""
) -> str:
    """根据案件金额和类型确定管辖法院/投诉受理部门。

    依据《民事诉讼法》和《消费者权益保护法》相关规定：
    - 金额 ≤ 1万：基层人民法院简易程序 / 平台投诉
    - 1万 < 金额 ≤ 10万：基层人民法院普通程序
    - 10万 < 金额 ≤ 100万：中级人民法院
    - 金额 > 100万：高级人民法院
    - 涉及食品/药品安全：可优先向市场监督管理局投诉
    """
    amount = float(amount) if amount else 0
    issue_desc = issue_description or ""

    # 推荐投诉渠道
    channels = []

    # 渠道1：平台投诉（所有案件首选）
    channels.append({
        "channel": "电商平台投诉",
        "priority": 1,
        "description": "通过平台客服/纠纷处理通道投诉（最快，1-7天处理）",
        "applicable": "所有电商交易纠纷首选"
    })

    # 渠道2：12315 投诉
    channels.append({
        "channel": "12315消费者投诉热线",
        "priority": 2,
        "description": "全国12315平台（www.12315.cn）或拨打12315电话",
        "applicable": "平台处理不满意或商家拒绝配合时"
    })

    # 渠道3：市场监督管理局
    if any(kw in issue_desc for kw in ["食品", "药品", "化妆品", "医疗器械"]):
        channels.append({
            "channel": "市场监督管理局",
            "priority": 2,
            "description": "涉及食品/药品安全问题，向当地市场监督管理局投诉",
            "applicable": "食品/药品/化妆品安全问题"
        })

    # 渠道3-医疗：医疗纠纷场景
    if any(kw in issue_desc for kw in ["医疗", "诊疗", "病历"]):
        channels.append({
            "channel": "医疗纠纷人民调解委员会",
            "priority": 2,
            "description": "医患纠纷第三方调解，免费、便捷（1-3个月）",
            "applicable": "医疗纠纷、医患矛盾"
        })
        channels.append({
            "channel": "卫生健康委员会",
            "priority": 3,
            "description": "向医院所属地卫健委投诉，行政调查",
            "applicable": "医院/诊所违规行为、医生执业问题"
        })
        channels.append({
            "channel": "医学会医疗事故技术鉴定",
            "priority": 3,
            "description": "申请医疗事故技术鉴定，作为诉讼证据",
            "applicable": "医疗事故、伤残/死亡后果"
        })

    # 渠道3-劳动：劳动争议场景
    if any(kw in issue_desc for kw in ["工资", "劳动合同", "工伤"]):
        channels.append({
            "channel": "劳动监察大队",
            "priority": 2,
            "description": "向用人单位所在地劳动监察大队投诉（行政途径，最快）",
            "applicable": "拖欠工资、未签劳动合同、违法用工"
        })
        channels.append({
            "channel": "劳动人事争议仲裁委员会",
            "priority": 3,
            "description": "申请劳动仲裁（前置程序，仲裁裁决后再起诉）",
            "applicable": "工资/经济补偿/劳动合同/工伤争议"
        })
        channels.append({
            "channel": "法院劳动争议审判庭",
            "priority": 4,
            "description": "对仲裁裁决不服，向法院提起诉讼",
            "applicable": "对仲裁裁决不服，或仲裁不予受理"
        })

    # 渠道4：法院诉讼（按金额分级）
    if amount <= 10000:
        court_level = "基层人民法院（简易程序）"
        procedure = "小额诉讼程序（一审终审，最快1-3个月）"
        cost = f"诉讼费约 {max(25, int(amount * 0.025))} 元"
    elif amount <= 100000:
        court_level = "基层人民法院（普通程序）"
        procedure = "简易程序或普通程序（3-6个月）"
        cost = f"诉讼费约 {int(amount * 0.025)} 元"
    elif amount <= 1000000:
        court_level = "中级人民法院"
        procedure = "普通程序（6-12个月）"
        cost = f"诉讼费约 {int(amount * 0.015)} 元"
    else:
        court_level = "高级人民法院"
        procedure = "普通程序（12个月以上）"
        cost = f"诉讼费约 {int(amount * 0.01)} 元"

    channels.append({
        "channel": court_level,
        "priority": 3,
        "description": f"向被告住所地或合同履行地法院提起诉讼",
        "procedure": procedure,
        "cost": cost,
        "applicable": f"金额 > {amount} 元，其他渠道无法解决时"
    })

    # 管辖法院确定依据
    legal_basis = {
        "law_name": "中华人民共和国民事诉讼法",
        "article_number": "第二十三条",
        "content": "因合同纠纷提起的诉讼，由被告住所地或者合同履行地人民法院管辖。",
        "note": "网络购物合同履行地通常为收货地"
    }

    return json.dumps({
        "status": "ok",
        "case_type": case_type,
        "amount": amount,
        "recommended_channels": channels,
        "legal_basis": legal_basis,
        "summary": f"案件金额 {amount} 元，推荐依次尝试：{' → '.join(c['channel'] for c in channels)}"
    }, ensure_ascii=False, indent=2)


def make_jurisdiction_determine_tool():
    """构造 jurisdiction_determine 工具。"""
    from langchain_core.tools import tool

    @tool
    async def jurisdiction_determine(
        case_type: str, amount: float, issue_description: str = ""
    ) -> str:
        """确定管辖法院和投诉受理部门。根据案件金额和类型推荐投诉渠道。

        当需要建议用户向哪个部门投诉或在投诉中说明管辖依据时调用此工具。

        Args:
            case_type: 案件类型（shopping/service/secondhand/other）
            amount: 涉案金额（元，正数）
            issue_description: 问题描述（可选，用于判断是否涉及食品/药品安全等专项）

        Returns:
            JSON 字符串，含推荐投诉渠道列表（按优先级排序）和法律依据
        """
        try:
            if amount < 0:
                return json.dumps({
                    "status": "error",
                    "message": "金额不能为负数"
                }, ensure_ascii=False)
            return await _jurisdiction_determine_impl(case_type, amount, issue_description)
        except Exception as e:
            logger.error(f"jurisdiction_determine 工具调用失败: {e}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"管辖确定失败: {e}",
                "case_type": case_type,
                "amount": amount
            }, ensure_ascii=False)

    return jurisdiction_determine


# ============================================================
# 工具 7：相似案件检索（基于历史案件库）
# ============================================================

async def _case_similarity_impl(
    case_description: str, case_type: str = "", scenario: str = "", top_k: int = 5
) -> str:
    """基于历史案件库检索相似案件。

    从 MySQL Case 表查询同类型已结案案件，按金额和关键词相似度排序。
    支持 scenario 场景维度过滤：service/medical/labor。
    """
    from api.models import Case
    from asgiref.sync import sync_to_async
    from django.db.models import Q

    # 场景关键词映射
    scenario_keywords_map = {
        "service": ["服务", "家装", "维修", "培训", "家政", "违约"],
        "medical": ["医疗", "诊疗", "病历", "医疗事故", "医患"],
        "labor": ["劳动", "工资", "劳动合同", "工伤", "社保"],
    }

    # 查询同类型已结案案件（closed 状态）
    query = Q(status='closed') | Q(status='submitted')
    if case_type:
        query &= Q(case_type=case_type)

    # 关键词匹配
    keywords = [kw.strip() for kw in case_description.split() if len(kw.strip()) > 1][:5]
    if keywords:
        keyword_query = Q()
        for kw in keywords:
            keyword_query |= Q(description__icontains=kw) | Q(title__icontains=kw)
        query &= keyword_query

    # 场景关键词匹配：scenario 非空时，将 scenario 关键词加入 keyword_query 匹配
    scenario = (scenario or "").strip().lower()
    scenario_kws = scenario_keywords_map.get(scenario, [])
    if scenario_kws:
        scenario_query = Q()
        for kw in scenario_kws:
            scenario_query |= Q(description__icontains=kw) | Q(title__icontains=kw)
        query &= scenario_query

    cases = await sync_to_async(list)(
        Case.objects.filter(query).order_by('-created_at')[:top_k]
    )

    if not cases:
        # 降级：仅按类型查询
        if case_type:
            cases = await sync_to_async(list)(
                Case.objects.filter(
                    case_type=case_type, status='closed'
                ).order_by('-created_at')[:top_k]
            )

    if not cases:
        return json.dumps({
            "status": "no_results",
            "message": "未找到相似的历史案件",
            "case_description": case_description,
            "case_type": case_type or "all"
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "case_description": case_description,
        "case_type": case_type or "all",
        "count": len(cases),
        "similar_cases": [
            {
                "case_id": c.id,
                "title": c.title,
                "case_type": c.case_type,
                "description": (c.description or "")[:200],
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }
            for c in cases
        ]
    }, ensure_ascii=False, indent=2)


def make_case_similarity_tool():
    """构造 case_similarity 工具。"""
    from langchain_core.tools import tool

    @tool
    async def case_similarity(
        case_description: str, case_type: str = "", scenario: str = "", top_k: int = 5
    ) -> str:
        """检索相似的历史案件。从已结案案件中查找相似案例。

        当需要参考类似案件的处理方式或预测可能的判决结果时调用此工具。
        scenario: 场景类型（可选：service=服务违约/medical=医疗纠纷/labor=劳动争议，空=不过滤）

        Args:
            case_description: 当前案件描述（用于关键词匹配）
            case_type: 案件类型（可选：shopping/service/secondhand/other）
            scenario: 场景类型（可选：service=服务违约/medical=医疗纠纷/labor=劳动争议，空=不过滤）
            top_k: 返回最多相似案件数（默认5，最大10）

        Returns:
            JSON 字符串，含相似案件列表（含标题、描述、状态）
        """
        try:
            top_k = min(max(int(top_k), 1), 10)  # 限制 1-10
            return await _case_similarity_impl(case_description, case_type, scenario, top_k)
        except Exception as e:
            logger.error(f"case_similarity 工具调用失败: {e}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"相似案件检索失败: {e}",
                "case_description": case_description
            }, ensure_ascii=False)

    return case_similarity


# ============================================================
# 通用工具调用辅助函数（供 evidence_chain_node 和 complaint_node 共用）
# ============================================================

async def pre_retrieve_law_articles(case_keywords: list[str], top_k: int = 5) -> list[dict]:
    """节点入口主动预检索法律条文（强制首次调用，失败降级）。

    混合模式策略：
    - 首次强制尝试 RAG 检索
    - 失败或返回空 → 降级返回空列表（节点继续执行，LLM 按常识生成）

    Args:
        case_keywords: 案件关键词列表
        top_k: 返回最多法条数

    Returns:
        法条字典列表（空列表表示降级）
    """
    if not case_keywords:
        return []

    try:
        from api.services.rag_service import LawRetriever, is_rag_enabled
        if not is_rag_enabled():
            return []

        retriever = LawRetriever()
        query = " ".join(case_keywords)
        results = await retriever.retrieve(query, top_k=top_k)
        return results or []
    except Exception as e:
        logger.warning(f"预检索法条失败（降级为空列表）: {e}")
        return []


async def invoke_llm_with_tools(
    prompt: str,
    tools: list,
    max_iterations: int = 5,
    errors: list = None,
    node_name: str = "node"
) -> tuple[str, list[dict]]:
    """通用 LLM 工具调用循环（多轮 tool calling）。

    流程：
    1. 绑定 Tools 到 LLM
    2. 发送 prompt，LLM 返回 content + tool_calls
    3. 并行执行 tool_calls
    4. 将 tool_results 追加到消息历史，再次调用 LLM
    5. 循环直到 LLM 不再调用工具或达到最大轮数
    6. 返回最终 content 和工具调用记录

    Args:
        prompt: 初始 prompt
        tools: LangChain tool 实例列表
        max_iterations: 最大工具调用轮数
        errors: 错误累积列表（可选）
        node_name: 节点名称（用于日志）

    Returns:
        (最终 content, 工具调用记录列表)
    """
    import asyncio
    from api.services import llm_service
    from langchain_core.messages import HumanMessage, ToolMessage

    if errors is None:
        errors = []

    if not tools:
        # 无工具可绑定，直接调用 LLM
        try:
            response = await llm_service.get_scenario_llm("text").ainvoke(
                [HumanMessage(content=prompt)]
            )
            return (response.content if hasattr(response, 'content') else str(response), [])
        except Exception as e:
            errors.append(f"[{node_name}] LLM 调用失败: {e}")
            return ("", [])

    llm = llm_service.get_scenario_llm("text")
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    messages = [HumanMessage(content=prompt)]
    tool_call_log = []

    for iteration in range(max_iterations):
        try:
            response = await llm_with_tools.ainvoke(messages)
        except Exception as e:
            logger.warning(f"[{node_name}] LLM 工具调用失败 (iteration {iteration}): {e}")
            errors.append(f"[{node_name}] LLM 工具调用失败: {e}")
            break

        # 若无 tool_calls，返回最终 content
        if not response.tool_calls:
            logger.info(f"[{node_name}] Tools 调用完成（{iteration} 轮），返回最终结果")
            content = response.content if hasattr(response, 'content') else str(response)
            return (content, tool_call_log)

        # 追加 AI 消息（含 tool_calls）
        messages.append(response)

        # 执行所有 tool_calls（asyncio.gather 并行）
        async def _exec_tool(tool_call):
            tool_name = tool_call['name']
            tool_args = tool_call['args']
            tool = tool_map.get(tool_name)
            if not tool:
                return ToolMessage(
                    content=f"工具 {tool_name} 不存在",
                    tool_call_id=tool_call['id']
                )
            try:
                logger.info(f"[{node_name}] 调用工具 {tool_name} (args={tool_args})")
                result = await tool.ainvoke(tool_args)
                tool_call_log.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result_preview": (result if isinstance(result, str) else str(result))[:200]
                })
                return ToolMessage(
                    content=result if isinstance(result, str) else str(result),
                    tool_call_id=tool_call['id']
                )
            except Exception as e:
                logger.error(f"[{node_name}] 工具 {tool_name} 执行失败: {e}", exc_info=True)
                return ToolMessage(
                    content=f"工具执行失败: {e}",
                    tool_call_id=tool_call['id']
                )

        tool_messages = await asyncio.gather(*[
            _exec_tool(tc) for tc in response.tool_calls
        ])
        messages.extend(tool_messages)

        logger.info(
            f"[{node_name}] iteration {iteration + 1}: 执行 {len(response.tool_calls)} 个工具"
        )

    # 达到最大轮数，强制获取最终 content
    logger.warning(f"[{node_name}] 达到最大工具调用轮数 {max_iterations}，强制结束")
    try:
        final_response = await llm.ainvoke(messages)
        content = final_response.content if hasattr(final_response, 'content') else str(final_response)
        return (content, tool_call_log)
    except Exception as e:
        logger.error(f"[{node_name}] 最终 LLM 调用失败: {e}")
        errors.append(f"[{node_name}] 最终 LLM 调用失败: {e}")
        return ("", tool_call_log)
