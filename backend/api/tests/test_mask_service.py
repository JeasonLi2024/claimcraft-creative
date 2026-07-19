from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.models import (
    Case,
    ComplaintTemplate,
    Evidence,
    ExtractedField,
    TimelineNode,
)
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

    def test_description_item_carries_source_metadata_and_risk_level(self):
        Evidence.objects.create(
            case=self.case,
            code='E1',
            evidence_type='实名信息',
            description='身份证 130101199003078888',
            source_time=timezone.now(),
        )
        item = mask_case_sensitive_info(self.case)[0]
        self.assertEqual(item['source_type'], 'evidence')
        self.assertEqual(item['type'], 'id_card')
        self.assertEqual(item['risk_level'], 'high')
        self.assertIn('E1', item['source_label'])


class MaskCaseMultiSourceTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='multi-source-owner')
        self.case = Case.objects.create(title='多来源脱敏', owner=user)
        self.evidence = Evidence.objects.create(
            case=self.case,
            code='E1',
            evidence_type='聊天记录',
            description='无敏感描述',
            extracted_text='联系电话 13800138000',
            source_time=timezone.now(),
        )

    def _by_source(self, results):
        return {item['source_type'] for item in results}

    def test_scans_ocr_extracted_field_timeline_and_document(self):
        ExtractedField.objects.create(
            evidence=self.evidence,
            field_name='收件人电话',
            field_value='13900139000',
            confidence=0.9,
        )
        TimelineNode.objects.create(
            case=self.case,
            datetime=timezone.now(),
            event='买家身份证 130101199003078888 已核验',
            order=0,
            category='其他',
            auto_generated=True,
        )
        ComplaintTemplate.objects.create(
            case=self.case,
            template_type=ComplaintTemplate.PLATFORM,
            title='投诉书',
            content='投诉人手机号 13700137000，请依法处理。',
        )
        results = mask_case_sensitive_info(self.case)
        sources = self._by_source(results)
        self.assertIn('ocr', sources)
        self.assertIn('extracted_field', sources)
        self.assertIn('timeline', sources)
        self.assertIn('document', sources)
        # 时间线里的身份证应判为高风险
        timeline_item = next(i for i in results if i['source_type'] == 'timeline')
        self.assertEqual(timeline_item['risk_level'], 'high')
        # 不下发原文
        self.assertTrue(all('original' not in i for i in results))

    def test_same_value_within_evidence_is_deduped(self):
        # 描述与 OCR 文本命中同一手机号 → 只保留一项
        self.evidence.description = '电话 13800138000'
        self.evidence.save(update_fields=['description'])
        results = mask_case_sensitive_info(self.case)
        phone_items = [
            i for i in results
            if i.get('evidence_code') == 'E1' and i['type'] == 'phone'
        ]
        self.assertEqual(len(phone_items), 1)

    def test_include_original_passes_through_raw(self):
        results = mask_case_sensitive_info(self.case, include_original=True)
        ocr_item = next(i for i in results if i['source_type'] == 'ocr')
        self.assertEqual(ocr_item['original'], '联系电话 13800138000')
