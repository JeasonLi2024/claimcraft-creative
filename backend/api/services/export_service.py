# -*- coding: utf-8 -*-
"""案件文本与证据包导出服务。"""
import io
import json
import os
import re
import zipfile

from django.utils import timezone

from api.services import complaint_service, mask_service, timeline_service

_SAFE_ARCHIVE_NAME = re.compile(r'[^0-9A-Za-z._-]+')


def get_export_document(case, template_type='platform'):
    """返回当前案件应导出的最新文书。

    优先使用用户可能已经编辑过的最新 DocumentVersion；不存在版本记录时，
    再按案件模式回退到 ComplaintTemplate/RespondTemplate/Jinja2 生成服务。
    """
    from api.models import DocumentVersion

    document_type = 'respond_complaint' if case.case_mode == 'respond' else 'complaint'
    versions = DocumentVersion.objects.filter(
        case=case,
        document_type=document_type,
    ).select_related('complaint_template', 'respond_template').order_by('-version', '-id')

    for version in versions:
        related_template = (
            version.respond_template
            if document_type == 'respond_complaint'
            else version.complaint_template
        )
        if related_template is None or related_template.template_type == template_type:
            return {
                'title': version.title or ('反证答辩书' if case.case_mode == 'respond' else '投诉书'),
                'content': version.content,
                'template_type': template_type,
                'document_version_id': version.id,
                'version': version.version,
            }

    if case.case_mode == 'respond':
        return complaint_service.generate_respond_complaint(case, template_type)
    return complaint_service.generate_complaint(case, template_type)


def _format_datetime(value):
    """格式化可为空的时间，避免未识别时间导致整个导出失败。"""
    return value.strftime('%Y-%m-%d %H:%M') if value else '时间待确认'


def _safe_archive_filename(value, fallback):
    """将用户可编辑的证据编号转换为安全的 ZIP 内文件名。"""
    basename = os.path.basename(str(value or '').replace('\\', '/')).strip()
    safe = _SAFE_ARCHIVE_NAME.sub('_', basename).strip('._')
    return (safe or fallback)[:80]


def generate_export_text(case, template_type='platform', masked=False):
    """生成包含文书、证据清单和时间线的 UTF-8 文本。"""
    lines = []
    document = get_export_document(case, template_type)
    title = document['title']
    content = document['content']
    if masked:
        title = mask_service.mask_text(title)
        content = mask_service.mask_text(content)

    document_label = '反证答辩书' if case.case_mode == 'respond' else '投诉文本'
    lines.extend([
        '=' * 60,
        f'一、{document_label}',
        '=' * 60,
        f'【标题】{title}',
        '',
        '【正文】',
        content,
        '',
        '=' * 60,
        '二、证据清单',
        '=' * 60,
    ])

    evidences = case.evidences.order_by('order', 'id')
    for ev in evidences:
        desc = mask_service.mask_text(ev.description) if masked else ev.description
        evidence_type = (
            mask_service.mask_text(ev.evidence_type) if masked else ev.evidence_type
        )
        sensitive_flag = '（含敏感信息）' if ev.has_sensitive_info else ''
        lines.append(f'[{ev.code}] 类型：{evidence_type}{sensitive_flag}')
        lines.append(f'    时间：{_format_datetime(ev.source_time)}')
        lines.append(f'    描述：{desc}')
        lines.append('')

    lines.extend(['=' * 60, '三、时间线', '=' * 60])
    for node in timeline_service.get_sorted_timeline(case):
        event = mask_service.mask_text(node.event) if masked else node.event
        related_codes = (
            mask_service.mask_text(node.related_evidence_codes)
            if masked else node.related_evidence_codes
        )
        related = f'（关联证据：{related_codes}）' if related_codes else ''
        lines.append(f'[{_format_datetime(node.datetime)}] {event}{related}')
        lines.append('')

    return '\n'.join(lines)


def export_evidence_package(case, template_type='platform'):
    """生成包含原始素材、时间线和文书正文的 ZIP，返回 BytesIO。

    压缩包稳定契约：
    - complaint.txt：当前案件模式下、指定模板的最新文书正文；
    - timeline.txt：按时间和人工顺序整理的时间线；
    - images/：用户上传的原始素材图片；
    - images/masked/：用户此前已生成的打码图片，文件名带 masked 标记；
    - evidence_list.txt：图片编号、类型、原图和打码图索引；
    - manifest.json：文件映射、文书版本及缺失素材信息。
    """
    buf = io.BytesIO()
    document = get_export_document(case, template_type)
    evidences = list(case.evidences.all().order_by('order', 'id'))
    nodes = timeline_service.get_sorted_timeline(case)
    generated_at = timezone.now().isoformat()
    manifest = {
        'schema_version': 1,
        'case_id': case.id,
        'case_title': case.title,
        'generated_at': generated_at,
        'template_type': template_type,
        'document_type': 'respond_complaint' if case.case_mode == 'respond' else 'complaint',
        'document_filename': 'complaint.txt',
        'document_version_id': document.get('document_version_id'),
        'document_version': document.get('version'),
        'timeline_filename': 'timeline.txt',
        'image_policy': 'original_and_existing_masked',
        'images': [],
        'missing_images': [],
    }

    complaint_text = '\n'.join([
        document['title'],
        '',
        document['content'],
        '',
    ])
    timeline_lines = [
        f'案件：{case.title}',
        f'导出时间：{generated_at}',
        '',
        '时间线梳理',
        '=' * 60,
    ]
    if not nodes:
        timeline_lines.append('暂无时间线节点。')
    for index, node in enumerate(nodes, start=1):
        timeline_lines.extend([
            f'{index}. {_format_datetime(node.datetime)}',
            f'   事件：{node.event}',
            f'   关联证据：{node.related_evidence_codes or "无"}',
            '',
        ])

    evidence_lines = [
        f'案件：{case.title}',
        '',
        '证据编号 | 类型 | 描述 | 原始图片 | 打码图片',
        '-' * 60,
    ]

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 文本增加 UTF-8 BOM，兼容 Windows 直接打开时的中文识别。
        zf.writestr('complaint.txt', complaint_text.encode('utf-8-sig'))
        zf.writestr('timeline.txt', '\n'.join(timeline_lines).encode('utf-8-sig'))

        for index, ev in enumerate(evidences, start=1):
            if not ev.image:
                evidence_lines.append(
                    f'{ev.code} | {ev.evidence_type} | {ev.description[:120]} | 无 | 无'
                )
                continue

            try:
                image_path = ev.image.path
            except (ValueError, OSError) as exc:
                manifest['missing_images'].append({
                    'evidence_id': ev.id,
                    'code': ev.code,
                    'reason': f'无法解析原始文件路径：{exc}',
                })
                evidence_lines.append(
                    f'{ev.code} | {ev.evidence_type} | {ev.description[:120]} | 文件不可用 | 无'
                )
                continue

            original_name = os.path.basename(ev.image.name or image_path)
            if not os.path.isfile(image_path):
                manifest['missing_images'].append({
                    'evidence_id': ev.id,
                    'code': ev.code,
                    'original_filename': original_name,
                    'reason': '原始媒体文件不存在',
                })
                evidence_lines.append(
                    f'{ev.code} | {ev.evidence_type} | {ev.description[:120]} | 文件缺失 | 无'
                )
                continue

            ext = os.path.splitext(original_name)[1].lower()
            if not ext:
                ext = os.path.splitext(image_path)[1].lower() or '.jpg'
            safe_code = _safe_archive_filename(ev.code, f'evidence_{index}')
            filename = f'{index:03d}_{safe_code}{ext}'
            archive_path = f'images/{filename}'
            zf.write(image_path, arcname=archive_path)
            manifest['images'].append({
                'evidence_id': ev.id,
                'code': ev.code,
                'original_filename': original_name,
                'filename': filename,
                'archive_path': archive_path,
                'source': 'original_upload',
                'size': os.path.getsize(image_path),
            })
            masked_archive_path = '无'
            if ev.mask_status == 'done' and ev.masked_image:
                try:
                    masked_path = ev.masked_image.path
                    masked_original_name = os.path.basename(
                        ev.masked_image.name or masked_path
                    )
                    if os.path.isfile(masked_path):
                        masked_ext = os.path.splitext(masked_original_name)[1].lower() or '.jpg'
                        masked_filename = f'{index:03d}_{safe_code}_masked{masked_ext}'
                        masked_archive_path = f'images/masked/{masked_filename}'
                        zf.write(masked_path, arcname=masked_archive_path)
                        manifest['images'].append({
                            'evidence_id': ev.id,
                            'code': ev.code,
                            'original_filename': masked_original_name,
                            'filename': masked_filename,
                            'archive_path': masked_archive_path,
                            'source': 'masked_derivative',
                            'size': os.path.getsize(masked_path),
                        })
                    else:
                        manifest['missing_images'].append({
                            'evidence_id': ev.id,
                            'code': ev.code,
                            'original_filename': masked_original_name,
                            'source': 'masked_derivative',
                            'reason': '打码图片文件不存在',
                        })
                except (ValueError, OSError) as exc:
                    manifest['missing_images'].append({
                        'evidence_id': ev.id,
                        'code': ev.code,
                        'source': 'masked_derivative',
                        'reason': f'无法解析打码图片路径：{exc}',
                    })
            evidence_lines.append(
                f'{ev.code} | {ev.evidence_type} | {ev.description[:120]} | '
                f'{archive_path} | {masked_archive_path}'
            )

        manifest['image_count'] = len(manifest['images'])
        manifest['original_image_count'] = sum(
            item['source'] == 'original_upload' for item in manifest['images']
        )
        manifest['masked_image_count'] = sum(
            item['source'] == 'masked_derivative' for item in manifest['images']
        )
        manifest['missing_image_count'] = len(manifest['missing_images'])
        zf.writestr('evidence_list.txt', '\n'.join(evidence_lines).encode('utf-8-sig'))
        zf.writestr(
            'manifest.json',
            json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'),
        )

    buf.seek(0)
    return buf
