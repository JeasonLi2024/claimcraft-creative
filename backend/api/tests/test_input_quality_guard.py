# -*- coding: utf-8 -*-
"""输入质量门纯函数单元测试（input-quality-guard）。

覆盖三道门的核心判定纯函数：
- Gate 1 `_compute_evidence_relevance`（classify_node）
- Gate 2 `_is_evidence_critically_insufficient`（extract_node）
- Gate 3 `assess_data_sufficiency`（utils.data_sufficiency）

均为纯计算函数（不依赖 DB / LLM），用 `SimpleTestCase`。

运行方式（任选其一）：
    cd backend
    python manage.py test api.tests.test_input_quality_guard -v 2
    # 或（如已安装 pytest）：
    python -m pytest api/tests/test_input_quality_guard.py -v
"""
import os
import sys

# 确保可从项目根目录或 backend/ 目录运行（backend/ 需在 sys.path 上以解析 claimcraft.settings）
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django  # noqa: E402
from django.apps import apps as _django_apps  # noqa: E402
if not _django_apps.ready:
    django.setup()

from django.test import SimpleTestCase  # noqa: E402

from api.agents.nodes.classify_node import _compute_evidence_relevance  # noqa: E402
from api.agents.nodes.extract_node import (  # noqa: E402
    _is_evidence_critically_insufficient,
)
from api.agents.utils.data_sufficiency import assess_data_sufficiency  # noqa: E402


class ComputeEvidenceRelevanceTest(SimpleTestCase):
    """Gate 1：`_compute_evidence_relevance` 测试。"""

    def test_empty_results_return_all_other(self):
        """无分类结果 → ratio 0.0 / all_other True。"""
        r = _compute_evidence_relevance("shopping", [])
        self.assertEqual(r["relevance_ratio"], 0.0)
        self.assertTrue(r["all_other"])
        self.assertEqual(r["total_count"], 0)

    def test_all_other_low_relevance(self):
        """shopping 案件全 other → ratio 0.0 / all_other True。"""
        results = [
            {"evidence_category": "other"},
            {"evidence_category": "other"},
        ]
        r = _compute_evidence_relevance("shopping", results)
        self.assertEqual(r["relevance_ratio"], 0.0)
        self.assertTrue(r["all_other"])
        self.assertEqual(r["matched_count"], 0)
        self.assertEqual(r["total_count"], 2)

    def test_partial_match_ratio(self):
        """混合命中：2/4 命中 shopping 预期类别 → ratio 0.5。"""
        results = [
            {"evidence_category": "chat_screenshot"},  # 命中
            {"evidence_category": "payment_record"},   # 命中
            {"evidence_category": "other"},             # 未命中
            {"evidence_category": "medical_record"},    # 未命中（非 shopping 预期）
        ]
        r = _compute_evidence_relevance("shopping", results)
        self.assertEqual(r["relevance_ratio"], 0.5)
        self.assertEqual(r["matched_count"], 2)
        self.assertEqual(r["total_count"], 4)
        self.assertFalse(r["all_other"])

    def test_full_match_ratio(self):
        """全部命中 → ratio 1.0。"""
        results = [
            {"evidence_category": "chat_screenshot"},
            {"evidence_category": "product_order"},
        ]
        r = _compute_evidence_relevance("shopping", results)
        self.assertEqual(r["relevance_ratio"], 1.0)
        self.assertTrue(r["expected_categories"])  # shopping 有预期集合

    def test_other_case_type_not_restricted(self):
        """other / 未知案件类型不做限制 → ratio 1.0，expected 为空。"""
        results = [{"evidence_category": "other"}]
        r = _compute_evidence_relevance("other", results)
        self.assertEqual(r["relevance_ratio"], 1.0)
        self.assertEqual(r["expected_categories"], [])
        # all_other 仍如实反映
        self.assertTrue(r["all_other"])


class IsEvidenceCriticallyInsufficientTest(SimpleTestCase):
    """Gate 2：`_is_evidence_critically_insufficient` 测试（严格 AND）。"""

    def test_all_conditions_met_triggers(self):
        """全 other + 均值 0.2 + 0 字段 → True。"""
        classify = [
            {"evidence_category": "other"},
            {"evidence_category": "other"},
        ]
        preclassify = [{"confidence": 0.2}, {"confidence": 0.2}]
        self.assertTrue(
            _is_evidence_critically_insufficient(classify, preclassify, 0)
        )

    def test_not_all_other_does_not_trigger(self):
        """存在非 other 分类 → False（即便字段为 0）。"""
        classify = [
            {"evidence_category": "chat_screenshot"},
            {"evidence_category": "other"},
        ]
        preclassify = [{"confidence": 0.2}, {"confidence": 0.2}]
        self.assertFalse(
            _is_evidence_critically_insufficient(classify, preclassify, 0)
        )

    def test_high_confidence_does_not_trigger(self):
        """全 other 但预分类均值 >= 0.5 → False（LLM 有把握）。"""
        classify = [{"evidence_category": "other"}]
        preclassify = [{"confidence": 0.8}]
        self.assertFalse(
            _is_evidence_critically_insufficient(classify, preclassify, 0)
        )

    def test_has_fields_does_not_trigger(self):
        """全 other + 低置信度但提取到字段（>0）→ False。"""
        classify = [{"evidence_category": "other"}]
        preclassify = [{"confidence": 0.2}]
        self.assertFalse(
            _is_evidence_critically_insufficient(classify, preclassify, 3)
        )

    def test_empty_classify_does_not_trigger(self):
        """无证据（另由 preclassify_node 处理）→ False。"""
        self.assertFalse(_is_evidence_critically_insufficient([], [], 0))


class AssessDataSufficiencyTest(SimpleTestCase):
    """Gate 3：`assess_data_sufficiency` 测试。"""

    def test_sufficient(self):
        """≥3 字段 + ≥2 链节点 + 长描述 → sufficient（score 1.0）。"""
        r = assess_data_sufficiency(
            all_fields=[{"a": 1}, {"b": 2}, {"c": 3}],
            evidence_chain=[{"x": 1}, {"y": 2}],
            case_description="这是一段足够长的案件描述" * 5,  # >= 50 字
        )
        self.assertEqual(r["level"], "sufficient")
        self.assertGreaterEqual(r["score"], 0.6)
        self.assertEqual(r["missing_dimensions"], [])

    def test_sparse(self):
        """少量字段 + 单链节点 + 中等描述 → sparse。"""
        r = assess_data_sufficiency(
            all_fields=[{"a": 1}],           # 0.2
            evidence_chain=[{"x": 1}],       # 0.15
            case_description="二十字左右的一段中等长度案件描述内容",  # >= 20 字 → 0.15
        )
        self.assertEqual(r["level"], "sparse")
        self.assertGreaterEqual(r["score"], 0.3)
        self.assertLess(r["score"], 0.6)

    def test_critically_sparse(self):
        """无字段 + 无链 + 极短描述 → critically_sparse，含缺失维度。"""
        r = assess_data_sufficiency(
            all_fields=[],
            evidence_chain=[],
            case_description="太短",
        )
        self.assertEqual(r["level"], "critically_sparse")
        self.assertLess(r["score"], 0.3)
        self.assertEqual(len(r["missing_dimensions"]), 3)

    def test_missing_dimensions_named(self):
        """缺失维度文案包含字段/时间线/描述关键词。"""
        r = assess_data_sufficiency(
            all_fields=[],
            evidence_chain=[],
            case_description="",
        )
        joined = "".join(r["missing_dimensions"])
        self.assertIn("证据字段", joined)
        self.assertIn("时间线", joined)
        self.assertIn("案件描述", joined)
