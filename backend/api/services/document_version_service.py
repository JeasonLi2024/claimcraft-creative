# -*- coding: utf-8 -*-
"""文书版本服务（Task 4.1.2 / 4.1.3 / 4.1.4）。

提供 DocumentVersion 创建 / 版本号计算 / 段落重新生成等共享逻辑，
供 complaint_node / respond_complaint_node 与 DocumentParagraphRegenerateView 复用。

设计要点：
- get_next_version: 按 (case, document_type) 计算下一个版本号（自增）
- create_document_version: 包装 DocumentVersion.objects.create，自动计算 version
- regenerate_paragraph: 段落级重新生成，创建新 DocumentVersion
"""
from typing import Optional

from api.models import DocumentVersion
from api.agents.utils.paragraph_splitter import (
    merge_paragraphs_to_content,
    update_paragraph,
)


def get_next_version(case_id: int, document_type: str) -> int:
    """计算指定 case + document_type 的下一个版本号。

    版本号策略：取当前最大 version + 1（无历史记录则为 1）。

    Args:
        case_id: 案件 ID
        document_type: 文书类型（complaint / respond_complaint）

    Returns:
        下一个版本号（int，>= 1）
    """
    latest = (
        DocumentVersion.objects
        .filter(case_id=case_id, document_type=document_type)
        .order_by('-version')
        .first()
    )
    if latest is None:
        return 1
    return (latest.version or 0) + 1


def create_document_version(
    *,
    case,
    workflow_run=None,
    document_type: str,
    title: str,
    content: str,
    paragraphs: Optional[list] = None,
    changelog: str = '',
    created_by_type: str = 'ai',
    created_by_id: Optional[int] = None,
    workflow_version: str = '',
    complaint_template=None,
    respond_template=None,
) -> DocumentVersion:
    """创建文书版本记录（自动计算 version）。

    Args:
        case: 案件实例
        workflow_run: 关联的工作流运行（可空）
        document_type: complaint / respond_complaint
        title: 文书标题
        content: 正文内容
        paragraphs: 段落结构（list[dict]，可空）
        changelog: 变更说明
        created_by_type: ai / user / system
        created_by_id: 创建者 ID
        workflow_version: 生成时的工作流版本（审计字段）
        complaint_template: 关联投诉模板（可空）
        respond_template: 关联答辩模板（可空）

    Returns:
        DocumentVersion 实例
    """
    version = get_next_version(case.id, document_type)
    return DocumentVersion.objects.create(
        case=case,
        workflow_run=workflow_run,
        complaint_template=complaint_template,
        respond_template=respond_template,
        document_type=document_type,
        version=version,
        title=title,
        content=content,
        paragraphs=paragraphs if paragraphs is not None else [],
        changelog=changelog,
        created_by_type=created_by_type,
        created_by_id=created_by_id,
        workflow_version=workflow_version,
    )


def regenerate_paragraph(
    doc_version: DocumentVersion,
    paragraph_id: str,
    new_content: str,
    evidence_codes: Optional[list] = None,
    *,
    changelog: str = '',
    created_by_type: str = 'user',
    created_by_id: Optional[int] = None,
) -> tuple[DocumentVersion, dict, int]:
    """段落级重新生成：基于现有版本创建新版本，仅替换目标段落。

    Args:
        doc_version: 基础版本（新版本 = doc_version.version + 1）
        paragraph_id: 目标段落 ID（如 "p2"）
        new_content: 新段落正文
        evidence_codes: 新证据编号列表（None 表示保留原值）
        changelog: 变更说明
        created_by_type: 创建者类型（默认 user）
        created_by_id: 创建者 ID

    Returns:
        (new_doc, new_paragraph, target_idx)：
            - new_doc: 新 DocumentVersion 实例
            - new_paragraph: 更新后的段落 dict
            - target_idx: 更新的段落索引

    Raises:
        ValueError: doc_version.paragraphs 为空 或 paragraph_id 不存在
    """
    paragraphs = doc_version.paragraphs or []
    if not paragraphs:
        raise ValueError('文档版本段落结构为空，无法重新生成段落')

    new_paragraphs, target_idx = update_paragraph(
        paragraphs, paragraph_id, new_content, evidence_codes
    )
    if target_idx == -1:
        raise ValueError(f'段落 {paragraph_id} 不存在')

    new_content_full = merge_paragraphs_to_content(new_paragraphs)
    workflow_run = doc_version.workflow_run
    new_doc = DocumentVersion.objects.create(
        case=doc_version.case,
        workflow_run=workflow_run,
        complaint_template=doc_version.complaint_template,
        respond_template=doc_version.respond_template,
        document_type=doc_version.document_type,
        version=get_next_version(doc_version.case_id, doc_version.document_type),
        title=doc_version.title,
        content=new_content_full,
        paragraphs=new_paragraphs,
        changelog=changelog or f'段落 {paragraph_id} 重新生成',
        created_by_type=created_by_type,
        created_by_id=created_by_id,
        workflow_version=doc_version.workflow_version,
    )
    return new_doc, new_paragraphs[target_idx], target_idx


def get_latest_version(case_id: int, document_type: str) -> Optional[DocumentVersion]:
    """获取指定 case + document_type 的最新版本。"""
    return (
        DocumentVersion.objects
        .filter(case_id=case_id, document_type=document_type)
        .order_by('-version')
        .first()
    )
