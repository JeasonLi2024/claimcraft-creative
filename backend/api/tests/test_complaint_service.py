from django.contrib.auth.models import User
from django.test import TestCase

from api.models import Case, ComplaintTemplate, ComplaintTemplateRule, TimelineNode
from api.services.complaint_service import generate_complaint


class ComplaintServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='complaint-owner')
        self.case = Case.objects.create(title='空材料案件', owner=self.user)

    def test_empty_timeline_does_not_break_global_rule_rendering(self):
        ComplaintTemplateRule.objects.create(
            case=None,
            template_type='platform',
            rule_title='{{ case.title }}——投诉申诉',
            rule_content="于 {{ timeline_nodes[0].datetime.strftime('%Y-%m-%d') }} 发生纠纷",
        )

        result = generate_complaint(self.case, 'platform')

        self.assertEqual(result['template_type'], 'platform')
        self.assertIn('材料尚未完整', result['content'])

    def test_invalid_case_rule_falls_back_to_renderable_global_rule(self):
        ComplaintTemplateRule.objects.create(
            case=self.case,
            template_type='platform',
            rule_title='案件规则',
            rule_content='{{ timeline_nodes[0].event }}',
        )
        ComplaintTemplateRule.objects.create(
            case=None,
            template_type='platform',
            rule_title='{{ case.title }}',
            rule_content='可安全展示的全局模板',
        )

        result = generate_complaint(self.case, 'platform')

        self.assertEqual(result['title'], self.case.title)
        self.assertEqual(result['content'], '可安全展示的全局模板')

    def test_invalid_rule_falls_back_to_saved_static_document(self):
        ComplaintTemplateRule.objects.create(
            case=None,
            template_type='platform',
            rule_title='错误规则',
            rule_content='{{ timeline_nodes[0].event }}',
        )
        ComplaintTemplate.objects.create(
            case=self.case,
            template_type='platform',
            title='已生成投诉书',
            content='已保存的有效内容',
        )

        result = generate_complaint(self.case, 'platform')

        self.assertEqual(result['title'], '已生成投诉书')
        self.assertEqual(result['content'], '已保存的有效内容')

    def test_valid_rule_still_renders_normally(self):
        TimelineNode.objects.create(case=self.case, event='发现商品损坏')
        ComplaintTemplateRule.objects.create(
            case=None,
            template_type='platform',
            rule_title='{{ case.title }}',
            rule_content='{% for node in timeline_nodes %}{{ node.event }}{% endfor %}',
        )

        result = generate_complaint(self.case, 'platform')

        self.assertEqual(result['content'], '发现商品损坏')

    def test_context_exposes_username_as_signer(self):
        ComplaintTemplateRule.objects.create(
            case=None, template_type="platform",
            rule_title="投诉书", rule_content="## 署名\n{{ signer_name }}",
        )

        result = generate_complaint(self.case, "platform")

        self.assertEqual(result["content"], "## 署名\ncomplaint-owner")
