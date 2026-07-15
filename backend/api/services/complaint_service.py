# -*- coding: utf-8 -*-
"""投诉文本生成相关业务逻辑。"""
from jinja2 import Template

from api.models import ComplaintTemplateRule, ComplaintTemplate, RespondTemplate
from api.services.timeline_service import get_sorted_timeline


def _build_context(case):
    """构建 Jinja2 渲染上下文（案件 + 证据 + 时间线 + 抽取字段）。"""
    evidences = list(case.evidences.all().order_by('code'))
    timeline_nodes = get_sorted_timeline(case)
    extracted_fields = []
    for ev in evidences:
        for ef in ev.extracted_fields.all():
            extracted_fields.append({
                'evidence_code': ev.code,
                'field_name': ef.field_name,
                'field_value': ef.field_value,
            })
    return {
        'case': case,
        'evidences': evidences,
        'timeline_nodes': timeline_nodes,
        'extracted_fields': extracted_fields,
    }


def generate_complaint(case, template_type):
    """动态生成投诉文本。优先用 ComplaintTemplateRule (Jinja2)，回退 ComplaintTemplate 静态。"""
    context = _build_context(case)

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


def get_respond_template(case, template_type):
    """读取已生成的反证答辩书（从 RespondTemplate 表）。

    Args:
        case: 案件实例
        template_type: 答辩类型（platform/regulatory/legal）

    Returns:
        {title, content, template_type} 或 None
    """
    try:
        tmpl = RespondTemplate.objects.get(case=case, template_type=template_type)
        return {
            'title': tmpl.title,
            'content': tmpl.content,
            'template_type': template_type,
        }
    except RespondTemplate.DoesNotExist:
        return None


def list_respond_templates(case):
    """列出案件所有已生成的反证答辩书。

    Returns:
        list[{title, content, template_type}]，按 template_type 排序
    """
    templates = RespondTemplate.objects.filter(case=case).order_by('template_type')
    return [
        {
            'title': t.title,
            'content': t.content,
            'template_type': t.template_type,
        }
        for t in templates
    ]


def generate_respond_complaint(case, template_type):
    """生成反证答辩书文本。

    优先从 RespondTemplate 表读取已生成的答辩书（工作流产物），
    若不存在则回退到投诉模板（Jinja2 动态渲染，供手动预览）。

    Returns:
        {title, content, template_type}
    """
    # 1. 优先读已生成的 RespondTemplate
    result = get_respond_template(case, template_type)
    if result:
        return result

    # 2. 回退：用投诉模板渲染（供手动预览，实际内容由工作流生成）
    return generate_complaint(case, template_type)
