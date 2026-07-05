# -*- coding: utf-8 -*-
"""langgraph dev 开发测试用入口（轻量级，不依赖 Django）。

用途：
    用于 `langgraph dev` 命令启动开发服务器，验证 langgraph.json 配置、
    graph 拓扑、Studio UI 等基础能力是否可用。

设计说明：
    - 完全不依赖 Django ORM / MySQL / PostgreSQL，避免环境配置污染
    - 复刻真实工作流拓扑（START → ocr → classify → extract → evidence_chain → complaint → END）
    - 节点用 mock 实现，便于在 Studio UI 中快速 threadless run 验证
    - 真实业务 graph 仍在 backend/api/agents/graph.py，受 Django 环境托管

启动方式：
    cd d:\\claimcraft-creative
    langgraph dev
    # 打开 https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
"""
from typing import Annotated, Any, Literal, Optional, TypedDict
from operator import add

from langgraph.graph import StateGraph, START, END


class DevWorkflowState(TypedDict):
    """开发测试用状态（与 backend/api/agents/state.py 同构，但无 Django 依赖）。"""
    case_id: int
    evidence_ids: list[int]

    evidence_ocr_results: Annotated[list[dict], add]
    evidence_classify_results: Annotated[list[dict], add]
    evidence_extract_results: Annotated[list[dict], add]
    needs_human_review: bool

    evidence_chain: list[dict]
    complaint_draft: Optional[dict]
    review_decision: Optional[dict]

    errors: Annotated[list[str], add]


async def dev_ocr_node(state: DevWorkflowState) -> dict[str, Any]:
    """Mock OCR 节点：模拟多证据 OCR + 纠错。"""
    evidence_ids = state.get("evidence_ids", [1, 2])
    results = [
        {
            "evidence_id": eid,
            "evidence_code": f"E{eid:03d}",
            "image_path": f"/mock/evidence_{eid}.png",
            "ocr_raw_text": f"原始 OCR 文本 {eid}（含错别字：兀→元）",
            "ocr_corrected_text": f"纠错后文本 {eid}（已修正：元）",
            "ocr_strategy_used": "mock_llm_vision",
            "ocr_status": "done",
            "errors": [],
        }
        for eid in evidence_ids
    ]
    return {"evidence_ocr_results": results}


async def dev_classify_node(state: DevWorkflowState) -> dict[str, Any]:
    """Mock 分类节点：模拟证据分类。"""
    ocr_results = state.get("evidence_ocr_results", [])
    results = [
        {
            "evidence_id": r["evidence_id"],
            "evidence_code": r["evidence_code"],
            "evidence_category": "order" if i % 2 == 0 else "chat",
            "category_label": "订单" if i % 2 == 0 else "聊天",
            "confidence": 0.92 + i * 0.01,
        }
        for i, r in enumerate(ocr_results)
    ]
    return {"evidence_classify_results": results}


async def dev_extract_node(state: DevWorkflowState) -> dict[str, Any]:
    """Mock 抽取节点：模拟字段抽取。"""
    ocr_results = state.get("evidence_ocr_results", [])
    results = [
        {
            "evidence_id": r["evidence_id"],
            "evidence_code": r["evidence_code"],
            "fields": {
                "order_id": f"ORD{r['evidence_id']:06d}",
                "amount": f"¥{r['evidence_id'] * 99}.00",
                "product": "示例商品",
            },
            "needs_human_review": False,
        }
        for r in ocr_results
    ]
    return {
        "evidence_extract_results": results,
        "needs_human_review": False,
    }


def _route_after_extract(state: DevWorkflowState) -> Literal["review", "evidence_chain"]:
    if state.get("needs_human_review"):
        return "review"
    return "evidence_chain"


async def dev_review_node(state: DevWorkflowState) -> dict[str, Any]:
    """Mock 人工校正节点（演示用，实际 HITL 需要 interrupt）。"""
    return {"review_decision": {"approved": True, "reviewer": "dev_user"}}


async def dev_evidence_chain_node(state: DevWorkflowState) -> dict[str, Any]:
    """Mock 证据链节点：构造时间线。"""
    ocr_results = state.get("evidence_ocr_results", [])
    chain = [
        {
            "datetime": f"2026-07-{i + 1:02d} 10:00",
            "event": r["ocr_corrected_text"],
            "category": "下单" if i % 2 == 0 else "沟通",
            "evidence_codes": [r["evidence_code"]],
            "chain_order": i,
        }
        for i, r in enumerate(ocr_results)
    ]
    return {"evidence_chain": chain}


async def dev_complaint_node(state: DevWorkflowState) -> dict[str, Any]:
    """Mock 投诉生成节点。"""
    chain = state.get("evidence_chain", [])
    return {
        "complaint_draft": {
            "title": "【开发测试】投诉书草稿",
            "content": f"基于 {len(chain)} 条证据链构造的投诉内容（mock）。",
            "template_type": "standard",
            "tone": "restrained",
        }
    }


def _build_dev_graph():
    """构建开发测试用 graph（无 checkpointer，无 store，无 Django 依赖）。"""
    g = StateGraph(DevWorkflowState)

    g.add_node("ocr", dev_ocr_node)
    g.add_node("classify", dev_classify_node)
    g.add_node("extract", dev_extract_node)
    g.add_node("review", dev_review_node)
    g.add_node("evidence_chain", dev_evidence_chain_node)
    g.add_node("complaint", dev_complaint_node)

    g.add_edge(START, "ocr")
    g.add_edge("ocr", "classify")
    g.add_edge("classify", "extract")
    g.add_conditional_edges(
        "extract",
        _route_after_extract,
        {"review": "review", "evidence_chain": "evidence_chain"},
    )
    g.add_edge("review", "evidence_chain")
    g.add_edge("evidence_chain", "complaint")
    g.add_edge("complaint", END)

    return g.compile()


# langgraph.json 的 graphs 字段引用此变量
graph = _build_dev_graph()
