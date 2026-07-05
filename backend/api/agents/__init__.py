# -*- coding: utf-8 -*-
"""ClaimCraft 案件智能体工作流（多证据聚合版）。

基于 LangGraph 1.0 构建 6 节点工作流：
OCR → 证据分类 → 字段抽取 → (HITL 校正) → 证据链构造 → 投诉生成

使用 MemorySaver checkpointer 实现案件级状态持久化。
"""
from api.agents.graph import build_case_workflow

__all__ = ["build_case_workflow"]
