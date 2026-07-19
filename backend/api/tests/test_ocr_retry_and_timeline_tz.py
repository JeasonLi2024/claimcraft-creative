# -*- coding: utf-8 -*-
"""回归测试：
1. OCR 策略级重试不再重试 FileNotFoundError 等非瞬时文件系统错误（问题 2）。
2. timeline_service 的 datetime 归一化到 USE_TZ 约定，避免 naive/aware 混排 TypeError
   与向 USE_TZ=False 的 MySQL 写入 aware 报错（问题 3）。
"""
import os
from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from api.services import ocr_strategies
from api.services.timeline_service import _coerce_tz, _parse_datetime


class OCRRetryPredicateTests(SimpleTestCase):
    """问题 2：FileNotFoundError 属非瞬时错误，不应重试。"""

    def test_file_not_found_is_not_retryable(self):
        self.assertFalse(ocr_strategies._is_retryable_ocr_error(FileNotFoundError()))

    def test_other_fs_errors_not_retryable(self):
        for exc in (PermissionError(), IsADirectoryError(), NotADirectoryError()):
            self.assertFalse(ocr_strategies._is_retryable_ocr_error(exc))

    def test_transient_errors_are_retryable(self):
        for exc in (TimeoutError(), ConnectionError(), OSError("transient")):
            self.assertTrue(ocr_strategies._is_retryable_ocr_error(exc))

    def test_decorator_does_not_retry_file_not_found(self):
        """装饰后的函数遇到 FileNotFoundError 只调用一次并原样抛出。"""
        with mock.patch.dict(os.environ, {
            "OCR_RETRY_MAX_ATTEMPTS": "3",
            "OCR_RETRY_WAIT_MIN": "0",
            "OCR_RETRY_WAIT_MAX": "0",
        }):
            retry = ocr_strategies._build_ocr_retry()
            calls = {"n": 0}

            @retry
            def _always_missing():
                calls["n"] += 1
                raise FileNotFoundError("/app/media/evidences/3/E1-1.png")

            with self.assertRaises(FileNotFoundError):
                _always_missing()
            self.assertEqual(calls["n"], 1)  # 未重试

    def test_decorator_retries_transient_error(self):
        """瞬时错误（ConnectionError）仍按 max_attempts 重试。"""
        with mock.patch.dict(os.environ, {
            "OCR_RETRY_MAX_ATTEMPTS": "3",
            "OCR_RETRY_WAIT_MIN": "0",
            "OCR_RETRY_WAIT_MAX": "0",
        }):
            retry = ocr_strategies._build_ocr_retry()
            calls = {"n": 0}

            @retry
            def _flaky():
                calls["n"] += 1
                raise ConnectionError("429")

            with self.assertRaises(ConnectionError):
                _flaky()
            self.assertEqual(calls["n"], 3)  # 重试到上限


class TimelineDatetimeTZTests(SimpleTestCase):
    """问题 3：datetime 归一化到 USE_TZ 约定。"""

    @override_settings(USE_TZ=False)
    def test_parse_datetime_returns_naive_when_use_tz_false(self):
        dt = _parse_datetime("2025-03-01 10:30:00")
        self.assertIsNotNone(dt)
        self.assertTrue(timezone.is_naive(dt))

    @override_settings(USE_TZ=False)
    def test_parse_iso_with_offset_becomes_naive(self):
        dt = _parse_datetime("2025-03-01T10:30:00+08:00")
        self.assertIsNotNone(dt)
        self.assertTrue(timezone.is_naive(dt))

    @override_settings(USE_TZ=True)
    def test_parse_datetime_returns_aware_when_use_tz_true(self):
        dt = _parse_datetime("2025-03-01 10:30:00")
        self.assertIsNotNone(dt)
        self.assertTrue(timezone.is_aware(dt))

    @override_settings(USE_TZ=False)
    def test_coerce_tz_strips_awareness(self):
        aware = datetime(2025, 3, 1, 10, 30, tzinfo=dt_timezone.utc)
        naive = datetime(2025, 3, 1, 10, 30)
        self.assertTrue(timezone.is_naive(_coerce_tz(aware)))
        self.assertTrue(timezone.is_naive(_coerce_tz(naive)))

    @override_settings(USE_TZ=False)
    def test_mixed_naive_aware_are_sortable_after_coerce(self):
        """混合 naive/aware 经 _coerce_tz 后可安全排序（复现问题 3 的 TypeError 场景）。"""
        aware = datetime(2025, 3, 2, 9, 0, tzinfo=dt_timezone.utc)
        naive = datetime(2025, 3, 1, 9, 0)
        coerced = sorted([_coerce_tz(aware), _coerce_tz(naive)])  # 不应抛 TypeError
        self.assertEqual(len(coerced), 2)

    def test_coerce_none_returns_none(self):
        self.assertIsNone(_coerce_tz(None))
