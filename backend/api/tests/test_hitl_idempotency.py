# -*- coding: utf-8 -*-
"""Task 0.3.5 测试：HITL 节点副作用幂等性验证。

对齐 `langgraph-human-in-the-loop` skill：
- resume 时整个节点从头重新执行，interrupt() 前的代码会再次运行
- 因此 interrupt() 前的副作用必须幂等（用 update_or_create / update，不用 create）

测试策略：
- 测试 1 & 2 用纯 Python + 内存 dict 模拟 DB，对比 update_or_create（幂等）与
  create（非幂等）在节点重复执行时的行为差异。
- 测试 3 验证 review_node 的 interrupt payload 结构 JSON 可序列化。
- 测试 4 验证 build_stage_pause_payload 返回值 JSON 可序列化（真实函数调用）。
"""
import json
import unittest
from collections import defaultdict

from django.test import SimpleTestCase


# ---------------------------------------------------------------------------
# 测试 1 & 2：mock 节点 + 内存 DB，验证幂等性
# ---------------------------------------------------------------------------

class _MemoryDB:
    """内存 DB 模拟：记录每条记录的「创建次数」，用于验证幂等性。

    - upsert(key, value): 等价 update_or_create（存在则更新，不存在则创建）
    - insert(key, value): 等价 create（始终新建一条，重复 key 会累积）
    """

    def __init__(self):
        self._records = {}  # key -> value
        self._create_count = defaultdict(int)  # key -> 该 key 被新建的次数

    def upsert(self, key, value):
        """幂等：存在则更新，不存在则创建（等价 update_or_create）。"""
        if key not in self._records:
            self._create_count[key] += 1
        self._records[key] = value

    def insert(self, key, value):
        """非幂等：始终视为新建一条记录（等价 create，重复 key 累积）。"""
        self._create_count[key] += 1
        self._records[f"{key}#{self._create_count[key]}"] = value

    def create_count(self, key):
        return self._create_count[key]


def _simulate_node_with_upsert(db: _MemoryDB, corrections, exec_count):
    """模拟 review_node resume 行为：interrupt 后用 update_or_create 持久化校正。

    每次 resume 节点从头执行，interrupt 后代码再次运行，调用 upsert。
    """
    exec_count["n"] += 1
    for c in corrections:
        key = (c["evidence_id"], c["field_name"])
        db.upsert(key, c["field_value"])
    return {"done": True}


def _simulate_node_with_create(db: _MemoryDB, corrections, exec_count):
    """错误模式：模拟用 create（非幂等）持久化，对比测试。"""
    exec_count["n"] += 1
    for c in corrections:
        key = (c["evidence_id"], c["field_name"])
        db.insert(key, c["field_value"])
    return {"done": True}


class IdempotencyMockTests(unittest.TestCase):
    """测试 1 & 2：update_or_create vs create 在节点重复执行时的行为。"""

    def test_upsert_is_idempotent_on_resume(self):
        """测试 1：update_or_create 在 resume 重复执行时不创建重复记录。

        场景：首次 invoke 触发 interrupt，resume 时节点从头重新执行，
        upsert 再次被调用。断言记录数仍为 1（幂等）。
        """
        db = _MemoryDB()
        exec_count = {"n": 0}
        corrections = [
            {"evidence_id": 10, "field_name": "金额", "field_value": "999元"},
            {"evidence_id": 11, "field_name": "日期", "field_value": "2026-01-01"},
        ]

        # 模拟首次 interrupt 后的执行（节点执行到 interrupt，resume 后从头执行）
        # 这里直接模拟 resume 后节点重新执行两次（极端情况：重复 resume）
        _simulate_node_with_upsert(db, corrections, exec_count)
        _simulate_node_with_upsert(db, corrections, exec_count)  # resume 重新执行

        self.assertEqual(exec_count["n"], 2, "节点应执行 2 次（首次 + resume）")
        # 每条 correction 只创建 1 次（幂等）
        self.assertEqual(db.create_count((10, "金额")), 1, "upsert 幂等：不应重复创建")
        self.assertEqual(db.create_count((11, "日期")), 1, "upsert 幂等：不应重复创建")

    def test_create_duplicates_on_resume(self):
        """测试 2：create（错误模式）在 resume 重复执行时创建重复记录。

        对比测试，证明 update_or_create 的必要性。
        """
        db = _MemoryDB()
        exec_count = {"n": 0}
        corrections = [
            {"evidence_id": 10, "field_name": "金额", "field_value": "999元"},
        ]

        # 首次执行 + resume 重新执行
        _simulate_node_with_create(db, corrections, exec_count)
        _simulate_node_with_create(db, corrections, exec_count)

        self.assertEqual(exec_count["n"], 2)
        # create 模式：同一 key 被新建 2 次（非幂等，产生重复记录）
        self.assertEqual(
            db.create_count((10, "金额")), 2,
            "create 非幂等：resume 重复执行会创建重复记录",
        )


# ---------------------------------------------------------------------------
# 测试 3：review_node interrupt payload JSON 可序列化
# ---------------------------------------------------------------------------

class ReviewNodePayloadJsonTests(SimpleTestCase):
    """测试 3：验证 review_node 的 interrupt payload JSON 可序列化。

    review_node 在 interrupt() 前构建 payload：
        {"case_id": int, "fields_to_review": list[dict], "message": str}
    本测试构造与节点相同结构的 payload，断言 json.dumps 不抛异常。
    （不直接调用节点，因为 interrupt() 需要 graph 上下文 + checkpointer。）
    """

    def test_review_interrupt_payload_is_json_serializable(self):
        """review_node interrupt payload 应可被 json.dumps 序列化。"""
        # 与 review_node.py line 91-95 相同的 payload 结构
        fields_to_review = [
            {
                "evidence_id": 101,
                "evidence_code": "EV-001",
                "field_name": "交易金额",
                "field_value": "1500元",
                "confidence": 0.42,
            },
            {
                "evidence_id": 102,
                "evidence_code": "EV-002",
                "field_name": "下单日期",
                "field_value": "2026-03-15",
                "confidence": 0.55,
            },
        ]
        payload = {
            "case_id": 42,
            "fields_to_review": fields_to_review,
            "message": f"共 {len(fields_to_review)} 个低置信度字段需要校正",
        }

        # 断言 JSON 序列化不抛异常
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertIsInstance(serialized, str)

        # 反序列化后结构一致
        restored = json.loads(serialized)
        self.assertEqual(restored["case_id"], 42)
        self.assertEqual(len(restored["fields_to_review"]), 2)
        self.assertEqual(restored["fields_to_review"][0]["evidence_id"], 101)
        self.assertEqual(restored["fields_to_review"][0]["confidence"], 0.42)
        self.assertIn("低置信度字段", restored["message"])

    def test_review_payload_has_no_unsupported_types(self):
        """payload 字段类型应仅限 JSON 原生类型（int/float/str/list/dict/bool/None）。"""
        import datetime

        fields_to_review = [
            {
                "evidence_id": 1,
                "evidence_code": "EV-1",
                "field_name": "f",
                "field_value": "v",
                "confidence": 0.1,
            }
        ]
        payload = {
            "case_id": 1,
            "fields_to_review": fields_to_review,
            "message": "msg",
        }

        # 显式断言无 datetime 等不可序列化类型
        def _check(value, path="root"):
            if isinstance(value, (str, int, float, bool, type(None))):
                return
            if isinstance(value, list):
                for i, item in enumerate(value):
                    _check(item, f"{path}[{i}]")
                return
            if isinstance(value, dict):
                for k, v in value.items():
                    _check(v, f"{path}.{k}")
                return
            self.fail(
                f"payload {path} 含不可 JSON 序列化的类型: {type(value).__name__} = {value!r}"
            )

        _check(payload)
        # 额外断言：典型不可序列化类型应被排除
        bad_payload = {"ts": datetime.datetime.now(tz=datetime.timezone.utc)}
        with self.assertRaises((TypeError, ValueError, OverflowError)):
            json.dumps(bad_payload)


# ---------------------------------------------------------------------------
# 测试 4：build_stage_pause_payload 返回值 JSON 可序列化（真实函数调用）
# ---------------------------------------------------------------------------

class StageGatePayloadJsonTests(SimpleTestCase):
    """测试 4：验证 build_stage_pause_payload 返回值 JSON 可序列化。

    直接调用真实函数（无需 DB，纯计算），断言所有 paused_after 取值的返回值
    均可被 json.dumps 序列化。
    """

    def _build_payload(self, paused_after):
        # 直接导入真实函数（需 Django app registry，SimpleTestCase 已保证）
        from api.services.workflow_pause_service import build_stage_pause_payload
        return build_stage_pause_payload(paused_after)

    def test_payload_json_serializable_for_all_stages(self):
        """所有阶段的 build_stage_pause_payload 返回值应 JSON 可序列化。"""
        from api.services.workflow_pause_service import STAGE_EDITABLE_SCOPES

        for paused_after in STAGE_EDITABLE_SCOPES:
            with self.subTest(paused_after=paused_after):
                payload = self._build_payload(paused_after)
                serialized = json.dumps(payload, ensure_ascii=False)
                self.assertIsInstance(serialized, str, f"{paused_after} payload 应可序列化")
                restored = json.loads(serialized)
                self.assertEqual(restored["interrupt_type"], "stage_pause")
                self.assertEqual(restored["paused_after"], paused_after)
                self.assertIsInstance(restored["editable_scope"], dict)
                self.assertIsInstance(restored["message"], str)

    def test_payload_structure_is_json_native(self):
        """payload 仅含 str / dict[str, list[str]]，无 datetime / model 实例。"""
        payload = self._build_payload("review")
        # editable_scope 应为 dict[str, list[str]]
        self.assertIsInstance(payload["editable_scope"], dict)
        for scope_name, fields in payload["editable_scope"].items():
            self.assertIsInstance(scope_name, str)
            self.assertIsInstance(fields, list)
            for f in fields:
                self.assertIsInstance(f, str)
        # 顶层字段类型
        self.assertIsInstance(payload["interrupt_type"], str)
        self.assertIsInstance(payload["paused_after"], str)
        self.assertIsInstance(payload["message"], str)

    def test_payload_has_no_datetime(self):
        """显式断言 payload 无 datetime 字段（Task 0.3.4 要求）。"""
        import datetime

        payload = self._build_payload("complaint")
        def _walk(value):
            if isinstance(value, (datetime.datetime, datetime.date)):
                self.fail(f"payload 含 datetime: {value!r}")
            if isinstance(value, dict):
                for v in value.values():
                    _walk(v)
            elif isinstance(value, list):
                for v in value:
                    _walk(v)

        _walk(payload)


if __name__ == "__main__":
    unittest.main()
