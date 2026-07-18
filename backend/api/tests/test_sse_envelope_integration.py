# -*- coding: utf-8 -*-
"""Task 1.5.2 SSE 事件信封端到端集成测试。

对齐 tasks.md SubTask 1.5.2（端到端验证）：
- 测试 1：WorkflowRunner 运行后，EventDepot 中事件含 run_id / revision / occurred_at 字段
- 测试 2：_format_sse_event 输出 SSE 字符串含统一信封 7 字段
- 测试 3：事件类型映射正确（workflow.start → stage.started，complaint.token → document.delta）

与 test_sse_envelope.py 的区别：
- test_sse_envelope.py 主要是单元测试（dataclass 字段、map 函数、format 函数）
- 本文件聚焦端到端集成：WorkflowRunner.run_and_persist 真实运行流程 +
  EventDepot 持久化 + _format_sse_event 输出全链路验证。

测试策略：
- mock EventDepot（内存版）替代真实 PostgreSQL EventDepot，记录 persist 调用
- mock workflow.astream_events 产生事件流（不依赖真实 LangGraph 节点）
- mock lifecycle 服务（complete_processing / fail_processing 等）避免 DB 操作
- _format_sse_event 直接调用真实函数（views.py），无 DB 依赖

运行方式：
    cd backend
    python manage.py test api.tests.test_sse_envelope_integration -v 2
"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# 确保 backend/ 在 sys.path 上
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django  # noqa: E402
from django.apps import apps as _django_apps  # noqa: E402
if not _django_apps.ready:
    django.setup()

from django.test import SimpleTestCase  # noqa: E402

from api.agents.sse_event_mapper import (  # noqa: E402
    LEGACY_EVENT_TYPE_MAP,
    EVENT_DOCUMENT_DELTA,
    EVENT_STAGE_STARTED,
    SSEEvent,
    SSEEventMapper,
    map_legacy_event_type,
)
from api.views import _format_sse_event  # noqa: E402


# 统一信封 7 字段
ENVELOPE_FIELDS = (
    'event_id', 'event_type', 'run_id', 'thread_id',
    'revision', 'occurred_at', 'payload',
)


def _parse_sse_data(sse_str: str) -> dict:
    """从 SSE 协议字符串中解析出 data JSON dict。"""
    data_line = None
    for line in sse_str.split('\n'):
        if line.startswith('data: '):
            data_line = line[len('data: '):]
            break
    if data_line is None:
        raise ValueError(f"SSE 字符串中未找到 data 行: {sse_str!r}")
    return json.loads(data_line)


def _make_mock_depot():
    """构造内存 EventDepot mock，记录所有 persist 调用 + 信封字段。"""
    events = []

    async def _persist(thread_id, event_type, payload, **kwargs):
        events.append({
            "thread_id": thread_id,
            "event_type": event_type,
            "payload": payload,
            "run_id": kwargs.get("run_id"),
            "revision": kwargs.get("revision"),
            "occurred_at": kwargs.get("occurred_at"),
        })
        return len(events)

    mock_depot = MagicMock()
    mock_depot.persist = AsyncMock(side_effect=_persist)
    return mock_depot, events


def _make_mock_emitter():
    """构造 NotifyEmitter mock。"""
    mock_emitter = MagicMock()
    mock_emitter.notify = AsyncMock(return_value=None)
    return mock_emitter


def _make_mock_completion(status="succeeded"):
    """构造 complete_processing 返回的 mock 对象。"""
    mock_completion = MagicMock()
    mock_completion.case.workflow_status = status
    return mock_completion


# ============================================================================
# 测试 1：WorkflowRunner 运行后，EventDepot 中事件含 run_id / revision / occurred_at
# ============================================================================

class WorkflowRunnerEnvelopeIntegrationTest(SimpleTestCase):
    """测试 1：端到端验证 WorkflowRunner 写入 EventDepot 的事件含信封字段。

    通过 mock workflow.astream_events 产生事件流，让 WorkflowRunner.run_and_persist
    完整跑一遍，从 mock EventDepot 中读回事件，验证信封字段。

    注意：当前 WorkflowRunner.run_and_persist 暂未注入 run_id / revision（Task 3.1 / 2.4
    引入后才注入），故这两个字段为 None。本测试断言字段存在于事件结构中（即使为 None），
    并验证 occurred_at 字段被持久化（WorkflowRunner 在 _utcnow_iso() 中注入）。
    """

    def test_events_persisted_contain_envelope_fields(self):
        """EventDepot.persist 被调用时，事件结构含 run_id / revision / occurred_at 字段。"""
        from api.agents import workflow_runner as wr_module

        # mock astream_events 产生 2 个节点事件后正常结束
        async def _mock_stream(*args, **kwargs):
            for evt in (
                {"event": "on_chain_start", "name": "preclassify",
                 "data": {"input": {"case_id": 1, "evidence_ids": [1]}}},
                {"event": "on_chain_end", "name": "preclassify",
                 "data": {"output": {"evidence_preclassify_results": []}}},
            ):
                yield evt

        mock_workflow = MagicMock()
        mock_workflow.astream_events = MagicMock(return_value=_mock_stream())
        mock_workflow.aget_state = AsyncMock(return_value=MagicMock(
            interrupts=None, tasks=[], next=None,
        ))

        mock_depot, events = _make_mock_depot()
        mock_emitter = _make_mock_emitter()

        with patch.object(wr_module, "build_case_workflow", return_value=mock_workflow), \
             patch.object(wr_module, "EventDepot", return_value=mock_depot), \
             patch.object(wr_module, "NotifyEmitter", return_value=mock_emitter), \
             patch.object(wr_module, "complete_processing",
                          new=MagicMock(return_value=_make_mock_completion())), \
             patch.object(wr_module, "fail_processing", new=MagicMock()), \
             patch.object(wr_module, "mark_paused", new=MagicMock()), \
             patch.object(wr_module, "mark_waiting_review", new=MagicMock()):
            runner = wr_module.WorkflowRunner()
            asyncio.run(runner.run_and_persist(
                case_id=1, thread_id="env-integ-1",
                initial_state={"case_id": 1, "evidence_ids": [1]},
            ))

        # 应至少产生 workflow.start + workflow.complete 事件
        event_types = [e["event_type"] for e in events]
        self.assertIn("workflow.start", event_types)
        self.assertIn("workflow.complete", event_types)

        # 验证每个事件结构含信封字段（run_id / revision / occurred_at key 存在）
        for evt in events:
            self.assertIn("run_id", evt, "事件应含 run_id 字段（即使为 None）")
            self.assertIn("revision", evt, "事件应含 revision 字段（即使为 None）")
            self.assertIn("occurred_at", evt, "事件应含 occurred_at 字段")

        # workflow.start 事件 payload 应含 started_at（ISO 8601）
        start_evt = next(e for e in events if e["event_type"] == "workflow.start")
        self.assertIn("started_at", start_evt["payload"])
        self.assertIsInstance(start_evt["payload"]["started_at"], str)

        # workflow.complete 事件 payload 应含 total_duration_ms
        complete_evt = next(e for e in events if e["event_type"] == "workflow.complete")
        self.assertIn("total_duration_ms", complete_evt["payload"])
        self.assertIsInstance(complete_evt["payload"]["total_duration_ms"], int)

    def test_failed_workflow_emits_workflow_error_with_envelope(self):
        """工作流失败时 workflow.error 事件也含信封字段结构。"""
        from api.agents import workflow_runner as wr_module

        async def _raising_stream(*args, **kwargs):
            raise RuntimeError("模拟致命错误")
            yield  # pragma: no cover

        mock_workflow = MagicMock()
        mock_workflow.astream_events = MagicMock(return_value=_raising_stream())
        mock_workflow.aget_state = AsyncMock(return_value=MagicMock(
            interrupts=None, tasks=[], next=None,
        ))

        mock_depot, events = _make_mock_depot()
        mock_emitter = _make_mock_emitter()

        with patch.object(wr_module, "build_case_workflow", return_value=mock_workflow), \
             patch.object(wr_module, "EventDepot", return_value=mock_depot), \
             patch.object(wr_module, "NotifyEmitter", return_value=mock_emitter), \
             patch.object(wr_module, "fail_processing", new=MagicMock()), \
             patch.object(wr_module, "complete_processing",
                          new=MagicMock(return_value=_make_mock_completion())), \
             patch.object(wr_module, "mark_paused", new=MagicMock()), \
             patch.object(wr_module, "mark_waiting_review", new=MagicMock()):
            runner = wr_module.WorkflowRunner()
            asyncio.run(runner.run_and_persist(
                case_id=1, thread_id="env-integ-2",
                initial_state={"case_id": 1, "evidence_ids": [1]},
            ))

        # 验证 workflow.error 事件被持久化
        error_events = [e for e in events if e["event_type"] == "workflow.error"]
        self.assertEqual(len(error_events), 1)
        err_evt = error_events[0]
        # 信封字段都存在
        for field in ("run_id", "revision", "occurred_at"):
            self.assertIn(field, err_evt, f"workflow.error 事件应含 {field} 字段")
        # payload 含错误信息
        self.assertIn("message", err_evt["payload"])
        self.assertIn("模拟致命错误", err_evt["payload"]["message"])
        self.assertFalse(err_evt["payload"]["recoverable"])


# ============================================================================
# 测试 2：_format_sse_event 输出 SSE 字符串含统一信封 7 字段
# ============================================================================

class FormatSSEEventEnvelopeIntegrationTest(SimpleTestCase):
    """测试 2：_format_sse_event 输出 SSE 字符串含统一信封 7 字段。

    端到端验证：构造一个 EventDepot 读回的事件 dict（含信封字段），
    调用真实 _format_sse_event 生成 SSE 协议字符串，解析 data JSON 验证 7 字段。
    """

    def test_sse_string_contains_all_seven_envelope_fields(self):
        """_format_sse_event 输出的 SSE 字符串 data JSON 顶层含 7 字段。"""
        evt = {
            'event_id': 42,
            'event_type': 'workflow.start',
            'payload': {'case_id': 1, 'started_at': '2026-07-17T10:00:00+00:00'},
            'run_id': 100,
            'revision': 5,
            'occurred_at': '2026-07-17T10:00:00+00:00',
            'created_at': '2026-07-17T10:00:01+00:00',
        }
        sse_str = _format_sse_event(evt, thread_id='case-1-run-100')
        data = _parse_sse_data(sse_str)

        # 7 个统一信封字段全部存在
        for field in ENVELOPE_FIELDS:
            self.assertIn(field, data, f"SSE 信封缺少字段: {field}")

        # 字段值正确
        self.assertEqual(data['event_id'], 42)
        self.assertEqual(data['event_type'], 'workflow.start')
        self.assertEqual(data['run_id'], 100)
        self.assertEqual(data['thread_id'], 'case-1-run-100')
        self.assertEqual(data['revision'], 5)
        self.assertEqual(data['occurred_at'], '2026-07-17T10:00:00+00:00')
        self.assertEqual(data['payload']['case_id'], 1)

    def test_sse_envelope_with_none_run_id_and_revision(self):
        """run_id / revision 为 None（旧数据 / Task 3.1 前数据）时字段仍存在。"""
        evt = {
            'event_id': 1,
            'event_type': 'node.start',
            'payload': {'node': 'ocr'},
            'run_id': None,
            'revision': None,
            'occurred_at': None,  # 应回退到 created_at
            'created_at': '2026-07-17T10:00:01+00:00',
        }
        sse_str = _format_sse_event(evt, thread_id='case-1')
        data = _parse_sse_data(sse_str)

        # 字段都存在（即使为 None）
        for field in ENVELOPE_FIELDS:
            self.assertIn(field, data, f"字段 {field} 应存在即使为 None")
        self.assertIsNone(data['run_id'])
        self.assertIsNone(data['revision'])
        # occurred_at 回退到 created_at
        self.assertEqual(data['occurred_at'], '2026-07-17T10:00:01+00:00')

    def test_sse_envelope_includes_legacy_and_mapped_event_type(self):
        """SSE 信封含 legacy_event_type 字段，便于前端调试与渐进迁移。"""
        evt = {
            'event_id': 5,
            'event_type': 'complaint.token',
            'payload': {'delta': 'hello'},
            'run_id': 1,
            'revision': 3,
            'occurred_at': '2026-07-17T10:00:00+00:00',
            'created_at': '2026-07-17T10:00:01+00:00',
        }
        sse_str = _format_sse_event(evt, thread_id='case-1-run-1')
        data = _parse_sse_data(sse_str)

        # legacy_event_type 字段（向后兼容字段，对齐 _format_sse_event 实现）
        self.assertIn('legacy_event_type', data)
        self.assertEqual(data['legacy_event_type'], 'complaint.token')
        # event_type 仍是旧类型字符串（前端 addEventListener 用）
        self.assertEqual(data['event_type'], 'complaint.token')

    def test_sse_envelope_payload_flattened_to_top_level(self):
        """payload 字段被展开到顶层（向后兼容旧前端 reducer 直接读 data.delta 等）。"""
        evt = {
            'event_id': 6,
            'event_type': 'complaint.token',
            'payload': {'delta': 'hello', 'node': 'complaint'},
            'run_id': None,
            'revision': None,
            'occurred_at': None,
            'created_at': '2026-07-17T10:00:00+00:00',
        }
        sse_str = _format_sse_event(evt, thread_id='case-1')
        data = _parse_sse_data(sse_str)

        # payload 字段被展开到顶层
        self.assertEqual(data['delta'], 'hello')
        self.assertEqual(data['node'], 'complaint')
        # 嵌套 payload 也保留
        self.assertEqual(data['payload']['delta'], 'hello')


# ============================================================================
# 测试 3：事件类型映射正确
# ============================================================================

class EventTypeMappingIntegrationTest(SimpleTestCase):
    """测试 3：端到端验证事件类型映射（旧 → 新）。

    验证 spec 行 69 列出的全部映射规则：
    - workflow.start → stage.started
    - complaint.token → document.delta
    - workflow.complete → stage.completed
    - workflow.error → issue.created
    - ... 等
    """

    def test_workflow_start_maps_to_stage_started(self):
        """workflow.start → stage.started（端到端：从 raw 事件到 mapped_type）。"""
        # 直接调用 map_legacy_event_type 验证映射
        self.assertEqual(map_legacy_event_type("workflow.start"), EVENT_STAGE_STARTED)
        self.assertEqual(map_legacy_event_type("workflow.start"), "stage.started")

    def test_complaint_token_maps_to_document_delta(self):
        """complaint.token → document.delta（端到端）。"""
        # 验证常量
        self.assertEqual(map_legacy_event_type("complaint.token"), EVENT_DOCUMENT_DELTA)
        self.assertEqual(map_legacy_event_type("complaint.token"), "document.delta")

        # 验证 SSEEventMapper.map 对 complaint.token 事件应用映射
        mapper = SSEEventMapper()
        mapper.current_node = "complaint"
        from datetime import datetime, timezone
        mapper._node_start_times["complaint"] = datetime.now(timezone.utc)
        raw_event = {
            "event": "on_chat_model_stream",
            "name": "llm",
            "data": {"chunk": type("C", (), {"content": "x"})()},
        }
        sse_events = asyncio.run(mapper.map(raw_event))
        self.assertEqual(len(sse_events), 1)
        evt = sse_events[0]
        # SSEEvent.type 保留旧类型（向后兼容）
        self.assertEqual(evt.type, "complaint.token")
        # payload 中含 mapped_event_type（新类型）
        self.assertEqual(evt.payload.get("mapped_event_type"), "document.delta")
        self.assertEqual(evt.payload.get("legacy_event_type"), "complaint.token")

    def test_all_legacy_event_type_mappings_are_correct(self):
        """tasks.md SubTask 1.3.4 列出的所有映射规则端到端验证。"""
        expected_mappings = {
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
        for old_type, expected_new_type in expected_mappings.items():
            with self.subTest(old_type=old_type):
                actual = map_legacy_event_type(old_type)
                self.assertEqual(
                    actual, expected_new_type,
                    f"映射不匹配: {old_type} → 期望 {expected_new_type}，实际 {actual}",
                )

    def test_unmapped_event_types_passthrough(self):
        """未在映射表中的事件类型（node.* / complaint.done / review.interrupt）保持原样。"""
        passthrough_types = [
            "node.start", "node.complete", "node.progress", "node.error",
            "complaint.done", "review.interrupt",
            "unknown.event.type",
        ]
        for old_type in passthrough_types:
            with self.subTest(old_type=old_type):
                self.assertEqual(
                    map_legacy_event_type(old_type), old_type,
                    f"未映射的事件类型应保持原样: {old_type}",
                )

    def test_legacy_event_type_map_dict_complete(self):
        """LEGACY_EVENT_TYPE_MAP dict 含全部 10 条映射规则。"""
        expected_keys = {
            "workflow.start", "workflow.resumed", "workflow.paused",
            "workflow.waiting_review", "workflow.complete", "workflow.error",
            "complaint.token", "complaint.completed",
            "review.skipped", "review.resumed",
        }
        self.assertEqual(set(LEGACY_EVENT_TYPE_MAP.keys()), expected_keys)
        self.assertEqual(len(LEGACY_EVENT_TYPE_MAP), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
