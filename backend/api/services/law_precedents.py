# -*- coding: utf-8 -*-
"""v10 维权判例数据（供 lookup_precedent 工具使用）。

判例数据来源：公开的消费者维权典型案例（中国消费者协会公布的年度案例、
最高法公布的消费者权益保护典型案例、各级法院公布的维权判例）。

当前版本：内置 10 个典型维权判例，按场景关键词匹配。
后续可扩展为向量检索（与法条检索同样的 RAG 架构）。
"""
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 维权判例数据（基于公开典型案例整理）
# ============================================================

_PRECEDENTS = [
    {
        "case_title": "虚假宣传退一赔三案",
        "scenario_keywords": ["虚假宣传", "欺诈", "退一赔三", "夸大宣传", "误导"],
        "case_type": "欺诈行为",
        "applicable_law": "消费者权益保护法第五十五条",
        "facts": "消费者购买某品牌手机，商家宣传为\u201c全新原装正品\u201d，实为翻新机。",
        "court_ruling": "法院认定商家构成欺诈，判决退一赔三",
        "compensation": "退还货款 + 三倍赔偿",
        "amount_range": "三倍购买价款，最低500元"
    },
    {
        "case_title": "食品安全十倍赔偿案",
        "scenario_keywords": ["食品过期", "食品变质", "十倍赔偿", "食品安全", "异物"],
        "case_type": "食品安全",
        "applicable_law": "食品安全法第一百四十八条",
        "facts": "消费者购买食品发现已过保质期，食品中有异物。",
        "court_ruling": "法院判决十倍赔偿，最低1000元",
        "compensation": "退还货款 + 十倍赔偿",
        "amount_range": "十倍价款，最低1000元"
    },
    {
        "case_title": "延迟发货违约赔偿案",
        "scenario_keywords": ["延迟发货", "延迟发货", "未发货", "延迟发货"],
        "case_type": "合同违约",
        "applicable_law": "民法典第五百七十七条",
        "facts": "消费者下单购买商品，商家承诺48小时内发货，实际超过7天未发货。",
        "court_ruling": "法院判决商家承担违约责任，退还货款并赔偿实际损失",
        "compensation": "退还货款 + 实际损失赔偿",
        "amount_range": "根据实际损失计算"
    },
    {
        "case_title": "商品质量三包责任案",
        "scenario_keywords": ["质量问题", "瑕疵", "三包", "性能不符", "质量不达标"],
        "case_type": "产品质量",
        "applicable_law": "产品质量法第四十条",
        "facts": "消费者购买电器，使用不久出现性能故障，商家拒绝退货。",
        "court_ruling": "法院判决商家履行三包义务，退货退款",
        "compensation": "退货退款 + 损失赔偿",
        "amount_range": "退货款 + 实际损失"
    },
    {
        "case_title": "网购七日无理由退货案",
        "scenario_keywords": ["七日无理由", "退货被拒", "网购退货", "七天退货"],
        "case_type": "消费者权利",
        "applicable_law": "消费者权益保护法第二十五条",
        "facts": "消费者网购商品，7日内申请退货，商家以\u201c已拆封\u201d为由拒绝。",
        "court_ruling": "法院认定商品完好，判决商家履行七日无理由退货义务",
        "compensation": "退还货款 + 运费由消费者承担",
        "amount_range": "全额退款"
    },
    {
        "case_title": "电商平台连带责任案",
        "scenario_keywords": ["平台责任", "假货", "平台不作为", "资质造假"],
        "case_type": "平台责任",
        "applicable_law": "电子商务法第三十八条",
        "facts": "消费者在平台购买到假货，平台未采取必要措施。",
        "court_ruling": "法院判决平台承担连带责任",
        "compensation": "平台与经营者连带赔偿",
        "amount_range": "根据实际损失"
    },
    {
        "case_title": "订单成立合同纠纷案",
        "scenario_keywords": ["取消订单", "价格标错", "合同成立", "格式条款"],
        "case_type": "合同成立",
        "applicable_law": "电子商务法第四十九条",
        "facts": "消费者下单后商家以\u201c价格标错\u201d为由单方面取消订单。",
        "court_ruling": "法院认定订单提交即合同成立，判决商家履行合同",
        "compensation": "履行合同 or 赔偿损失",
        "amount_range": "合同差价 + 实际损失"
    },
    {
        "case_title": "个人信息泄露维权案",
        "scenario_keywords": ["信息泄露", "隐私", "个人信息", "数据泄露"],
        "case_type": "个人信息",
        "applicable_law": "个人信息保护法",
        "facts": "消费者在平台购物后收到大量骚扰电话，平台泄露个人信息。",
        "court_ruling": "法院判决平台承担侵权责任",
        "compensation": "赔偿损失 + 精神损害赔偿",
        "amount_range": "根据损害程度"
    },
    {
        "case_title": "价格欺诈赔偿案",
        "scenario_keywords": ["价格欺诈", "虚构原价", "虚假折扣", "价格问题"],
        "case_type": "价格欺诈",
        "applicable_law": "消费者权益保护法第五十五条",
        "facts": "商家虚构原价进行虚假打折，消费者实际支付价格高于真实原价。",
        "court_ruling": "法院认定构成欺诈，判决退一赔三",
        "compensation": "退还货款 + 三倍赔偿",
        "amount_range": "三倍购买价款，最低500元"
    },
    {
        "case_title": "假冒伪劣商品赔偿案",
        "scenario_keywords": ["假冒", "伪劣", "假货", "以次充好", "假冒伪劣"],
        "case_type": "欺诈行为",
        "applicable_law": "消费者权益保护法第五十五条",
        "facts": "消费者购买品牌商品，经鉴定为假冒商品。",
        "court_ruling": "法院认定构成欺诈，判决退一赔三",
        "compensation": "退还货款 + 三倍赔偿",
        "amount_range": "三倍购买价款，最低500元"
    },
]


def get_precedents_by_scenario(scenario: str) -> list[dict]:
    """按场景关键词匹配维权判例。

    Args:
        scenario: 维权场景描述（如 "商家虚假宣传导致退款"）

    Returns:
        匹配的判例列表（含 case_title/case_type/applicable_law/facts/court_ruling/compensation）
    """
    if not scenario:
        return []

    scenario_lower = scenario.lower()
    matched = []

    for p in _PRECEDENTS:
        # 检查场景关键词是否出现在用户描述中
        for kw in p.get('scenario_keywords', []):
            if kw in scenario_lower:
                matched.append({
                    'case_title': p['case_title'],
                    'case_type': p['case_type'],
                    'applicable_law': p['applicable_law'],
                    'facts': p['facts'],
                    'court_ruling': p['court_ruling'],
                    'compensation': p['compensation'],
                    'amount_range': p['amount_range'],
                    'matched_keyword': kw,
                })
                break  # 每个判例只匹配一次

    return matched


def get_all_precedents() -> list[dict]:
    """获取全部维权判例。"""
    return _PRECEDENTS.copy()
