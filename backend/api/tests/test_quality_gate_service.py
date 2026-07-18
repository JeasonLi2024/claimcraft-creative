# -*- coding: utf-8 -*-
"""质量门服务单元测试（Task 2.3）。

验证 4 个 `evaluate_*` 函数 + `should_block_on_quality` 的核心场景：
1. `evaluate_material_understanding` 全成功 OCR + 高置信度分类 → `pass`
2. `evaluate_material_understanding` OCR 成功率 < 50% → `fail` + blocking issue
3. `evaluate_fact_checking` 字段完整率 < 30% → `fail` + blocking issue
4. `evaluate_case_organization` 覆盖率 < 80% → `warn`
5. `evaluate_document_generation` 空 content → `fail`
6. `should_block_on_quality` 对 `fail` 返回 True，对 `pass`/`warn` 返回 False

运行方式（任选其一）：
    cd backend
    python manage.py test api.tests.test_quality_gate_service -v 2
    # 或（如已安装 pytest）：
    python -m pytest api/tests/test_quality_gate_service.py -v
"""
import os
import sys
import unittest

# 确保可从项目根目录或 backend/ 目录运行（backend/ 需在 sys.path 上以解析 claimcraft.settings）
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# 配置 Django（幂等：manage.py test 运行时 Django 已由 runner 配置，此处为 no-op；
# pytest / 独立运行时由本 shim 完成配置，使 from api.services.* import ... 可用）
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django
from django.apps import apps as _django_apps
if not _django_apps.ready:
    django.setup()

from django.test import SimpleTestCase  # noqa: E402  (import 在 Django setup 之后)

from api.services.quality_gate_service import (  # noqa: E402
    evaluate_case_organization,
    evaluate_document_generation,
    evaluate_fact_checking,
    evaluate_material_understanding,
    should_block_on_quality,
)


class EvaluateMaterialUnderstandingTest(SimpleTestCase):
    """`evaluate_material_understanding` 测试。"""

    def test_pass_when_all_ocr_success_and_high_confidence(self):
        """测试 1：全成功 OCR + 高置信度分类 + 无 other → `status="pass"`。"""
        preclassify_results = [{"evidence_id": 1}, {"evidence_id": 2}]
        ocr_results = [
            {"evidence_id": 1, "ocr_status": "done"},
            {"evidence_id": 2, "ocr_status": "done"},
        ]
        classify_results = [
            {"evidence_id": 1, "evidence_category": "chat_screenshot", "confidence": 0.92},
            {"evidence_id": 2, "evidence_category": "product_order", "confidence": 0.88},
        ]

        report = evaluate_material_understanding(preclassify_results, ocr_results, classify_results)

        self.assertEqual(report.status, "pass")
        self.assertEqual(report.score, 1.0)
        self.assertEqual(report.coverage, 1.0)
        self.assertEqual(report.blocking_issues, [])
        self.assertEqual(report.details["ocr_success_rate"], 1.0)
        self.assertAlmostEqual(report.details["avg_classify_confidence"], 0.90)
        self.assertEqual(report.details["other_count"], 0)

    def test_fail_when_ocr_success_rate_below_50_percent(self):
        """测试 2：OCR 成功率 < 50% → `status="fail"` + blocking issue。"""
        preclassify_results = [{} for _ in range(5)]
        # 5 个证据中仅 1 个 OCR 成功 → 成功率 0.2 < 0.5 → blocking
        ocr_results = [
            {"evidence_id": 1, "ocr_status": "done"},
            {"evidence_id": 2, "ocr_status": "failed"},
            {"evidence_id": 3, "ocr_status": "failed"},
            {"evidence_id": 4, "ocr_status": "failed"},
            {"evidence_id": 5, "ocr_status": "failed"},
        ]
        classify_results = [
            {"evidence_id": 1, "evidence_category": "chat_screenshot", "confidence": 0.9},
        ]

        report = evaluate_material_understanding(preclassify_results, ocr_results, classify_results)

        self.assertEqual(report.status, "fail")
        self.assertEqual(report.coverage, 0.2)
        # blocking issue 应含 OCR 低成功率
        blocking_codes = [i.code for i in report.blocking_issues]
        self.assertIn("material.ocr_low_success_rate", blocking_codes)
        # OCR issue 应为 blocking（成功率 < 0.5）
        ocr_issue = next(i for i in report.blocking_issues if i.code == "material.ocr_low_success_rate")
        self.assertEqual(ocr_issue.severity, "blocking")
        self.assertEqual(ocr_issue.stage, "material_understanding")
        self.assertTrue(ocr_issue.recoverable)


class EvaluateFactCheckingTest(SimpleTestCase):
    """`evaluate_fact_checking` 测试。"""

    def test_fail_when_field_completeness_below_30_percent(self):
        """测试 3：字段完整率 < 30% → `status="fail"` + blocking issue。"""
        # 10 个字段仅 2 个有值 → 完整率 0.2 < 0.3 → blocking
        extract_results = [{
            "evidence_id": 1,
            "fields": [
                {"field_name": "f1", "field_value": "v1", "confidence": 0.95},
                {"field_name": "f2", "field_value": "", "confidence": 0.9},
                {"field_name": "f3", "field_value": "", "confidence": 0.9},
                {"field_name": "f4", "field_value": "v4", "confidence": 0.95},
                {"field_name": "f5", "field_value": "", "confidence": 0.9},
                {"field_name": "f6", "field_value": "", "confidence": 0.9},
                {"field_name": "f7", "field_value": "", "confidence": 0.9},
                {"field_name": "f8", "field_value": "", "confidence": 0.9},
                {"field_name": "f9", "field_value": "", "confidence": 0.9},
                {"field_name": "f10", "field_value": "", "confidence": 0.9},
            ],
        }]

        report = evaluate_fact_checking(extract_results)

        self.assertEqual(report.status, "fail")
        self.assertEqual(report.coverage, 0.2)
        blocking_codes = [i.code for i in report.blocking_issues]
        self.assertIn("fact.low_field_completeness", blocking_codes)
        completeness_issue = next(
            i for i in report.blocking_issues if i.code == "fact.low_field_completeness"
        )
        self.assertEqual(completeness_issue.severity, "blocking")
        self.assertEqual(completeness_issue.stage, "fact_checking")
        self.assertEqual(report.details["total_fields"], 10)
        self.assertEqual(report.details["low_confidence_count"], 0)


class EvaluateCaseOrganizationTest(SimpleTestCase):
    """`evaluate_case_organization` 测试。"""

    def test_warn_when_coverage_below_80_percent(self):
        """测试 4：引用覆盖率 < 80% → `status="warn"`（warning issue，非 blocking）。"""
        # 10 个证据中仅 5 个被链引用 → 覆盖率 0.5 < 0.8
        evidence_chain = [
            {"datetime": "2025-06-01T10:00", "evidence_codes": ["EV001", "EV002"]},
            {"datetime": "2025-06-05T10:00", "evidence_codes": ["EV003"]},
            {"datetime": "2025-06-10T10:00", "evidence_codes": ["EV004", "EV005"]},
        ]

        report = evaluate_case_organization(evidence_chain, total_evidence_count=10)

        self.assertEqual(report.status, "warn")
        self.assertEqual(report.coverage, 0.5)
        # 应有 warning 但无 blocking
        self.assertEqual(report.blocking_issues, [])
        # coverage warning 应存在
        all_issue_codes = [i.code for i in report.blocking_issues]
        self.assertNotIn("case.low_coverage", all_issue_codes)  # warning 不在 blocking 列表
        # details 应反映覆盖率
        self.assertEqual(report.details["coverage"], 0.5)
        self.assertEqual(report.details["time_gaps"], 0)
        self.assertEqual(report.details["chain_length"], 3)


class EvaluateDocumentGenerationTest(SimpleTestCase):
    """`evaluate_document_generation` 测试。"""

    def test_fail_when_content_empty(self):
        """测试 5：空 content → `status="fail"` + blocking issue。"""
        # case 5a：complaint_draft 为 None
        report_none = evaluate_document_generation(complaint_draft=None)
        self.assertEqual(report_none.status, "fail")
        self.assertEqual(report_none.coverage, 0.0)
        blocking_codes = [i.code for i in report_none.blocking_issues]
        self.assertIn("document.empty_content", blocking_codes)

        # case 5b：complaint_draft.content 为空字符串
        report_empty = evaluate_document_generation(complaint_draft={"content": ""})
        self.assertEqual(report_empty.status, "fail")
        self.assertEqual(report_empty.coverage, 0.0)
        blocking_codes_empty = [i.code for i in report_empty.blocking_issues]
        self.assertIn("document.empty_content", blocking_codes_empty)

        # case 5c：有 content → pass（占位参数默认 None 不触发 issue）
        report_ok = evaluate_document_generation(complaint_draft={"content": "投诉书正文..."})
        self.assertEqual(report_ok.status, "pass")
        self.assertEqual(report_ok.coverage, 1.0)
        self.assertEqual(report_ok.blocking_issues, [])
        self.assertTrue(report_ok.details["has_content"])

    def test_fail_when_legal_references_invalid_or_amount_inconsistent(self):
        """补充测试：法条验证失败 / 金额不一致 → blocking issue（占位参数）。

        覆盖 Task 4.2 占位参数路径，确保 None 不触发 issue，False 触发 blocking。
        """
        # case A：法条验证失败
        report_legal = evaluate_document_generation(
            complaint_draft={"content": "投诉书正文"},
            legal_references_valid=False,
        )
        self.assertEqual(report_legal.status, "fail")
        legal_codes = [i.code for i in report_legal.blocking_issues]
        self.assertIn("document.invalid_legal_reference", legal_codes)

        # case B：金额不一致
        report_amount = evaluate_document_generation(
            complaint_draft={"content": "投诉书正文"},
            amount_consistent=False,
        )
        self.assertEqual(report_amount.status, "fail")
        amount_codes = [i.code for i in report_amount.blocking_issues]
        self.assertIn("document.amount_inconsistent", amount_codes)

        # case C：占位参数为 None（默认）→ 不触发 issue
        report_none = evaluate_document_generation(
            complaint_draft={"content": "投诉书正文"},
            legal_references_valid=None,
            amount_consistent=None,
        )
        self.assertEqual(report_none.status, "pass")
        self.assertEqual(report_none.blocking_issues, [])


class ShouldBlockOnQualityTest(SimpleTestCase):
    """`should_block_on_quality` 测试。"""

    def test_returns_true_for_fail_status(self):
        """测试 6a：status="fail" → 返回 True。"""
        from api.agents.schemas import Issue, QualityReport
        quality = QualityReport(
            score=0.6,
            status="fail",
            blocking_issues=[
                Issue(
                    code="material.ocr_low_success_rate",
                    message="OCR 成功率 20% 低于阈值 80%",
                    severity="blocking",
                    stage="material_understanding",
                    recoverable=True,
                )
            ],
        )
        self.assertTrue(should_block_on_quality(quality))

    def test_returns_false_for_pass_status(self):
        """测试 6b：status="pass" → 返回 False。"""
        from api.agents.schemas import QualityReport
        quality = QualityReport(score=1.0, status="pass")
        self.assertFalse(should_block_on_quality(quality))

    def test_returns_false_for_warn_status(self):
        """测试 6c：status="warn" → 返回 False（warning 不阻塞，仅提示）。"""
        from api.agents.schemas import Issue, QualityReport
        quality = QualityReport(
            score=0.9,
            status="warn",
            blocking_issues=[],  # warn 时 blocking_issues 必为空
            details={"low_confidence_count": 3},
        )
        self.assertFalse(should_block_on_quality(quality))


if __name__ == '__main__':
    unittest.main()
