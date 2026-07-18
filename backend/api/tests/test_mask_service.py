from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.models import Case, Evidence
from api.services.mask_service import (
    contains_sensitive_info,
    detect_sensitive_type,
    mask_case_sensitive_info,
    mask_text,
)


class MaskTextTests(TestCase):
    def test_masks_phone_with_numeric_boundaries(self):
        self.assertEqual(mask_text('电话 13800138000'), '电话 138****8000')
        self.assertEqual(
            mask_text('订单号 202413800138000123'),
            '订单号 202413800138000123',
        )

    def test_masks_id_card_before_phone(self):
        masked = mask_text('身份证 130101199003078888')
        self.assertEqual(masked, '身份证 130***********8888')
        self.assertNotIn('199003078888', masked)
        self.assertEqual(detect_sensitive_type('130101199003078888'), 'id_card')

    def test_masks_structured_address_without_swallowing_following_sentence(self):
        masked = mask_text('地址北京市朝阳区望京街道，商品已签收')
        self.assertIn('北京市******', masked)
        self.assertIn('，商品已签收', masked)

    def test_invalid_long_number_is_not_sensitive(self):
        self.assertFalse(contains_sensitive_info('流水号 123456789012345678901234'))


class MaskCaseTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='mask-owner')
        self.case = Case.objects.create(title='脱敏测试', owner=user)

    def test_scans_unflagged_evidence_and_does_not_return_original_by_default(self):
        Evidence.objects.create(
            case=self.case,
            code='E1',
            evidence_type='聊天记录',
            description='联系电话 13800138000',
            source_time=timezone.now(),
            has_sensitive_info=False,
        )
        result = mask_case_sensitive_info(self.case)
        self.assertEqual(len(result), 1)
        self.assertNotIn('original', result[0])
        self.assertEqual(result[0]['masked'], '联系电话 138****8000')

    def test_explicit_sensitive_flag_without_regex_match_is_kept_for_manual_review(self):
        Evidence.objects.create(
            case=self.case,
            code='E2',
            evidence_type='实名信息',
            description='姓名张三',
            source_time=timezone.now(),
            has_sensitive_info=True,
        )
        result = mask_case_sensitive_info(self.case)
        self.assertEqual(result[0]['type'], 'unknown')
        self.assertEqual(result[0]['masked'], '姓名张三')
