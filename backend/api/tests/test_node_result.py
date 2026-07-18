# -*- coding: utf-8 -*-
"""NodeResult 统一输出契约单元测试（Task 1.1）。

验证：
- NodeResult 能正确实例化（含必填字段 node / quality / metrics）
- NodeResult.model_dump() 返回 dict 可作为 state["node_result"] 值
- WorkflowVersion.to_initial_state() 返回 dict 含 4 个版本字段

运行方式（任选其一）：
    cd backend
    python manage.py test api.tests.test_node_result -v 2
    # 或（如已安装 pytest）：
    python -m pytest api/tests/test_node_result.py -v
"""
import os
import sys
import unittest

# 确保可从项目根目录或 backend/ 目录运行（backend/ 需在 sys.path 上以解析 claimcraft.settings）
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# 配置 Django（幂等：manage.py test 运行时 Django 已由 runner 配置，此处为 no-op；
# pytest / 独立运行时由本 shim 完成配置，使 from api.agents.schemas import ... 可用）
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django
from django.apps import apps as _django_apps
if not _django_apps.ready:
    django.setup()

from api.agents.schemas import (  # noqa: E402  (import 在 Django setup 之后)
    DocumentVersion,
    Issue,
    Metrics,
    NodeResult,
    ProvenanceItem,
    QualityReport,
    Warning,
)
from api.agents.version import WorkflowVersion  # noqa: E402


class NodeResultInstantiationTest(unittest.TestCase):
    """NodeResult 实例化与必填字段测试。"""

    def test_minimal_node_result_with_required_fields(self):
        """测试 NodeResult 仅传入必填字段（node / quality / metrics）能正常实例化。"""
        quality = QualityReport(score=0.85, status="pass")
        metrics = Metrics(duration_ms=120)
        result = NodeResult(node="ocr", quality=quality, metrics=metrics)

        self.assertEqual(result.node, "ocr")
        self.assertEqual(result.quality.score, 0.85)
        self.assertEqual(result.quality.status, "pass")
        self.assertEqual(result.metrics.duration_ms, 120)
        # 默认值
        self.assertEqual(result.data, {})
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.errors, [])
        self.assertEqual(result.provenance, [])
        self.assertEqual(result.metrics.model_calls, 0)
        self.assertEqual(result.metrics.api_calls, 0)
        self.assertEqual(result.metrics.tokens_used, 0)
        self.assertEqual(result.metrics.retries, 0)
        self.assertEqual(result.quality.coverage, 1.0)
        self.assertEqual(result.quality.blocking_issues, [])
        self.assertEqual(result.quality.details, {})

    def test_node_result_with_full_payload(self):
        """测试 NodeResult 含全部子结构（warnings/errors/provenance/data）实例化。"""
        result = NodeResult(
            node="extract",
            data={"evidence_id": 42, "fields_count": 5},
            quality=QualityReport(
                score=0.62,
                coverage=0.8,
                status="warn",
                blocking_issues=[
                    Issue(
                        code="field.low_confidence",
                        message="金额置信度过低",
                        severity="blocking",
                        evidence_id=42,
                        stage="extract",
                        recoverable=True,
                    )
                ],
                details={"low_confidence_count": 1},
            ),
            warnings=[
                Warning(
                    code="ocr.low_confidence",
                    message="OCR 置信度 0.55",
                    severity="warning",
                    evidence_id=42,
                    stage="ocr",
                )
            ],
            errors=[
                Issue(
                    code="field.missing",
                    message="缺少下单时间",
                    severity="warning",
                    recoverable=True,
                )
            ],
            provenance=[
                ProvenanceItem(
                    node="extract",
                    evidence_id=42,
                    field_name="金额",
                    source_ref="EV001:金额:rect(10,20,100,40)",
                    ts="2026-07-17T10:00:00Z",
                )
            ],
            metrics=Metrics(
                duration_ms=350,
                model_calls=2,
                api_calls=1,
                tokens_used=1500,
                retries=0,
            ),
        )

        self.assertEqual(result.node, "extract")
        self.assertEqual(result.data["evidence_id"], 42)
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(len(result.provenance), 1)
        self.assertEqual(result.quality.blocking_issues[0].code, "field.low_confidence")
        self.assertEqual(result.provenance[0].source_ref, "EV001:金额:rect(10,20,100,40)")
        self.assertEqual(result.metrics.tokens_used, 1500)


class NodeResultStateInteropTest(unittest.TestCase):
    """NodeResult 与 CaseWorkflowState["node_result"] 互操作测试。"""

    def test_model_dump_returns_dict_compatible_with_state(self):
        """测试 NodeResult.model_dump() 返回 dict 可作为 state["node_result"] 值。"""
        quality = QualityReport(score=0.9, status="pass")
        metrics = Metrics(duration_ms=100, model_calls=1, tokens_used=500)
        result = NodeResult(
            node="classify",
            data={"categories": ["聊天截图"]},
            quality=quality,
            metrics=metrics,
        )

        dumped = result.model_dump()

        # 必须是 dict 类型（TypedDict node_result: Optional[dict] 接受）
        self.assertIsInstance(dumped, dict)
        # 关键字段在 dump 后保留
        self.assertEqual(dumped["node"], "classify")
        self.assertIn("quality", dumped)
        self.assertIn("metrics", dumped)
        self.assertEqual(dumped["quality"]["score"], 0.9)
        self.assertEqual(dumped["metrics"]["duration_ms"], 100)
        # JSON 可序列化（state 需持久化到 PostgresSaver checkpoint）
        import json
        json_str = json.dumps(dumped)
        self.assertIn('"node": "classify"', json_str)

    def test_node_result_dict_can_be_assigned_to_state(self):
        """模拟 state["node_result"] = NodeResult.model_dump() 赋值场景。"""
        # 构造一个最小 state dict（模拟 CaseWorkflowState 子集）
        state = {
            "case_id": 1,
            "evidence_ids": [1, 2],
            "case_mode": "complain",
            "node_result": None,
        }
        self.assertIsNone(state["node_result"])

        quality = QualityReport(score=0.7, status="warn")
        metrics = Metrics(duration_ms=200)
        result = NodeResult(node="ocr", quality=quality, metrics=metrics)

        # 节点返回 partial update dict 时，node_result 字段存储 NodeResult.model_dump()
        state["node_result"] = result.model_dump()

        self.assertIsNotNone(state["node_result"])
        self.assertEqual(state["node_result"]["node"], "ocr")
        self.assertEqual(state["node_result"]["quality"]["status"], "warn")
        self.assertEqual(state["node_result"]["metrics"]["duration_ms"], 200)


class WorkflowVersionTest(unittest.TestCase):
    """WorkflowVersion 常量与注入测试。"""

    def test_to_initial_state_returns_dict_with_4_version_fields(self):
        """测试 WorkflowVersion.to_initial_state() 返回 dict 含 4 个版本字段。"""
        initial_state = WorkflowVersion.to_initial_state()

        self.assertIsInstance(initial_state, dict)
        # 4 个版本字段全部存在
        self.assertIn("workflow_version", initial_state)
        self.assertIn("state_schema_version", initial_state)
        self.assertIn("policy_version", initial_state)
        self.assertIn("prompt_bundle_version", initial_state)
        # 值符合 SPEC 约定
        self.assertEqual(initial_state["workflow_version"], "v11")
        self.assertEqual(initial_state["state_schema_version"], 1)
        self.assertEqual(initial_state["policy_version"], "v1")
        self.assertEqual(initial_state["prompt_bundle_version"], "2026.07")

    def test_to_initial_state_does_not_overwrite_caller_provided_keys(self):
        """测试 WorkflowVersion 注入不覆盖调用方传入的同名字段（调用方优先）。

        场景：WorkflowRunner.run_and_persist 中
        initial_state = {**WorkflowVersion.to_initial_state(), **initial_state}
        — 调用方传入的同名字段应覆盖版本常量默认值。
        """
        caller_state = {
            "workflow_version": "v99",  # 调用方覆盖
            "evidence_ids": [1, 2, 3],
            "case_mode": "complain",
        }
        merged = {**WorkflowVersion.to_initial_state(), **caller_state}

        # 调用方 workflow_version 覆盖版本常量
        self.assertEqual(merged["workflow_version"], "v99")
        # 未被覆盖的版本常量保留默认值
        self.assertEqual(merged["state_schema_version"], 1)
        self.assertEqual(merged["policy_version"], "v1")
        self.assertEqual(merged["prompt_bundle_version"], "2026.07")
        # 调用方的业务字段保留
        self.assertEqual(merged["evidence_ids"], [1, 2, 3])
        self.assertEqual(merged["case_mode"], "complain")


class DocumentVersionPlaceholderTest(unittest.TestCase):
    """DocumentVersion 占位模型测试（Task 4.1 将详细实现）。"""

    def test_document_version_can_be_instantiated(self):
        """测试 DocumentVersion 占位模型可实例化（含必填字段）。"""
        doc = DocumentVersion(
            document_id=1,
            version=3,
            content="投诉书正文…",
            created_at="2026-07-17T10:00:00Z",
        )
        self.assertEqual(doc.document_id, 1)
        self.assertEqual(doc.version, 3)
        self.assertEqual(doc.created_by_type, "ai")  # 默认值
        self.assertEqual(doc.created_by_id, None)  # 默认值
        self.assertEqual(doc.workflow_version, "")  # 默认空字符串


if __name__ == '__main__':
    unittest.main()
