# -*- coding: utf-8 -*-
"""Task 1.3: SSE 事件信封升级单元测试。

测试覆盖（对齐 SubTask 1.3.1 ~ 1.3.4 + tasks.md SubTask 1.5.2）：
1. SSEEvent dataclass 含 run_id / revision / occurred_at 字段（默认 None）
2. _format_sse_event 返回的 SSE 字符串中 data JSON 含 7 个统一信封字段
3. map_legacy_event_type("workflow.start") 返回 "stage.started"
4. map_legacy_event_type("complaint.token") 返回 "document.delta"
5. map_legacy_event_type("unknown.event") 返回 "unknown.event"（保持原样）
6. （如 DB 可运行）EventDepot.persist(..., run_id=1, revision=5, occurred_at="...")
   成功写入并能在 get_all_events 中读回信封字段

运行方式（任选其一）：
    cd backend
    python manage.py test api.tests.test_sse_envelope -v 2
    # 或（如已安装 pytest）：
    python -m pytest api/tests/test_sse_envelope.py -v
"""
import json
import os
import sys
import unittest

# 确保可从项目根目录或 backend/ 目录运行（backend/ 需在 sys.path 上以解析 claimcraft.settings）
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django  # noqa: E402
from django.apps import apps as _django_apps  # noqa: E402
if not _django_apps.ready:
    django.setup()

from api.agents.sse_event_mapper import (  # noqa: E402
    EVENT_ARTIFACT_CREATED,
    EVENT_ARTIFACT_STALE,
    EVENT_ARTIFACT_UPDATED,
    EVENT_DOCUMENT_COMPLETED,
    EVENT_DOCUMENT_DELTA,
    EVENT_INTERVENTION_CANCELLED,
    EVENT_INTERVENTION_CREATED,
    EVENT_INTERVENTION_SUBMITTED,
    EVENT_ISSUE_CREATED,
    EVENT_ISSUE_RESOLVED,
    EVENT_STAGE_COMPLETED,
    EVENT_STAGE_PROGRESS,
    EVENT_STAGE_QUALITY_CHANGED,
    EVENT_STAGE_STARTED,
    LEGACY_EVENT_TYPE_MAP,
    SSEEvent,
    map_legacy_event_type,
)
from api.views import _format_sse_event  # noqa: E402


# 统一信封 7 字段
ENVELOPE_FIELDS = {
    'event_id', 'event_type', 'run_id', 'thread_id',
    'revision', 'occurred_at', 'payload',
}


def _parse_sse_data(sse_str: str) -> dict:
    """从 SSE 协议字符串中解析出 data JSON dict。

    SSE 格式：event: {type}\nid: {event_id}\ndata: {json}\n\n
    """
    data_line = None
    for line in sse_str.split('\n'):
        if line.startswith('data: '):
            data_line = line[len('data: '):]
            break
    if data_line is None:
        raise ValueError(f"SSE 字符串中未找到 data 行: {sse_str!r}")
    return json.loads(data_line)


class SSEEventDataclassTest(unittest.TestCase):
    """测试 1: SSEEvent dataclass 含 run_id / revision / occurred_at 字段（默认 None）。"""

    def test_default_fields_are_none(self):
        """新字段默认 None，保持向后兼容（旧调用方不传新字段也能用）。"""
        evt = SSEEvent(type="node.start", payload={"node": "ocr"})
        self.assertIsNone(evt.run_id)
        self.assertIsNone(evt.revision)
        self.assertIsNone(evt.occurred_at)

    def test_fields_assignable(self):
        """新字段可被显式赋值。"""
        evt = SSEEvent(
            type="stage.started",
            payload={"case_id": 1},
            run_id=42,
            revision=5,
            occurred_at="2026-07-17T10:00:00+00:00",
        )
        self.assertEqual(evt.run_id, 42)
        self.assertEqual(evt.revision, 5)
        self.assertEqual(evt.occurred_at, "2026-07-17T10:00:00+00:00")

    def test_old_callers_still_work(self):
        """旧调用方仅传 type + payload 仍可正常构造（向后兼容）。"""
        evt = SSEEvent(type="complaint.token", payload={"delta": "hello"})
        self.assertEqual(evt.type, "complaint.token")
        self.assertEqual(evt.payload, {"delta": "hello"})


class FormatSSEEventEnvelopeTest(unittest.TestCase):
    """测试 2: _format_sse_event 返回 SSE 字符串中 data JSON 含 7 个统一信封字段。"""

    def test_envelope_contains_all_seven_fields(self):
        """_format_sse_event 输出的 data JSON 顶层含 7 个统一信封字段。"""
        evt = {
            'event_id': 7,
            'event_type': 'workflow.start',
            'payload': {'case_id': 1, 'started_at': '2026-07-17T10:00:00+00:00'},
            'run_id': None,
            'revision': None,
            'occurred_at': '2026-07-17T10:00:00+00:00',
            'created_at': '2026-07-17T10:00:01+00:00',
        }
        sse_str = _format_sse_event(evt, thread_id='case-1-run-1')
        data = _parse_sse_data(sse_str)

        # 7 个统一信封字段全部存在
        for field in ENVELOPE_FIELDS:
            self.assertIn(field, data, f"信封缺少字段: {field}")

        # 字段值正确
        self.assertEqual(data['event_id'], 7)
        self.assertEqual(data['event_type'], 'workflow.start')
        self.assertIsNone(data['run_id'])
        self.assertEqual(data['thread_id'], 'case-1-run-1')
        self.assertIsNone(data['revision'])
        self.assertEqual(data['occurred_at'], '2026-07-17T10:00:00+00:00')
        self.assertEqual(data['payload']['case_id'], 1)

    def test_envelope_fallback_occurred_at_to_created_at(self):
        """occurred_at 缺失时回退到 created_at（向后兼容旧数据）。"""
        evt = {
            'event_id': 1,
            'event_type': 'node.start',
            'payload': {'node': 'ocr'},
            'run_id': None,
            'revision': None,
            'occurred_at': None,  # 旧数据无此字段
            'created_at': '2026-07-17T10:00:01+00:00',
        }
        sse_str = _format_sse_event(evt, thread_id='case-1')
        data = _parse_sse_data(sse_str)
        self.assertEqual(data['occurred_at'], '2026-07-17T10:00:01+00:00')

    def test_envelope_backward_compat_flattened_payload(self):
        """向后兼容：payload 字段展开到顶层，旧前端 reducer 可直接读 data.node 等。"""
        evt = {
            'event_id': 2,
            'event_type': 'node.complete',
            'payload': {'node': 'ocr', 'duration_ms': 120},
            'run_id': None,
            'revision': None,
            'occurred_at': None,
            'created_at': '2026-07-17T10:00:05+00:00',
        }
        sse_str = _format_sse_event(evt, thread_id='case-1')
        data = _parse_sse_data(sse_str)
        # 扁平字段保留
        self.assertEqual(data['node'], 'ocr')
        self.assertEqual(data['duration_ms'], 120)
        # 嵌套 payload 字段也存在
        self.assertEqual(data['payload']['node'], 'ocr')

    def test_envelope_legacy_event_type_field(self):
        """信封含 legacy_event_type 字段供调试（值与 event_type 一致，保留旧类型）。"""
        evt = {
            'event_id': 3,
            'event_type': 'workflow.complete',
            'payload': {'total_duration_ms': 5000},
            'run_id': None,
            'revision': None,
            'occurred_at': None,
            'created_at': '2026-07-17T10:01:00+00:00',
        }
        sse_str = _format_sse_event(evt, thread_id='case-1')
        data = _parse_sse_data(sse_str)
        self.assertEqual(data['event_type'], 'workflow.complete')
        self.assertEqual(data['legacy_event_type'], 'workflow.complete')

    def test_envelope_payload_key_does_not_overwrite_envelope(self):
        """payload 中的 key 与信封字段同名时不覆盖信封字段。"""
        evt = {
            'event_id': 4,
            'event_type': 'node.start',
            'payload': {'event_id': 999, 'event_type': 'fake'},  # 同名 key
            'run_id': None,
            'revision': None,
            'occurred_at': None,
            'created_at': '2026-07-17T10:00:00+00:00',
        }
        sse_str = _format_sse_event(evt, thread_id='case-1')
        data = _parse_sse_data(sse_str)
        # 信封字段不被 payload 同名 key 覆盖
        self.assertEqual(data['event_id'], 4)
        self.assertEqual(data['event_type'], 'node.start')
        # 但嵌套 payload 保留原值
        self.assertEqual(data['payload']['event_id'], 999)


class MapLegacyEventTypeTest(unittest.TestCase):
    """测试 3-5: map_legacy_event_type 映射函数行为。"""

    def test_workflow_start_maps_to_stage_started(self):
        """测试 3: workflow.start → stage.started。"""
        self.assertEqual(map_legacy_event_type("workflow.start"), "stage.started")

    def test_complaint_token_maps_to_document_delta(self):
        """测试 4: complaint.token → document.delta。"""
        self.assertEqual(map_legacy_event_type("complaint.token"), "document.delta")

    def test_unknown_event_type_passthrough(self):
        """测试 5: 未知事件类型保持原样（向后兼容）。"""
        self.assertEqual(map_legacy_event_type("unknown.event"), "unknown.event")

    def test_all_documented_legacy_mappings(self):
        """验证 tasks.md 中列出的所有旧→新映射。"""
        expected = {
            "workflow.start": "stage.started",
            "workflow.resumed": "stage.started",
            "workflow.paused": "intervention.created",
            "workflow.waiting_review": "intervention.created",
            "workflow.complete": "stage.completed",
            "workflow.error": "issue.created",
            "complaint.token": "document.delta",
            "complaint.completed": "document.completed",
            "review.skipped": "stage.completed",
            "review.resumed": "intervention.submitted",
        }
        for old_type, new_type in expected.items():
            self.assertEqual(
                map_legacy_event_type(old_type), new_type,
                f"映射不匹配: {old_type} → 期望 {new_type}",
            )

    def test_unmapped_legacy_types_passthrough(self):
        """未在映射表中的旧事件类型（node.* / complaint.done / review.interrupt）保持原样。"""
        for old_type in (
            "node.start", "node.complete", "node.progress", "node.error",
            "complaint.done", "review.interrupt",
        ):
            self.assertEqual(map_legacy_event_type(old_type), old_type)

    def test_legacy_map_dict_matches_constants(self):
        """LEGACY_EVENT_TYPE_MAP 的 value 与事件类型常量一致。"""
        self.assertEqual(LEGACY_EVENT_TYPE_MAP["workflow.start"], EVENT_STAGE_STARTED)
        self.assertEqual(LEGACY_EVENT_TYPE_MAP["workflow.complete"], EVENT_STAGE_COMPLETED)
        self.assertEqual(LEGACY_EVENT_TYPE_MAP["complaint.token"], EVENT_DOCUMENT_DELTA)
        self.assertEqual(LEGACY_EVENT_TYPE_MAP["workflow.error"], EVENT_ISSUE_CREATED)
        self.assertEqual(LEGACY_EVENT_TYPE_MAP["workflow.paused"], EVENT_INTERVENTION_CREATED)
        self.assertEqual(LEGACY_EVENT_TYPE_MAP["review.resumed"], EVENT_INTERVENTION_SUBMITTED)

    def test_all_event_type_constants_defined(self):
        """SubTask 1.3.4: 所有 14 个事件类型常量已定义。"""
        expected_constants = {
            "stage.started", "stage.progress", "stage.completed", "stage.quality_changed",
            "artifact.created", "artifact.updated", "artifact.stale",
            "intervention.created", "intervention.submitted", "intervention.cancelled",
            "document.delta", "document.completed",
            "issue.created", "issue.resolved",
        }
        actual = {
            EVENT_STAGE_STARTED, EVENT_STAGE_PROGRESS, EVENT_STAGE_COMPLETED,
            EVENT_STAGE_QUALITY_CHANGED,
            EVENT_ARTIFACT_CREATED, EVENT_ARTIFACT_UPDATED, EVENT_ARTIFACT_STALE,
            EVENT_INTERVENTION_CREATED, EVENT_INTERVENTION_SUBMITTED,
            EVENT_INTERVENTION_CANCELLED,
            EVENT_DOCUMENT_DELTA, EVENT_DOCUMENT_COMPLETED,
            EVENT_ISSUE_CREATED, EVENT_ISSUE_RESOLVED,
        }
        # 验证 14 个常量全部定义且值匹配预期
        self.assertEqual(len(actual), 14, "应有 14 个事件类型常量")
        self.assertEqual(actual, expected_constants)


class SSEEventMapperEnvelopeTest(unittest.TestCase):
    """验证 SSEEventMapper.map() 对返回的 SSEEvent 应用统一信封字段。"""

    def test_map_applies_envelope_fields(self):
        """map() 返回的 SSEEvent 含 occurred_at 字段（map 后处理填充）。"""
        import asyncio
        from api.agents.sse_event_mapper import SSEEventMapper

        mapper = SSEEventMapper()
        # 构造一个 on_chain_start raw_event 命中 preclassify 节点
        raw_event = {
            "event": "on_chain_start",
            "name": "preclassify",
            "data": {"input": {"case_id": 1, "evidence_ids": [10, 11]}},
        }
        sse_events = asyncio.run(mapper.map(raw_event))

        self.assertEqual(len(sse_events), 1)
        evt = sse_events[0]
        self.assertEqual(evt.type, "node.start")
        # occurred_at 被 _apply_envelope 填充
        self.assertIsNotNone(evt.occurred_at)
        # run_id / revision 保持 None（Task 3.1 / 2.4 引入前）
        self.assertIsNone(evt.run_id)
        self.assertIsNone(evt.revision)

    def test_map_injects_legacy_and_mapped_type_in_payload(self):
        """map() 在 payload 中注入 legacy_event_type + mapped_event_type。"""
        import asyncio
        from api.agents.sse_event_mapper import SSEEventMapper

        mapper = SSEEventMapper()
        # complaint 节点的 on_chat_model_stream → complaint.token
        mapper.current_node = "complaint"
        mapper._node_start_times["complaint"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        raw_event = {
            "event": "on_chat_model_stream",
            "name": "llm",
            "data": {"chunk": type("C", (), {"content": "hello"})()},
        }
        sse_events = asyncio.run(mapper.map(raw_event))
        self.assertEqual(len(sse_events), 1)
        evt = sse_events[0]
        self.assertEqual(evt.type, "complaint.token")  # 旧类型保留
        self.assertEqual(evt.payload.get("legacy_event_type"), "complaint.token")
        self.assertEqual(evt.payload.get("mapped_event_type"), "document.delta")  # 新类型


class EventDepotPersistEnvelopeTest(unittest.TestCase):
    """测试 6: EventDepot.persist 写入 run_id / revision / occurred_at（需 DB）。

    若测试环境无 Postgres 连接（DATABASE_URL 未配置或连不上），自动 skip。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._db_available = cls._check_db_available()

    @staticmethod
    def _check_db_available() -> bool:
        """探测 Postgres 连接是否可用（不可用则 skip 测试 6）。"""
        try:
            from api.agents.sse_event_depot import EventDepot
            depot = EventDepot()
            return True
        except Exception:
            return False

    def setUp(self):
        if not self._db_available:
            self.skipTest("Postgres 不可用，跳过 EventDepot.persist 写入测试")

    def test_persist_with_envelope_fields(self):
        """EventDepot.persist 传入 run_id / revision / occurred_at 成功写入并读回。"""
        import asyncio
        from api.agents.sse_event_depot import EventDepot

        depot = EventDepot()
        thread_id = "test-envelope-{ts}".format(ts=__import__("time").time())
        occurred_at_iso = "2026-07-17T10:00:00+00:00"

        try:
            eid = asyncio.run(depot.persist(
                thread_id,
                "stage.started",
                {"case_id": 999, "message": "envelope test"},
                run_id=1,
                revision=5,
                occurred_at=occurred_at_iso,
            ))
            self.assertIsInstance(eid, int)
            self.assertGreaterEqual(eid, 1)

            # 读回验证
            events = asyncio.run(depot.get_all_events(thread_id))
            self.assertEqual(len(events), 1)
            evt = events[0]
            self.assertEqual(evt['event_type'], "stage.started")
            self.assertEqual(evt['run_id'], 1)
            self.assertEqual(evt['revision'], 5)
            # occurred_at 读回为 ISO 字符串（datetime.isoformat()）
            self.assertIsNotNone(evt['occurred_at'])
            self.assertIn("2026-07-17", evt['occurred_at'])
        finally:
            # 清理测试数据（避免污染）
            try:
                asyncio.run(depot.cleanup_old_events(ttl_hours=0))
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
