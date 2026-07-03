# -*- coding: utf-8 -*-
"""投诉文本生成相关业务逻辑。"""
from jinja2 import Template

from api.models import ComplaintTemplateRule, ComplaintTemplate
from api.services.timeline_service import get_sorted_timeline


def generate_complaint(case, template_type):
    """动态生成投诉文本。优先用 ComplaintTemplateRule (Jinja2)，回退 ComplaintTemplate 静态。"""
    evidences = list(case.evidences.all().order_by('code'))
    timeline_nodes = get_sorted_timeline(case)
    # 收集所有抽取字段
    extracted_fields = []
    for ev in evidences:
        for ef in ev.extracted_fields.all():
            extracted_fields.append({
                'evidence_code': ev.code,
                'field_name': ef.field_name,
                'field_value': ef.field_value,
            })

    context = {
        'case': case,
        'evidences': evidences,
        'timeline_nodes': timeline_nodes,
        'extracted_fields': extracted_fields,
    }

    # 优先用案件级 Rule
    try:
        rule = ComplaintTemplateRule.objects.get(template_type=template_type, case=case)
        title_tmpl = Template(rule.rule_title)
        content_tmpl = Template(rule.rule_content)
        return {
            'title': title_tmpl.render(**context),
            'content': content_tmpl.render(**context),
            'template_type': template_type,
        }
    except ComplaintTemplateRule.DoesNotExist:
        # 查全局 Rule（case=null）
        try:
            rule = ComplaintTemplateRule.objects.get(
                template_type=template_type, case__isnull=True
            )
            title_tmpl = Template(rule.rule_title)
            content_tmpl = Template(rule.rule_content)
            return {
                'title': title_tmpl.render(**context),
                'content': content_tmpl.render(**context),
                'template_type': template_type,
            }
        except ComplaintTemplateRule.DoesNotExist:
            pass

    # 回退静态 ComplaintTemplate
    try:
        tmpl = ComplaintTemplate.objects.get(case=case, template_type=template_type)
        return {
            'title': tmpl.title,
            'content': tmpl.content,
            'template_type': template_type,
        }
    except ComplaintTemplate.DoesNotExist:
        return {
            'title': '投诉标题',
            'content': '暂无模板',
            'template_type': template_type,
        }
