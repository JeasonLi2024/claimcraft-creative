# -*- coding: utf-8 -*-
"""Task 3.4.2 测试：Case.workflow_status 枚举映射。"""
from django.test import TestCase
from api.services.case_lifecycle_service import (
    map_workflow_status_to_legacy,
    map_legacy_status_to_new,
)


class WorkflowStatusMappingTests(TestCase):
    def test_legacy_to_new_status_mapping(self):
        """旧 → 新状态映射。"""
        self.assertEqual(map_legacy_status_to_new('idle'), 'idle')
        self.assertEqual(map_legacy_status_to_new('running'), 'running')
        self.assertEqual(map_legacy_status_to_new('pausing'), 'pausing')
        self.assertEqual(map_legacy_status_to_new('paused'), 'waiting_user')
        self.assertEqual(map_legacy_status_to_new('waiting_review'), 'waiting_user')
        self.assertEqual(map_legacy_status_to_new('succeeded'), 'succeeded')
        self.assertEqual(map_legacy_status_to_new('failed'), 'failed')

    def test_new_to_legacy_status_default_mapping(self):
        """新 → 旧状态映射（默认）。"""
        self.assertEqual(map_workflow_status_to_legacy('idle'), 'idle')
        self.assertEqual(map_workflow_status_to_legacy('queued'), 'idle')
        self.assertEqual(map_workflow_status_to_legacy('running'), 'running')
        self.assertEqual(map_workflow_status_to_legacy('pausing'), 'pausing')
        self.assertEqual(map_workflow_status_to_legacy('waiting_user'), 'paused')
        self.assertEqual(map_workflow_status_to_legacy('succeeded'), 'succeeded')
        self.assertEqual(map_workflow_status_to_legacy('failed'), 'failed')
        self.assertEqual(map_workflow_status_to_legacy('cancelled'), 'failed')

    def test_new_to_legacy_with_intervention_type(self):
        """waiting_user 根据 intervention_type 区分 paused / waiting_review。"""
        self.assertEqual(
            map_workflow_status_to_legacy('waiting_user', 'user_pause'),
            'paused'
        )
        self.assertEqual(
            map_workflow_status_to_legacy('waiting_user', 'quality_review'),
            'waiting_review'
        )
        self.assertEqual(
            map_workflow_status_to_legacy('waiting_user', None),
            'paused'  # 默认
        )

    def test_round_trip_mapping(self):
        """旧 → 新 → 旧 往返映射一致（waiting_review / paused 都映射到 waiting_user 再回退）。"""
        # waiting_review → waiting_user → waiting_review (with intervention_type=quality_review)
        new = map_legacy_status_to_new('waiting_review')
        self.assertEqual(new, 'waiting_user')
        legacy = map_workflow_status_to_legacy(new, intervention_type='quality_review')
        self.assertEqual(legacy, 'waiting_review')

        # paused → waiting_user → paused (with intervention_type=user_pause)
        new = map_legacy_status_to_new('paused')
        self.assertEqual(new, 'waiting_user')
        legacy = map_workflow_status_to_legacy(new, intervention_type='user_pause')
        self.assertEqual(legacy, 'paused')
