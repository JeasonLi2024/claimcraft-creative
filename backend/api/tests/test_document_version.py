# -*- coding: utf-8 -*-
"""Task 4.1 测试：段落级证据引用 + 文书版本。

覆盖范围（22 个测试用例，>= 12 要求）：
1. DocumentVersion 模型测试（创建 / 版本自增 / 按 case 查询 / 跨 document_type 独立版本号）
2. ComplaintTemplate / RespondTemplate paragraphs 字段默认值
3. paragraph_splitter 单元测试（Markdown / 中文序号切分 / 证据匹配 / 无标题单段 / update_paragraph / merge）
4. document_version_service 服务测试（get_next_version / create_document_version / regenerate_paragraph）
5. complaint_node 输出 paragraphs 字段 + 创建 DocumentVersion（mock LLM）
6. respond_complaint_node 输出 paragraphs 字段（mock LLM）
7. 段落重新生成 API（成功 / 404 段落不存在 / 403 非 owner / 400 段落为空）

测试策略：
- 模型 / 服务 / API 测试使用 Django TestCase（DB-backed，SQLite 兼容）
- paragraph_splitter 纯函数测试使用 SimpleTestCase（无 DB 依赖）
- 节点测试 mock LLM 调用（llm_service.is_llm_available / chat_with_retry）+
  mock RAG 检索（pre_retrieve_law_articles）+ mock 工具开关（is_tools_enabled=False）
- API 测试 mock `_regenerate_paragraph_content` 模块级函数（便于断言）

运行方式：
    cd backend
    python manage.py test api.tests.test_document_version -v 2
"""
import asyncio
from unittest.mock import AsyncMock, patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.agents.utils.paragraph_splitter import (
    merge_paragraphs_to_content,
    split_into_paragraphs,
    update_paragraph,
)
from api.models import (
    Case,
    ComplaintTemplate,
    DocumentVersion,
    RespondTemplate,
    WorkflowRun,
)
from api.services.document_version_service import (
    create_document_version,
    get_next_version,
    regenerate_paragraph,
)


# ============================================================================
# 辅助函数
# ============================================================================


def _make_case(user=None, **kwargs):
    """创建一个最小 Case。"""
    return Case.objects.create(
        title=kwargs.pop('title', '测试案件'),
        owner=user,
        **kwargs,
    )


def _make_run(case, **kwargs):
    """创建一个 WorkflowRun（thread_id 由 save() 自动生成）。"""
    defaults = {
        'status': 'running',
        'current_stage': 'document_generation',
        'current_node': 'complaint',
        'progress': 0.90,
        'revision': 1,
    }
    defaults.update(kwargs)
    return WorkflowRun.objects.create(case=case, **defaults)


def _make_paragraphs():
    """构造测试用段落列表（含证据引用 + 法条引用）。"""
    return [
        {
            'paragraph_id': 'p1',
            'title': '当事人信息',
            'content': '## 当事人信息\n投诉人：张三',
            'evidence_codes': ['E1'],
            'legal_references': [],
            'source_regions': [],
        },
        {
            'paragraph_id': 'p2',
            'title': '事实与理由',
            'content': '## 事实与理由\n商家未按约定发货（参见 E2）'
                       '，违反《消费者权益保护法》第五十五条。',
            'evidence_codes': ['E2'],
            'legal_references': [
                {'law_name': '消费者权益保护法', 'article_number': '第五十五条'},
            ],
            'source_regions': [],
        },
        {
            'paragraph_id': 'p3',
            'title': '诉求',
            'content': '## 诉求\n请求退一赔三。',
            'evidence_codes': [],
            'legal_references': [],
            'source_regions': [],
        },
    ]


def _make_node_state(case_id, **extra):
    """构造 complaint_node / respond_complaint_node 测试用 state。"""
    state = {
        'case_id': case_id,
        'revision': 5,
        'workflow_version': 'v11',
        'evidence_preclassify_results': [],
        'evidence_ocr_results': [],
        'evidence_classify_results': [],
        'evidence_extract_results': [],
        'evidence_chain': [],
        'errors': [],
        'warnings': [],
        'provenance': [],
        'issues': [],
        'events': [],
        'artifacts': [],
    }
    state.update(extra)
    return state


# ============================================================================
# SubTask 4.1.3：paragraph_splitter 单元测试（纯函数）
# ============================================================================


class ParagraphSplitterUnitTests(SimpleTestCase):
    """paragraph_splitter 工具函数单元测试（无 DB 依赖）。"""

    def test_split_into_paragraphs_markdown_headers(self):
        """Markdown 标题（## ）被识别为段落边界，每段含 paragraph_id。"""
        content = (
            '## 当事人信息\n投诉人：张三\n\n'
            '## 事实与理由\n商家未按约定发货\n\n'
            '## 诉求\n请求退款'
        )
        paragraphs = split_into_paragraphs(content)

        self.assertEqual(len(paragraphs), 3)
        self.assertEqual(paragraphs[0]['paragraph_id'], 'p1')
        self.assertEqual(paragraphs[0]['title'], '当事人信息')
        self.assertIn('投诉人：张三', paragraphs[0]['content'])
        self.assertEqual(paragraphs[1]['paragraph_id'], 'p2')
        self.assertEqual(paragraphs[1]['title'], '事实与理由')
        self.assertEqual(paragraphs[2]['title'], '诉求')
        # 每段含必需字段
        for p in paragraphs:
            self.assertIn('evidence_codes', p)
            self.assertIn('legal_references', p)
            self.assertIn('source_regions', p)
            self.assertEqual(p['source_regions'], [])

    def test_split_into_paragraphs_chinese_numbered_with_evidence(self):
        """中文序号（一、二、）作为段落边界 + 证据编号匹配过滤。"""
        content = (
            '一、当事人信息\n投诉人：张三，证据 E1 已附\n\n'
            '二、事实与理由\n商家欺诈，证据 E2 + EV5 已附（EV5 不在可用列表，应被过滤）'
        )
        # available_codes 含 E1 / E2，不含 EV5（验证过滤）
        paragraphs = split_into_paragraphs(
            content, evidence_codes=['E1', 'E2'],
        )

        self.assertEqual(len(paragraphs), 2)
        self.assertEqual(paragraphs[0]['title'], '当事人信息')
        self.assertEqual(paragraphs[0]['evidence_codes'], ['E1'])
        self.assertEqual(paragraphs[1]['title'], '事实与理由')
        # E2 在可用列表，EV5 不在，应被过滤掉
        self.assertEqual(paragraphs[1]['evidence_codes'], ['E2'])

    def test_split_into_paragraphs_no_header_returns_single_paragraph(self):
        """无任何标题时整篇作为单段返回（paragraph_id=p1）。

        注意：split_into_paragraphs 的 _flush() 在无标题时使用 '段落 N' 作为
        默认标题；仅当 content 为空时才回退到 '正文' 单段。
        """
        content = '这是一段没有标题的纯文本内容，包含证据 E1。'
        paragraphs = split_into_paragraphs(content, evidence_codes=['E1'])

        self.assertEqual(len(paragraphs), 1)
        self.assertEqual(paragraphs[0]['paragraph_id'], 'p1')
        # 无标题时 _flush() 使用 '段落 N' 作为默认标题
        self.assertEqual(paragraphs[0]['title'], '段落 1')
        self.assertEqual(paragraphs[0]['evidence_codes'], ['E1'])

    def test_split_into_paragraphs_legal_references_matching(self):
        """段落正文包含法条 law_name 时被匹配到 legal_references。"""
        content = (
            '## 事实与理由\n商家欺诈行为违反《消费者权益保护法》第五十五条。'
        )
        legal_refs = [
            {'law_name': '消费者权益保护法', 'article_number': '第五十五条'},
            {'law_name': '民法典', 'article_number': '第一千条'},
        ]
        paragraphs = split_into_paragraphs(content, legal_references=legal_refs)

        self.assertEqual(len(paragraphs), 1)
        # 仅消费者权益保护法被匹配（民法典未在正文中出现）
        self.assertEqual(len(paragraphs[0]['legal_references']), 1)
        self.assertEqual(
            paragraphs[0]['legal_references'][0]['law_name'],
            '消费者权益保护法',
        )

    def test_split_into_paragraphs_empty_content_returns_empty_list(self):
        """空内容返回空列表。"""
        self.assertEqual(split_into_paragraphs(''), [])
        self.assertEqual(split_into_paragraphs('   \n  \n'), [])

    def test_update_paragraph_returns_updated_list_with_target_index(self):
        """update_paragraph 深拷贝更新目标段落，返回新列表 + 索引。"""
        paragraphs = _make_paragraphs()
        original_p2_content = paragraphs[1]['content']

        new_paragraphs, idx = update_paragraph(
            paragraphs, 'p2', '## 事实与理由\n新的理由内容',
            evidence_codes=['E3'],
        )

        # 返回的索引正确
        self.assertEqual(idx, 1)
        # 入参未被修改（深拷贝）
        self.assertEqual(paragraphs[1]['content'], original_p2_content)
        # 新列表中目标段落已更新
        self.assertIn('新的理由内容', new_paragraphs[1]['content'])
        self.assertEqual(new_paragraphs[1]['evidence_codes'], ['E3'])
        # 其他段落保持不变
        self.assertEqual(new_paragraphs[0], paragraphs[0])
        self.assertEqual(new_paragraphs[2], paragraphs[2])

    def test_update_paragraph_unknown_id_returns_minus_one_index(self):
        """update_paragraph 未找到段落 ID 时返回 -1，列表不变。"""
        paragraphs = _make_paragraphs()
        new_paragraphs, idx = update_paragraph(
            paragraphs, 'p999', 'new content',
        )
        self.assertEqual(idx, -1)
        self.assertEqual(len(new_paragraphs), len(paragraphs))

    def test_update_paragraph_empty_list_raises_value_error(self):
        """update_paragraph 入参为空列表时抛 ValueError。"""
        with self.assertRaises(ValueError):
            update_paragraph([], 'p1', 'content')

    def test_merge_paragraphs_to_content_joins_with_blank_line(self):
        """merge_paragraphs_to_content 以空行连接段落 content。"""
        paragraphs = _make_paragraphs()
        merged = merge_paragraphs_to_content(paragraphs)
        # 三段 content 之间应有空行分隔
        self.assertIn('## 当事人信息', merged)
        self.assertIn('## 事实与理由', merged)
        self.assertIn('## 诉求', merged)
        self.assertIn('\n\n', merged)

    def test_merge_paragraphs_to_content_empty_returns_empty_string(self):
        """merge_paragraphs_to_content 空列表返回空字符串。"""
        self.assertEqual(merge_paragraphs_to_content([]), '')


# ============================================================================
# SubTask 4.1.1：ComplaintTemplate / RespondTemplate paragraphs 字段测试
# ============================================================================


class TemplateParagraphsFieldTests(TestCase):
    """ComplaintTemplate / RespondTemplate paragraphs JSONField 默认值测试。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', password='pass',
        )
        self.case = _make_case(self.user)

    def test_complaint_template_paragraphs_defaults_to_empty_list(self):
        """ComplaintTemplate 创建时 paragraphs 默认为空列表。"""
        tmpl = ComplaintTemplate.objects.create(
            case=self.case,
            template_type='platform',
            title='测试投诉书',
            content='正文内容',
        )
        self.assertEqual(tmpl.paragraphs, [])
        # 重新从 DB 读取验证
        tmpl.refresh_from_db()
        self.assertEqual(tmpl.paragraphs, [])

    def test_respond_template_paragraphs_defaults_to_empty_list(self):
        """RespondTemplate 创建时 paragraphs 默认为空列表。"""
        tmpl = RespondTemplate.objects.create(
            case=self.case,
            template_type='platform',
            title='测试答辩书',
            content='正文内容',
        )
        self.assertEqual(tmpl.paragraphs, [])
        tmpl.refresh_from_db()
        self.assertEqual(tmpl.paragraphs, [])

    def test_complaint_template_paragraphs_persists_json_structure(self):
        """ComplaintTemplate.paragraphs 可持久化复杂 JSON 段落结构。"""
        paragraphs = _make_paragraphs()
        ComplaintTemplate.objects.create(
            case=self.case,
            template_type='platform',
            title='测试投诉书',
            content='正文',
            paragraphs=paragraphs,
        )
        tmpl = ComplaintTemplate.objects.get(case=self.case, template_type='platform')
        self.assertEqual(len(tmpl.paragraphs), 3)
        self.assertEqual(tmpl.paragraphs[0]['paragraph_id'], 'p1')
        self.assertEqual(tmpl.paragraphs[1]['evidence_codes'], ['E2'])


# ============================================================================
# SubTask 4.1.2：DocumentVersion 模型测试
# ============================================================================


class DocumentVersionModelTests(TestCase):
    """DocumentVersion 模型创建 / 版本号 / 查询测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user)
        self.other_case = _make_case(self.user, title='其他案件')

    def test_create_document_version_basic_fields(self):
        """DocumentVersion 创建后所有字段正确持久化。"""
        doc = DocumentVersion.objects.create(
            case=self.case,
            document_type='complaint',
            version=1,
            title='投诉书 v1',
            content='投诉书正文',
            paragraphs=_make_paragraphs(),
            changelog='AI 生成初版',
            created_by_type='ai',
            workflow_version='v11',
        )
        doc.refresh_from_db()
        self.assertEqual(doc.document_type, 'complaint')
        self.assertEqual(doc.version, 1)
        self.assertEqual(doc.title, '投诉书 v1')
        self.assertEqual(doc.content, '投诉书正文')
        self.assertEqual(len(doc.paragraphs), 3)
        self.assertEqual(doc.changelog, 'AI 生成初版')
        self.assertEqual(doc.created_by_type, 'ai')
        self.assertEqual(doc.workflow_version, 'v11')
        self.assertIsNotNone(doc.created_at)
        # workflow_run / complaint_template / respond_template 默认为 null
        self.assertIsNone(doc.workflow_run_id)
        self.assertIsNone(doc.complaint_template_id)
        self.assertIsNone(doc.respond_template_id)

    def test_document_version_str_representation(self):
        """DocumentVersion.__str__ 含 id / case_id / type / version。"""
        doc = DocumentVersion.objects.create(
            case=self.case,
            document_type='respond_complaint',
            version=2,
            title='答辩书',
            content='正文',
        )
        s = str(doc)
        self.assertIn('DocumentVersion', s)
        self.assertIn(f'case={self.case.id}', s)
        self.assertIn('type=respond_complaint', s)
        self.assertIn('v2', s)

    def test_document_version_case_related_name_works(self):
        """DocumentVersion 通过 case.document_versions 反向查询。"""
        DocumentVersion.objects.create(
            case=self.case, document_type='complaint',
            version=1, title='t1', content='c1',
        )
        DocumentVersion.objects.create(
            case=self.case, document_type='complaint',
            version=2, title='t2', content='c2',
        )
        versions = list(self.case.document_versions.order_by('version'))
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].version, 1)
        self.assertEqual(versions[1].version, 2)

    def test_document_version_ordering_default_desc_by_version(self):
        """DocumentVersion 默认 ordering = -version（最新版本在前）。"""
        for v in (1, 2, 3):
            DocumentVersion.objects.create(
                case=self.case, document_type='complaint',
                version=v, title=f't{v}', content='c',
            )
        versions = list(DocumentVersion.objects.all())
        self.assertEqual([v.version for v in versions], [3, 2, 1])


# ============================================================================
# SubTask 4.1.2：document_version_service 服务测试
# ============================================================================


class DocumentVersionServiceTests(TestCase):
    """document_version_service 服务测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user)

    def test_get_next_version_returns_1_when_no_history(self):
        """无历史版本时 get_next_version 返回 1。"""
        self.assertEqual(get_next_version(self.case.id, 'complaint'), 1)
        self.assertEqual(get_next_version(self.case.id, 'respond_complaint'), 1)

    def test_get_next_version_increments_max_version(self):
        """已有历史版本时 get_next_version 返回 max(version) + 1。"""
        DocumentVersion.objects.create(
            case=self.case, document_type='complaint',
            version=1, title='t1', content='c',
        )
        DocumentVersion.objects.create(
            case=self.case, document_type='complaint',
            version=3, title='t3', content='c',
        )
        self.assertEqual(get_next_version(self.case.id, 'complaint'), 4)

    def test_get_next_version_independent_across_document_types(self):
        """不同 document_type 的版本号序列独立。"""
        DocumentVersion.objects.create(
            case=self.case, document_type='complaint',
            version=1, title='t1', content='c',
        )
        DocumentVersion.objects.create(
            case=self.case, document_type='complaint',
            version=2, title='t2', content='c',
        )
        # respond_complaint 应独立从 1 开始
        self.assertEqual(get_next_version(self.case.id, 'respond_complaint'), 1)
        self.assertEqual(get_next_version(self.case.id, 'complaint'), 3)

    def test_create_document_version_auto_assigns_version(self):
        """create_document_version 自动计算 version 字段。"""
        doc1 = create_document_version(
            case=self.case, document_type='complaint',
            title='t1', content='c1', paragraphs=[],
            changelog='v1', created_by_type='ai',
            workflow_version='v11',
        )
        self.assertEqual(doc1.version, 1)
        doc2 = create_document_version(
            case=self.case, document_type='complaint',
            title='t2', content='c2', paragraphs=[],
            changelog='v2', created_by_type='user',
            created_by_id=self.user.id,
            workflow_version='v11',
        )
        self.assertEqual(doc2.version, 2)
        self.assertEqual(doc2.created_by_type, 'user')
        self.assertEqual(doc2.created_by_id, self.user.id)

    def test_regenerate_paragraph_creates_new_version_with_updated_paragraph(self):
        """regenerate_paragraph 创建新版本，仅替换目标段落 content / evidence_codes。"""
        original_paragraphs = _make_paragraphs()
        doc_v1 = create_document_version(
            case=self.case, document_type='complaint',
            title='投诉书', content='原始正文',
            paragraphs=original_paragraphs,
            changelog='v1', workflow_version='v11',
        )

        new_doc, new_paragraph, idx = regenerate_paragraph(
            doc_version=doc_v1,
            paragraph_id='p2',
            new_content='## 事实与理由\n全新的事实理由',
            evidence_codes=['E5'],
            changelog='段落 p2 重新生成',
            created_by_type='user',
            created_by_id=self.user.id,
        )

        # 新版本号 = 2
        self.assertEqual(new_doc.version, 2)
        self.assertEqual(new_doc.case_id, self.case.id)
        # 入参 doc_version 未被修改
        doc_v1.refresh_from_db()
        self.assertEqual(doc_v1.version, 1)
        # 段落索引正确
        self.assertEqual(idx, 1)
        # 目标段落 content / evidence_codes 已更新
        self.assertIn('全新的事实理由', new_paragraph['content'])
        self.assertEqual(new_paragraph['evidence_codes'], ['E5'])
        # 其他段落保持不变
        self.assertEqual(new_doc.paragraphs[0]['content'], original_paragraphs[0]['content'])
        self.assertEqual(new_doc.paragraphs[2]['content'], original_paragraphs[2]['content'])
        # content 字段已合并重建（含新段落内容）
        self.assertIn('全新的事实理由', new_doc.content)

    def test_regenerate_paragraph_empty_paragraphs_raises_value_error(self):
        """regenerate_paragraph 段落为空时抛 ValueError。"""
        doc = create_document_version(
            case=self.case, document_type='complaint',
            title='t', content='c', paragraphs=[],
        )
        with self.assertRaises(ValueError):
            regenerate_paragraph(doc, 'p1', 'new content')

    def test_regenerate_paragraph_unknown_id_raises_value_error(self):
        """regenerate_paragraph 段落 ID 不存在时抛 ValueError。"""
        doc = create_document_version(
            case=self.case, document_type='complaint',
            title='t', content='c', paragraphs=_make_paragraphs(),
        )
        with self.assertRaises(ValueError):
            regenerate_paragraph(doc, 'p999', 'new content')


# ============================================================================
# SubTask 4.1.3：complaint_node 输出 paragraphs 测试（mock LLM）
# ============================================================================


class ComplaintNodeParagraphsTests(TransactionTestCase):
    """complaint_node 段落级结构化输出测试（mock LLM + RAG）。

    使用 TransactionTestCase 而非 TestCase：
    complaint_node 内部 sync_to_async(Case.objects.get)(...) 会在
    thread pool 中执行 ORM 查询，TestCase 的原子事务会导致 SQLite
    'database table is locked' 错误（跨线程连接看不到未提交事务）。
    TransactionTestCase 不包裹事务，每次操作即时提交，规避此问题。
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='complaint-owner', password='pass',
        )
        self.case = _make_case(self.user)
        # 预创建 ComplaintTemplate 让 generate_complaint 回退命中（避免"材料尚未完整"）
        ComplaintTemplate.objects.create(
            case=self.case, template_type='platform',
            title='投诉书', content='## 当事人信息\n骨架内容\n\n## 诉求\n请求退款',
        )

    def _run_complaint_node(self, state):
        """运行 complaint_node，mock LLM + RAG。"""
        from api.agents.nodes.complaint_node import complaint_node

        rewritten_content = (
            '## 当事人信息\n投诉人：张三，证据 E1 已附\n\n'
            '## 事实与理由\n商家欺诈，证据 E2 已附，'
            '违反《消费者权益保护法》第五十五条\n\n'
            '## 诉求\n请求退一赔三'
        )

        with patch(
            'api.services.llm_service.is_llm_available',
            return_value=True,
        ), patch(
            'api.services.llm_service.chat_with_retry',
            return_value=rewritten_content,
        ), patch(
            'api.agents.tools.law_tools.is_tools_enabled',
            return_value=False,
        ), patch(
            'api.agents.tools.law_tools.pre_retrieve_law_articles',
            new_callable=AsyncMock,
            return_value=[
                {
                    'law_name': '消费者权益保护法',
                    'article_number': '第五十五条',
                    'summary': '欺诈行为退一赔三',
                    'content': '经营者提供商品...退一赔三',
                    'source_url': 'local://law/1',
                },
            ],
        ):
            return asyncio.run(complaint_node(state))

    def test_complaint_node_outputs_paragraphs_field(self):
        """complaint_node 返回 partial 含 paragraphs 字段（list[dict]）。"""
        state = _make_node_state(self.case.id)
        partial = self._run_complaint_node(state)

        # node_result.data 含 paragraph_count
        self.assertIn('node_result', partial)
        self.assertIn('paragraph_count', partial['node_result']['data'])
        self.assertGreater(partial['node_result']['data']['paragraph_count'], 0)

        # legacy complaint_draft 字段含 paragraphs
        complaint_draft = partial.get('complaint_draft')
        self.assertIsNotNone(complaint_draft)
        self.assertIn('paragraphs', complaint_draft)
        paragraphs = complaint_draft['paragraphs']
        self.assertIsInstance(paragraphs, list)
        self.assertGreater(len(paragraphs), 0)

        # 每段含必需字段
        for p in paragraphs:
            self.assertIn('paragraph_id', p)
            self.assertIn('title', p)
            self.assertIn('content', p)
            self.assertIn('evidence_codes', p)
            self.assertIn('legal_references', p)
            self.assertIn('source_regions', p)

        # 至少一段含证据引用（E1 / E2）
        all_codes = [c for p in paragraphs for c in p.get('evidence_codes', [])]
        self.assertTrue(any(c in ('E1', 'E2') for c in all_codes))

    def test_complaint_node_creates_document_version_when_workflow_run_id(self):
        """complaint_node 在 workflow_run_id 存在时创建 DocumentVersion 记录。"""
        run = _make_run(self.case)
        state = _make_node_state(self.case.id, workflow_run_id=run.id)
        partial = self._run_complaint_node(state)

        # node_result.data.document_version_id 已设置
        doc_version_id = partial['node_result']['data'].get('document_version_id')
        self.assertIsNotNone(doc_version_id)

        # DB 中 DocumentVersion 已创建
        doc = DocumentVersion.objects.get(pk=doc_version_id)
        self.assertEqual(doc.case_id, self.case.id)
        self.assertEqual(doc.document_type, 'complaint')
        self.assertEqual(doc.created_by_type, 'ai')
        self.assertEqual(doc.workflow_version, 'v11')
        self.assertEqual(doc.workflow_run_id, run.id)
        self.assertGreater(len(doc.paragraphs), 0)
        # version=1（首次创建）
        self.assertEqual(doc.version, 1)

    def test_complaint_node_creates_complaint_template_with_paragraphs(self):
        """complaint_node 持久化 ComplaintTemplate 时写入 paragraphs 字段。"""
        state = _make_node_state(self.case.id)
        self._run_complaint_node(state)

        tmpl = ComplaintTemplate.objects.get(
            case=self.case, template_type='platform',
        )
        self.assertIsNotNone(tmpl.paragraphs)
        self.assertGreater(len(tmpl.paragraphs), 0)
        # paragraphs 中段落含 paragraph_id
        self.assertTrue(all('paragraph_id' in p for p in tmpl.paragraphs))


# ============================================================================
# SubTask 4.1.3：respond_complaint_node 输出 paragraphs 测试（mock LLM）
# ============================================================================


class RespondComplaintNodeParagraphsTests(TransactionTestCase):
    """respond_complaint_node 段落级结构化输出测试（mock LLM + RAG）。

    使用 TransactionTestCase 规避 sync_to_async 跨线程 SQLite 锁问题
    （详见 ComplaintNodeParagraphsTests 说明）。
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='respond-owner', password='pass',
        )
        self.case = _make_case(self.user, case_mode='respond')
        # 预创建 ComplaintTemplate 让 generate_complaint 骨架可命中
        ComplaintTemplate.objects.create(
            case=self.case, template_type='platform',
            title='答辩书', content='## 答辩人信息\n骨架\n\n## 答辩理由\n商家无过错',
        )

    def test_respond_complaint_node_outputs_paragraphs_field(self):
        """respond_complaint_node 返回 partial 含 paragraphs 字段。"""
        from api.agents.nodes.respond_complaint_node import respond_complaint_node

        rewritten_content = (
            '## 答辩人信息\n答辩人：商家，证据 E1 显示商品无瑕疵\n\n'
            '## 答辩理由\n消费者主张不成立，证据 E2 已附，'
            '不适用《消费者权益保护法》第五十五条\n\n'
            '## 结论\n请求驳回消费者诉求'
        )

        state = _make_node_state(self.case.id)
        with patch(
            'api.services.llm_service.is_llm_available',
            return_value=True,
        ), patch(
            'api.services.llm_service.chat_with_retry',
            return_value=rewritten_content,
        ), patch(
            'api.agents.tools.law_tools.is_tools_enabled',
            return_value=False,
        ), patch(
            'api.agents.tools.law_tools.pre_retrieve_law_articles',
            new_callable=AsyncMock,
            return_value=[
                {
                    'law_name': '消费者权益保护法',
                    'article_number': '第五十五条',
                    'summary': '欺诈行为退一赔三',
                    'content': '经营者提供商品...',
                    'source_url': 'local://law/1',
                },
            ],
        ):
            partial = asyncio.run(respond_complaint_node(state))

        # node_result.data 含 paragraph_count
        self.assertIn('node_result', partial)
        self.assertIn('paragraph_count', partial['node_result']['data'])
        self.assertGreater(partial['node_result']['data']['paragraph_count'], 0)

        # legacy complaint_draft（与 complaint_node 对齐，复用同名字段）
        complaint_draft = partial.get('complaint_draft')
        self.assertIsNotNone(complaint_draft)
        self.assertIn('paragraphs', complaint_draft)
        paragraphs = complaint_draft['paragraphs']
        self.assertIsInstance(paragraphs, list)
        self.assertGreater(len(paragraphs), 0)

        # 段落含证据引用
        all_codes = [c for p in paragraphs for c in p.get('evidence_codes', [])]
        self.assertTrue(any(c in ('E1', 'E2') for c in all_codes))

    def test_respond_complaint_node_creates_document_version(self):
        """respond_complaint_node 在 workflow_run_id 存在时创建 DocumentVersion
        （document_type='respond_complaint'）。"""
        from api.agents.nodes.respond_complaint_node import respond_complaint_node

        run = _make_run(self.case)
        rewritten_content = '## 答辩人信息\n商家无过错\n\n## 结论\n请求驳回'
        state = _make_node_state(self.case.id, workflow_run_id=run.id)
        with patch(
            'api.services.llm_service.is_llm_available',
            return_value=True,
        ), patch(
            'api.services.llm_service.chat_with_retry',
            return_value=rewritten_content,
        ), patch(
            'api.agents.tools.law_tools.is_tools_enabled',
            return_value=False,
        ), patch(
            'api.agents.tools.law_tools.pre_retrieve_law_articles',
            new_callable=AsyncMock,
            return_value=[],
        ):
            partial = asyncio.run(respond_complaint_node(state))

        doc_version_id = partial['node_result']['data'].get('document_version_id')
        self.assertIsNotNone(doc_version_id)
        doc = DocumentVersion.objects.get(pk=doc_version_id)
        self.assertEqual(doc.document_type, 'respond_complaint')
        self.assertEqual(doc.workflow_run_id, run.id)
        self.assertEqual(doc.created_by_type, 'ai')


# ============================================================================
# SubTask 4.1.4：段落重新生成 API 测试（mock LLM）
# ============================================================================


class DocumentParagraphRegenerateAPITests(TestCase):
    """DocumentParagraphRegenerateView 端点测试。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass',
        )
        self.other_user = User.objects.create_user(
            username='other', email='other@example.com', password='pass',
        )
        self.case = _make_case(self.user)
        self.run = _make_run(self.case)
        self.doc_version = create_document_version(
            case=self.case,
            workflow_run=self.run,
            document_type='complaint',
            title='投诉书',
            content='## 当事人信息\n投诉人\n\n## 诉求\n请求退款',
            paragraphs=_make_paragraphs(),
            changelog='AI 生成初版',
            created_by_type='ai',
            workflow_version='v11',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = (
            f'/api/workflow-runs/{self.run.id}/'
            f'documents/{self.doc_version.id}/'
            f'paragraphs/p2/regenerate/'
        )

    def test_regenerate_success_returns_new_version(self):
        """成功重新生成段落返回 200 + 新 DocumentVersion + 更新后段落。"""
        with patch(
            'api.views._regenerate_paragraph_content',
            return_value='## 事实与理由\n全新的理由内容',
        ):
            response = self.client.post(self.url, {
                'instructions': '更详细描述',
                'evidence_codes': ['E5'],
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn('document_id', payload)
        self.assertIn('version', payload)
        self.assertIn('paragraph_id', payload)
        self.assertIn('paragraph', payload)
        self.assertIn('changelog', payload)

        # 新版本号 = 2（原版本 1 + 1）
        self.assertEqual(payload['version'], 2)
        self.assertEqual(payload['paragraph_id'], 'p2')
        # 段落 content 已更新
        self.assertIn('全新的理由内容', payload['paragraph']['content'])
        # evidence_codes 通过 request.data 传入，已被更新
        self.assertEqual(payload['paragraph']['evidence_codes'], ['E5'])

        # DB 中新 DocumentVersion 已创建
        new_doc = DocumentVersion.objects.get(pk=payload['document_id'])
        self.assertEqual(new_doc.version, 2)
        self.assertEqual(new_doc.created_by_type, 'user')
        self.assertEqual(new_doc.created_by_id, self.user.id)
        # 原版本未受影响
        self.doc_version.refresh_from_db()
        self.assertEqual(self.doc_version.version, 1)

    def test_regenerate_404_when_paragraph_not_found(self):
        """段落 ID 不存在返回 404。"""
        url = (
            f'/api/workflow-runs/{self.run.id}/'
            f'documents/{self.doc_version.id}/'
            f'paragraphs/p999/regenerate/'
        )
        with patch(
            'api.views._regenerate_paragraph_content',
            return_value='new content',
        ):
            response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        payload = response.json()
        self.assertIn('detail', payload)

    def test_regenerate_404_when_run_not_found(self):
        """不存在的 run_id 返回 404。"""
        url = (
            f'/api/workflow-runs/999999/'
            f'documents/{self.doc_version.id}/'
            f'paragraphs/p1/regenerate/'
        )
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_regenerate_403_when_not_case_owner(self):
        """非 case owner 访问返回 404（不暴露存在性）。"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(self.url, {}, format='json')
        # 视图显式返回 404（对齐 workflow-runs API 一致性，不暴露存在性）
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_regenerate_401_when_unauthenticated(self):
        """未认证用户返回 401。"""
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regenerate_400_when_paragraphs_empty(self):
        """段落结构为空时返回 400。"""
        empty_doc = create_document_version(
            case=self.case,
            workflow_run=self.run,
            document_type='complaint',
            title='空段落文书',
            content='无段落结构',
            paragraphs=[],
        )
        url = (
            f'/api/workflow-runs/{self.run.id}/'
            f'documents/{empty_doc.id}/'
            f'paragraphs/p1/regenerate/'
        )
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        payload = response.json()
        self.assertIn('detail', payload)

    def test_regenerate_404_when_document_not_under_run(self):
        """document_id 不属于该 run 时返回 404（get_object_or_404 过滤）。"""
        # 创建另一个 run + doc，不属于当前 self.run
        other_run = _make_run(self.case)
        other_doc = create_document_version(
            case=self.case, workflow_run=other_run,
            document_type='complaint',
            title='其他 run 的文书', content='c',
            paragraphs=_make_paragraphs(),
        )
        url = (
            f'/api/workflow-runs/{self.run.id}/'  # 当前 run
            f'documents/{other_doc.id}/'  # 其他 run 的 doc
            f'paragraphs/p1/regenerate/'
        )
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_regenerate_preserves_other_paragraphs_unchanged(self):
        """重新生成单个段落后，其他段落 content 保持不变。"""
        original_paragraphs = _make_paragraphs()
        # 重建一个干净版本（setUp 中已创建 v1，这里复用即可）
        with patch(
            'api.views._regenerate_paragraph_content',
            return_value='## 事实与理由\n全新的理由',
        ):
            response = self.client.post(self.url, {
                'evidence_codes': ['E5'],
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_doc_id = response.json()['document_id']
        new_doc = DocumentVersion.objects.get(pk=new_doc_id)

        # p1 / p3 的 content 保持不变
        p1 = next(p for p in new_doc.paragraphs if p['paragraph_id'] == 'p1')
        p3 = next(p for p in new_doc.paragraphs if p['paragraph_id'] == 'p3')
        self.assertEqual(p1['content'], original_paragraphs[0]['content'])
        self.assertEqual(p3['content'], original_paragraphs[2]['content'])
