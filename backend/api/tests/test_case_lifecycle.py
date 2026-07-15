from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Case, CaseStatusLog, ComplaintTemplate, Evidence
from api.services.case_lifecycle_service import (
    LifecycleError,
    archive_case,
    complete_processing,
    fail_processing,
    get_case_progress,
    mark_waiting_review,
    start_processing,
)


class CaseLifecycleServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = Case.objects.create(title='测试案件', owner=self.user)

    def refresh_case(self):
        return Case.objects.get(pk=self.case.pk)

    def test_workflow_start_moves_draft_to_processing_idempotently(self):
        first = start_processing(
            self.case.pk, actor=self.user, thread_id='thread-1'
        )
        second = start_processing(
            self.case.pk, actor=self.user, thread_id='thread-2'
        )

        case = self.refresh_case()
        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(case.status, 'processing')
        self.assertEqual(case.workflow_status, 'running')
        self.assertEqual(case.workflow_revision, 2)
        self.assertEqual(CaseStatusLog.objects.count(), 1)
        self.assertEqual(CaseStatusLog.objects.get().trigger, 'workflow_started')

    def test_waiting_review_does_not_submit_case(self):
        start_processing(self.case.pk, actor=self.user, thread_id='thread-1')
        mark_waiting_review(self.case.pk)

        case = self.refresh_case()
        self.assertEqual(case.status, 'processing')
        self.assertEqual(case.workflow_status, 'waiting_review')

    def test_complete_requires_valid_document(self):
        start_processing(self.case.pk, actor=self.user, thread_id='thread-1')

        result = complete_processing(self.case.pk, thread_id='thread-1')

        case = self.refresh_case()
        self.assertFalse(result.changed)
        self.assertEqual(case.status, 'processing')
        self.assertEqual(case.workflow_status, 'failed')

    def test_valid_document_submits_case(self):
        start_processing(self.case.pk, actor=self.user, thread_id='thread-1')
        ComplaintTemplate.objects.create(
            case=self.case,
            template_type='platform',
            title='投诉书',
            content='这是一份有效的投诉文稿。',
        )

        result = complete_processing(self.case.pk, thread_id='thread-1')

        case = self.refresh_case()
        self.assertTrue(result.changed)
        self.assertEqual(case.status, 'submitted')
        self.assertEqual(case.workflow_status, 'succeeded')
        log = CaseStatusLog.objects.latest('created_at')
        self.assertEqual(log.trigger, 'document_generated')
        self.assertEqual(log.thread_id, 'thread-1')

    def test_archive_blocks_unmasked_sensitive_image(self):
        start_processing(self.case.pk, actor=self.user, thread_id='thread-1')
        ComplaintTemplate.objects.create(
            case=self.case, template_type='platform', title='投诉书', content='有效内容'
        )
        complete_processing(self.case.pk, thread_id='thread-1')
        Evidence.objects.create(
            case=self.case,
            code='E1',
            evidence_type='订单页',
            description='敏感订单',
            source_time=timezone.now(),
            has_sensitive_info=True,
            image='evidences/example.png',
            mask_status='none',
        )

        with self.assertRaises(LifecycleError):
            archive_case(self.case.pk, actor=self.user)

    def test_archive_closes_deliverable_case(self):
        start_processing(self.case.pk, actor=self.user, thread_id='thread-1')
        ComplaintTemplate.objects.create(
            case=self.case, template_type='platform', title='投诉书', content='有效内容'
        )
        complete_processing(self.case.pk, thread_id='thread-1')

        archive_case(self.case.pk, actor=self.user)

        case = self.refresh_case()
        self.assertEqual(case.status, 'closed')
        self.assertIsNotNone(case.archived_at)
        self.assertEqual(CaseStatusLog.objects.latest('created_at').trigger, 'user_archived')

    def test_progress_recommends_upload_for_new_case(self):
        progress = get_case_progress(self.case)
        self.assertEqual(progress['next_action'], 'upload_evidence')
        self.assertFalse(progress['can_archive'])

    def test_failure_keeps_lifecycle_processing(self):
        start_processing(self.case.pk, actor=self.user, thread_id='thread-1')
        fail_processing(self.case.pk, '模型服务不可用')

        case = self.refresh_case()
        self.assertEqual(case.status, 'processing')
        self.assertEqual(case.workflow_status, 'failed')
        self.assertEqual(case.workflow_error, '模型服务不可用')


class CaseLifecycleAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.other = User.objects.create_user(username='other', password='pass')
        self.case = Case.objects.create(title='接口测试案件', owner=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_normal_user_cannot_choose_status(self):
        response = self.client.post(
            f'/api/cases/{self.case.pk}/status/transition/',
            {'to_status': 'processing'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cancel_is_business_action_and_is_owner_scoped(self):
        response = self.client.post(
            f'/api/cases/{self.case.pk}/cancel/',
            {'reason': '不再处理'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['status'], 'cancelled')
        self.assertEqual(CaseStatusLog.objects.get().trigger, 'user_cancelled')

        other_case = Case.objects.create(title='他人案件', owner=self.other)
        response = self.client.post(f'/api/cases/{other_case.pk}/cancel/', format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
