# -*- coding: utf-8 -*-
"""PDF 投诉材料导出服务：基于 reportlab 生成含中文的 A4 PDF。"""
import os
import logging
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

logger = logging.getLogger(__name__)


def _resolve_chinese_font_path():
    """跨平台解析中文字体文件路径（A3 修复）。

    优先级：
    1. 环境变量 SIMSUN_PATH
    2. Windows 默认 C:\\Windows\\Fonts\\simsun.ttc
    3. Linux 常见路径：/usr/share/fonts/truetype/wqy/wqy-microhei.ttc
                      /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
    4. None（交给 _register_font 走 CID 字体回退）
    """
    env_path = os.environ.get('SIMSUN_PATH')
    if env_path and os.path.exists(env_path):
        return env_path
    candidates = [
        r'C:\Windows\Fonts\simsun.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/arphic/uming.ttc',
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


SIMSUN_PATH = _resolve_chinese_font_path()


def _register_font():
    """注册中文字体，三级回退。"""
    if SIMSUN_PATH:
        try:
            pdfmetrics.registerFont(TTFont('SimSun', SIMSUN_PATH))
            return 'SimSun'
        except Exception as e:
            logger.warning(f"中文字体注册失败 (path={SIMSUN_PATH}): {e}")
    else:
        logger.info("未找到本地中文字体文件，直接尝试 CID 字体")
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        return 'STSong-Light'
    except Exception as e:
        logger.warning(f"STSong-Light 注册失败: {e}")
    logger.warning("回退 Helvetica（中文可能乱码）")
    return 'Helvetica'


def generate_complaint_pdf(case, template_type='platform'):
    """生成 PDF 投诉材料，返回 BytesIO。"""
    from api.services.complaint_service import generate_complaint
    from api.services.timeline_service import get_sorted_timeline

    font_name = _register_font()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ChTitle', parent=styles['Title'], fontName=font_name, fontSize=18
    )
    h2_style = ParagraphStyle(
        'ChH2', parent=styles['Heading2'], fontName=font_name, fontSize=14
    )
    body_style = ParagraphStyle(
        'ChBody', parent=styles['Normal'],
        fontName=font_name, fontSize=11, leading=18,
    )

    complaint = generate_complaint(case, template_type)
    timeline_nodes = get_sorted_timeline(case)
    evidences = list(case.evidences.all().order_by('code'))

    story = []
    # 标题
    story.append(Paragraph(complaint['title'], title_style))
    story.append(Spacer(1, 0.5 * cm))
    # 事实经过
    story.append(Paragraph('一、事实经过', h2_style))
    for node in timeline_nodes:
        dt_str = node.datetime.strftime('%Y-%m-%d %H:%M')
        line = f'{dt_str} {node.event}'
        if node.related_evidence_codes:
            line += f'（见 {node.related_evidence_codes}）'
        story.append(Paragraph(line, body_style))
    story.append(Spacer(1, 0.3 * cm))
    # 关键信息表
    story.append(Paragraph('二、关键信息', h2_style))
    extracted_data = []
    for ev in evidences:
        for ef in ev.extracted_fields.all():
            extracted_data.append([ef.field_name, ef.field_value, ev.code])
    if extracted_data:
        tbl = Table(
            [['字段', '值', '证据']] + extracted_data,
            colWidths=[3 * cm, 8 * cm, 2 * cm],
        )
        tbl.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ]))
        story.append(tbl)
    story.append(Spacer(1, 0.3 * cm))
    # 诉求
    story.append(Paragraph('三、诉求', h2_style))
    story.append(Paragraph('1. 全额退款<br/>2. 依规则处理商家违约', body_style))
    story.append(Spacer(1, 0.3 * cm))
    # 证据清单（含图片缩略图）
    story.append(Paragraph('四、证据清单', h2_style))
    for ev in evidences:
        desc = ev.description or ''
        story.append(
            Paragraph(
                f'{ev.code} - {ev.evidence_type}：{desc[:50]}',
                body_style,
            )
        )
        if ev.image:
            try:
                img_path = (
                    ev.masked_image.path if ev.masked_image else ev.image.path
                )
                if os.path.exists(img_path):
                    img = Image(img_path, width=5 * cm, height=4 * cm)
                    story.append(img)
                    story.append(Spacer(1, 0.2 * cm))
            except Exception as e:
                logger.warning(f"图片嵌入失败 {ev.code}: {e}")
    story.append(Spacer(1, 1 * cm))
    # 签名区
    story.append(Paragraph('投诉人签名：________________', body_style))
    story.append(Paragraph('日期：________________', body_style))

    # 页眉页脚
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.drawString(2 * cm, A4[1] - 1 * cm, case.title)
        canvas.drawRightString(A4[0] - 2 * cm, 1 * cm, f'第 {doc.page} 页')
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    return buf
