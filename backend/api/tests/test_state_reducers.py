# -*- coding: utf-8 -*-
"""State reducer 单元测试（Task 0.1.7）。

验证 CaseWorkflowState 中各字段的 reducer 行为：
- Annotated[list, add] 累积追加
- 标量字段默认覆盖
- 自定义 dedup_add 去重追加
- 自定义 merge_dict 按 key 合并
- errors 类型从 list[str] 升级为 list[dict]（BREAKING 确认）

运行方式（任选其一）：
    cd backend
    python manage.py test api.tests.test_state_reducers -v 2
    # 或（如已安装 pytest）：
    python -m pytest api/tests/test_state_reducers.py -v
"""
import os
import sys
import unittest
from operator import add
from typing import Annotated, get_args, get_type_hints

# 确保可从项目根目录或 backend/ 目录运行（backend/ 需在 sys.path 上以解析 claimcraft.settings）
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# 配置 Django（幂等：manage.py test 运行时 Django 已由 runner 配置，此处为 no-op；
# pytest / 独立运行时由本 shim 完成配置，使 from api.agents.state import ... 可用）
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

import django
from django.apps import apps as _django_apps
if not _django_apps.ready:
    django.setup()

from api.agents.state import (  # noqa: E402  (import 在 Django setup 之后)
    CaseWorkflowState,
    dedup_add,
    merge_dict,
)


class DedupAddReducerTest(unittest.TestCase):
    """dedup_add reducer 行为测试（SubTask 0.1.4）。"""

    def test_empty_left_returns_copy_of_right(self):
        self.assertEqual(dedup_add([], [1, 2, 3]), [1, 2, 3])

    def test_empty_right_returns_copy_of_left(self):
        self.assertEqual(dedup_add([1, 2], []), [1, 2])

    def test_no_duplicates_concat(self):
        self.assertEqual(dedup_add([1, 2], [3, 4]), [1, 2, 3, 4])

    def test_duplicates_removed_preserving_first_occurrence(self):
        # 两次返回 [1,2] 与 [2,3] → [1,2,3]（去重，保留首次出现顺序）
        self.assertEqual(dedup_add([1, 2], [2, 3]), [1, 2, 3])

    def test_does_not_mutate_inputs(self):
        left = [1, 2]
        right = [2, 3]
        dedup_add(left, right)
        self.assertEqual(left, [1, 2])
        self.assertEqual(right, [2, 3])


class MergeDictReducerTest(unittest.TestCase):
    """merge_dict reducer 行为测试（SubTask 0.1.5）。"""

    def test_empty_left_returns_copy_of_right(self):
        self.assertEqual(merge_dict({}, {"a": 1}), {"a": 1})

    def test_empty_right_returns_copy_of_left(self):
        self.assertEqual(merge_dict({"a": 1}, {}), {"a": 1})

    def test_merge_by_key_new_overrides_existing(self):
        # 旧 {a:1, b:2} + 新 {b:3, c:4} → {a:1, b:3, c:4}
        result = merge_dict({"a": 1, "b": 2}, {"b": 3, "c": 4})
        self.assertEqual(result, {"a": 1, "b": 3, "c": 4})

    def test_does_not_mutate_inputs(self):
        left = {"a": 1}
        right = {"b": 2}
        merge_dict(left, right)
        self.assertEqual(left, {"a": 1})
        self.assertEqual(right, {"b": 2})


class StateSchemaAnnotationTest(unittest.TestCase):
    """CaseWorkflowState 字段 reducer 注解验证。

    通过 get_type_hints(include_extras=True) 解析 Annotated 元数据，
    确认每个字段绑定了正确的 reducer（或无 reducer = 默认覆盖）。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # include_extras=True 保留 Annotated 包装，否则 add/dedup_add 元数据会被丢弃
        cls.hints = get_type_hints(CaseWorkflowState, include_extras=True)

    def _get_reducer(self, field: str):
        """提取字段绑定的 reducer 函数；无 Annotated 时返回 None（默认覆盖语义）。

        注意：Optional[dict] 的 get_args 返回 (dict, NoneType)，会被误判为有 reducer，
        因此必须用 __metadata__ 属性精确识别 Annotated 类型（Annotated 才有 __metadata__）。
        """
        annotation = self.hints[field]
        if hasattr(annotation, '__metadata__'):
            # Annotated[X, reducer, ...] → __metadata__ = (reducer, ...)
            return annotation.__metadata__[0]
        return None  # 无 reducer，LangGraph 默认覆盖

    def test_existing_accumulate_fields_use_add(self):
        """SubTask 0.1.1：现有累积列表字段使用 operator.add。"""
        for field in (
            "evidence_preclassify_results",
            "evidence_ocr_results",
            "evidence_classify_results",
            "evidence_extract_results",
            "errors",
        ):
            self.assertIs(
                self._get_reducer(field), add,
                msg=f"{field} 应绑定 operator.add reducer",
            )

    def test_new_accumulate_fields_use_add(self):
        """SubTask 0.1.2：新增累积字段 warnings/provenance/artifacts/interventions/issues/events 使用 operator.add。"""
        for field in (
            "warnings",
            "provenance",
            "artifacts",
            "interventions",
            "issues",
            "events",
        ):
            self.assertIs(
                self._get_reducer(field), add,
                msg=f"{field} 应绑定 operator.add reducer",
            )

    def test_scalar_fields_have_no_reducer(self):
        """SubTask 0.1.3：标量字段默认覆盖（无 reducer）。"""
        for field in (
            "revision",
            "current_stage",
            "current_node",
            "progress",
            "workflow_version",
            "state_schema_version",
            "policy_version",
            "prompt_bundle_version",
        ):
            self.assertIsNone(
                self._get_reducer(field),
                msg=f"{field} 不应绑定 reducer（默认覆盖）",
            )

    def test_stale_artifact_ids_uses_dedup_add(self):
        """SubTask 0.1.4：stale_artifact_ids 绑定 dedup_add。"""
        self.assertIs(self._get_reducer("stale_artifact_ids"), dedup_add)

    def test_user_confirmed_fields_uses_merge_dict(self):
        """SubTask 0.1.5：user_confirmed_fields 绑定 merge_dict。"""
        self.assertIs(self._get_reducer("user_confirmed_fields"), merge_dict)

    def test_node_result_has_no_reducer(self):
        """SubTask 0.1.6：node_result 默认覆盖（无 reducer）。"""
        self.assertIsNone(self._get_reducer("node_result"))

    def test_errors_inner_type_is_list_dict(self):
        """BREAKING 确认：errors 类型注解为 list[dict]（不再是 list[str]）。"""
        annotation = self.hints["errors"]
        args = get_args(annotation)
        # Annotated[list[dict], add] → get_args 返回 (list[dict], add)
        inner_type = args[0]
        # list[dict] → get_args 返回 (dict,)
        self.assertEqual(
            get_args(inner_type), (dict,),
            msg="errors 元素类型应为 dict（已从 str 升级）",
        )


class ReducerBehaviorTest(unittest.TestCase):
    """reducer 行为模拟测试（直接调用 reducer 函数模拟 LangGraph 状态合并）。

    覆盖 SubTask 0.1.7 要求的 5 个测试用例：
    1. evidence_preclassify_results 累积追加
    2. revision 标量默认覆盖
    3. stale_artifact_ids 去重追加
    4. user_confirmed_fields 按 key 合并
    5. errors 类型升级为 list[dict] 确认
    """

    def test_case1_evidence_preclassify_results_accumulate(self):
        """用例 1：evidence_preclassify_results 累积追加（两个节点各返回 [item1]/[item2] → [item1, item2]）。"""
        item1 = {"evidence_id": 1, "evidence_code": "EV001", "confidence": 0.9}
        item2 = {"evidence_id": 2, "evidence_code": "EV002", "confidence": 0.85}
        # 模拟 LangGraph reducer 合并：节点1 返回 [item1]，节点2 返回 [item2]
        current = []
        current = add(current, [item1])
        current = add(current, [item2])
        self.assertEqual(current, [item1, item2])
        self.assertEqual(len(current), 2)

    def test_case2_revision_scalar_overwrite(self):
        """用例 2：标量字段 revision 默认覆盖（节点返回 {"revision": 5} 覆盖原值 3）。"""
        # LangGraph 对无 reducer 字段的默认行为：新值直接替换旧值
        current_revision = 3
        node_update = {"revision": 5}
        # 模拟默认覆盖 reducer：若 update 含该 key 则取 update 值，否则保留原值
        new_revision = node_update["revision"] if "revision" in node_update else current_revision
        self.assertEqual(new_revision, 5)
        self.assertNotEqual(new_revision, current_revision)

    def test_case3_stale_artifact_ids_dedup(self):
        """用例 3：stale_artifact_ids 去重追加（两次返回 [1,2]/[2,3] → [1,2,3]）。"""
        current = []
        current = dedup_add(current, [1, 2])
        current = dedup_add(current, [2, 3])
        self.assertEqual(current, [1, 2, 3])
        self.assertEqual(len(current), 3)

    def test_case4_user_confirmed_fields_merge(self):
        """用例 4：user_confirmed_fields 按 key 合并（旧 {a:1,b:2} + 新 {b:3,c:4} → {a:1,b:3,c:4}）。"""
        current = {"a": 1, "b": 2}
        current = merge_dict(current, {"b": 3, "c": 4})
        self.assertEqual(current, {"a": 1, "b": 3, "c": 4})

    def test_case5_errors_dict_structure(self):
        """用例 5：errors 类型升级为 list[dict]（与旧 list[str] 不兼容，显式确认升级）。"""
        # 模拟 graph.py _make_error_handler 返回的错误条目结构
        error_entry = {
            "code": "node.error",
            "message": "[OCR] 节点异常: TimeoutError: 超时",
            "severity": "warning",
            "stage": "OCR",
            "recoverable": True,
        }
        # 模拟 errors 字段累积（Annotated[list[dict], add]）
        current_errors = []
        current_errors = add(current_errors, [error_entry])
        self.assertEqual(len(current_errors), 1)
        self.assertIsInstance(current_errors[0], dict)
        self.assertEqual(current_errors[0]["code"], "node.error")
        self.assertTrue(current_errors[0]["recoverable"])
        # 确认旧 list[str] 模式不再适用：errors 元素是 dict 而非 str
        self.assertNotIsInstance(current_errors[0], str)


if __name__ == "__main__":
    unittest.main()
