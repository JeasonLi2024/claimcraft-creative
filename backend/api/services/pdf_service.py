# -*- coding: utf-8 -*-
"""正式文书导出：使用 XeLaTeX 生成中文 PDF，使用 Pandoc 生成 Word。"""
import logging
import os
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)


class DocumentRenderError(RuntimeError):
    """文书转换工具缺失或转换失败。"""


def _format_datetime(value):
    return value.strftime('%Y-%m-%d %H:%M') if value else '时间待确认'


def _latex_escape(value):
    """转义用户可编辑文本，防止破坏 LaTeX 模板或注入命令。"""
    replacements = {
        '\\': r'\textbackslash{}',
        '{': r'\{',
        '}': r'\}',
        '$': r'\$',
        '&': r'\&',
        '#': r'\#',
        '_': r'\_',
        '%': r'\%',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    return ''.join(replacements.get(char, char) for char in str(value or ''))


def _latex_paragraphs(value):
    """保留用户编辑后的段落结构，同时对每段执行 LaTeX 转义。"""
    normalized = str(value or '').replace('\r\n', '\n').replace('\r', '\n')
    blocks = normalized.split('\n\n')
    return '\n\n'.join(
        _latex_escape(block).replace('\n', r'\\' + '\n') for block in blocks
    )


def _markdown_escape(value):
    """把业务文本作为 Pandoc Markdown 的普通文本输出。"""
    text = str(value or '').replace('\\', r'\\')
    for char in ('*', '_', '[', ']', '<', '>', '#', '|'):
        text = text.replace(char, f'\\{char}')
    return text


def _load_export_material(case, template_type):
    """统一装载 PDF/Word 所需数据，始终读取用户编辑后的最新文书版本。"""
    from api.services.export_service import get_export_document
    from api.services.timeline_service import get_sorted_timeline

    return {
        'document': get_export_document(case, template_type),
        'timeline': list(get_sorted_timeline(case)),
        'evidences': list(
            case.evidences.all().prefetch_related('extracted_fields').order_by('order', 'id')
        ),
    }


def _original_image_path(evidence):
    """正式 PDF/Word 只使用用户上传的原图，不读取 masked_image。"""
    if not evidence.image:
        return None
    try:
        path = evidence.image.path
    except (ValueError, OSError):
        return None
    return path if os.path.isfile(path) else None


def build_latex_source(case, template_type='platform'):
    """构建可由 XeLaTeX 编译的中文正式文书源码。"""
    material = _load_export_material(case, template_type)
    document = material['document']
    document_label = '反证答辩正文' if case.case_mode == 'respond' else '投诉正文'
    signer_label = '答辩人' if case.case_mode == 'respond' else '投诉人'
    signer_name = case.owner.username if case.owner_id and case.owner.username else signer_label

    timeline_lines = []
    if material['timeline']:
        for node in material['timeline']:
            line = f'{_format_datetime(node.datetime)}  {node.event}'
            if node.related_evidence_codes:
                line += f'（见 {node.related_evidence_codes}）'
            timeline_lines.append(r'\item ' + _latex_escape(line))
    else:
        timeline_lines.append(r'\item 暂无已确认的时间线节点。')

    field_rows = []
    for evidence in material['evidences']:
        for field in evidence.extracted_fields.all():
            field_rows.append(
                f'{_latex_escape(field.field_name)} & '
                f'{_latex_escape(field.field_value)} & '
                f'{_latex_escape(evidence.code)} ' + r'\\ \hline'
            )
    fields = '\n'.join(field_rows) if field_rows else r'暂无 & 暂无已确认的结构化字段 & -- \\ \hline'

    evidence_blocks = []
    for evidence in material['evidences']:
        description = evidence.description or evidence.physical_note or evidence.ocr_summary or ''
        evidence_blocks.append(
            r'\noindent\textbf{' + _latex_escape(evidence.code) + '—' +
            _latex_escape(evidence.evidence_type) + '}\\\n' + _latex_paragraphs(description)
        )
        image_path = _original_image_path(evidence)
        if image_path:
            # detokenize 使空格等路径字符安全；路径来自服务端文件字段而非 LaTeX 命令。
            safe_path = image_path.replace('}', '')
            evidence_blocks.append(
                '\\begin{center}\n'
                f'\\includegraphics[width=0.86\\textwidth,height=8cm,keepaspectratio]'
                f'{{\\detokenize{{{safe_path}}}}}\n'
                '\\end{center}'
            )
        evidence_blocks.append(r'\medskip')

    return r'''\documentclass[UTF8,12pt,a4paper,fontset=fandol]{ctexart}
\usepackage[a4paper,top=2.4cm,bottom=2.3cm,left=2.6cm,right=2.6cm]{geometry}
\usepackage{graphicx,longtable,array,fancyhdr,lastpage,setspace,titlesec}
\usepackage[table]{xcolor}
\definecolor{ClaimGreen}{HTML}{244D3D}
\definecolor{ClaimGold}{HTML}{A58432}
\setstretch{1.45}
\setlength{\parindent}{2em}
\setlength{\parskip}{0.35em}
\titleformat{\section}{\large\bfseries\color{ClaimGreen}}{\chinese{section}、}{0.4em}{}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\color{gray} ClaimCraft 案件材料}
\fancyhead[R]{\small\color{gray} ''' + _latex_escape(case.title) + r'''}
\fancyfoot[C]{\small 第 \thepage 页，共 \pageref{LastPage} 页}
\renewcommand{\headrulewidth}{0.4pt}
\begin{document}
\begin{center}
{\zihao{2}\bfseries\color{ClaimGreen} ''' + _latex_escape(document['title']) + r'''}\\[0.5em]
{\small\color{gray} 案件编号：CC-''' + str(case.id) + r'''}
\end{center}
\vspace{0.6em}
\section{''' + document_label + r'''}
''' + _latex_paragraphs(document['content']) + r'''
\section{事实时间线}
\begin{enumerate}
''' + '\n'.join(timeline_lines) + r'''
\end{enumerate}
\section{关键信息}
\renewcommand{\arraystretch}{1.35}
\begin{longtable}{|>{\raggedright\arraybackslash}p{3cm}|>{\raggedright\arraybackslash}p{8cm}|p{2cm}|}
\hline
\rowcolor{ClaimGreen!10}\textbf{字段} & \textbf{值} & \textbf{证据} \\ \hline
''' + fields + r'''
\end{longtable}
\section{证据清单及原始图片}
''' + '\n'.join(evidence_blocks) + r'''
\vspace{1.2cm}
\begin{flushright}
''' + _latex_escape(signer_label) + '签名：' + _latex_escape(signer_name) + r'''\\[1em]
日期：\underline{\hspace{4cm}}
\end{flushright}
\end{document}
'''


def build_pandoc_markdown(case, template_type='platform'):
    """构建 Word 转换源；内容与 PDF 使用同一最新文书和原图策略。"""
    material = _load_export_material(case, template_type)
    document = material['document']
    label = '反证答辩正文' if case.case_mode == 'respond' else '投诉正文'
    lines = [
        f'% {_markdown_escape(document["title"])}',
        f'% 案件编号：CC-{case.id}',
        '',
        f'# {label}',
        '',
        _markdown_escape(document['content']),
        '',
        '# 事实时间线',
        '',
    ]
    if material['timeline']:
        for node in material['timeline']:
            line = f'{_format_datetime(node.datetime)}  {node.event}'
            if node.related_evidence_codes:
                line += f'（见 {node.related_evidence_codes}）'
            lines.append(f'1. {_markdown_escape(line)}')
    else:
        lines.append('1. 暂无已确认的时间线节点。')

    lines.extend(['', '# 关键信息', '', '| 字段 | 值 | 证据 |', '|---|---|---|'])
    has_fields = False
    for evidence in material['evidences']:
        for field in evidence.extracted_fields.all():
            has_fields = True
            lines.append(
                f'| {_markdown_escape(field.field_name)} | '
                f'{_markdown_escape(field.field_value)} | {_markdown_escape(evidence.code)} |'
            )
    if not has_fields:
        lines.append('| 暂无 | 暂无已确认的结构化字段 | -- |')

    lines.extend(['', '# 证据清单及原始图片', ''])
    for evidence in material['evidences']:
        description = evidence.description or evidence.physical_note or evidence.ocr_summary or ''
        lines.extend([
            f'## {_markdown_escape(evidence.code)}—{_markdown_escape(evidence.evidence_type)}',
            '',
            _markdown_escape(description),
            '',
        ])
        image_path = _original_image_path(evidence)
        if image_path:
            image_uri = Path(image_path).resolve().as_uri()
            lines.extend([f'![{_markdown_escape(evidence.code)} 原始图片]({image_uri}){{ width=85% }}', ''])

    signer_label = '答辩人' if case.case_mode == 'respond' else '投诉人'
    signer_name = case.owner.username if case.owner_id and case.owner.username else signer_label
    lines.extend(['', f'{signer_label}签名：{_markdown_escape(signer_name)}', '', '日期：________________'])
    return '\n'.join(lines)


def _run_converter(command, cwd, output_path, timeout):
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DocumentRenderError(f'服务器缺少文书转换工具：{command[0]}') from exc
    except subprocess.TimeoutExpired as exc:
        raise DocumentRenderError('文书转换超时，请稍后重试') from exc
    if result.returncode != 0 or not output_path.is_file():
        detail = (result.stderr or result.stdout or '未知错误')[-2000:]
        logger.error('文书转换失败 command=%s detail=%s', command[0], detail)
        raise DocumentRenderError('文书转换失败，请检查文书内容或服务器转换环境')


def generate_complaint_pdf(case, template_type='platform'):
    """使用 XeLaTeX 生成中文 PDF，且只嵌入原始证据图片。"""
    source = build_latex_source(case, template_type)
    with tempfile.TemporaryDirectory(prefix='claimcraft-pdf-') as tmp:
        workdir = Path(tmp)
        tex_path = workdir / 'document.tex'
        pdf_path = workdir / 'document.pdf'
        tex_path.write_text(source, encoding='utf-8')
        xelatex = os.environ.get('XELATEX_CMD', 'xelatex')
        command = [
            xelatex, '-interaction=nonstopmode', '-halt-on-error',
            '-no-shell-escape', '-output-directory', str(workdir), str(tex_path),
        ]
        # 编译两次以解析总页数、页眉页脚等交叉引用。
        _run_converter(command, workdir, pdf_path, timeout=120)
        _run_converter(command, workdir, pdf_path, timeout=120)
        return BytesIO(pdf_path.read_bytes())


def generate_word_document(case, template_type='platform'):
    """使用 Pandoc 生成可继续编辑的 DOCX，且只嵌入原始证据图片。"""
    markdown = build_pandoc_markdown(case, template_type)
    with tempfile.TemporaryDirectory(prefix='claimcraft-word-') as tmp:
        workdir = Path(tmp)
        source_path = workdir / 'document.md'
        output_path = workdir / 'document.docx'
        source_path.write_text(markdown, encoding='utf-8')
        pandoc = os.environ.get('PANDOC_CMD', 'pandoc')
        command = [
            pandoc, str(source_path), '--from=markdown', '--to=docx',
            '--standalone', '--resource-path', str(workdir), '--output', str(output_path),
        ]
        reference_doc = os.environ.get('PANDOC_REFERENCE_DOC')
        if reference_doc and os.path.isfile(reference_doc):
            command.extend(['--reference-doc', reference_doc])
        _run_converter(command, workdir, output_path, timeout=120)
        return BytesIO(output_path.read_bytes())
