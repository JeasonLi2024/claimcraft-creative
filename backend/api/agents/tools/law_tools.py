# -*- coding: utf-8 -*-
"""v10 法律工具集（4 个 LangChain @tool）。

供 complaint_node 使用，让 LLM 主动调用查询法律条款。

工具列表：
1. lookup_law：按关键词检索法律条文（RAG 向量检索）
2. lookup_precedent：查询类似维权判例（关键词匹配）
3. lookup_platform_rule：查询电商平台投诉规则
4. calculate_compensation：计算法定赔偿金额（退一赔三/十倍赔偿等）

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
            platform: 平台名称（taobao/tmall/jd/pdd/douyin/kuaishou/vipshop/suning/other）
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

    else:
        return json.dumps({
            "status": "unknown_violation",
            "message": f"未知的违法类型: {violation_type}",
            "supported_types": ["fraud", "food_safety", "late_delivery", "quality_issue"]
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
    """获取全部法律工具（用于 complaint_node 绑定）。

    Returns:
        list: 4 个 LangChain tool 实例
    """
    return [
        make_lookup_law_tool(),
        make_lookup_precedent_tool(),
        make_lookup_platform_rule_tool(),
        make_calculate_compensation_tool(),
    ]
