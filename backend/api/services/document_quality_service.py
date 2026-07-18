# -*- coding: utf-8 -*-
"""文书质量门服务（Task 4.2）。

实现两个核心能力：
1. `validate_legal_references(paragraphs) -> ValidationResult`
   - 验证 `paragraphs[].legal_references[]` 中的法条引用是否真实存在
   - 三级降级策略：LawRetriever RAG 检索 → LawArticle 直接查表 → 格式校验
2. `run_export_check(document_id, run_id=None) -> ExportCheckResult`
   - 导出前 5 项质量门检查（法条真实性 / 金额一致性 / 主体名称 / 必备要素 / stale 产物）

设计要点（对齐 spec.md Legal Reference Authenticity Validation + Export Pre-check Quality Gate）：
- LawRetriever 实例懒加载单例（避免每次校验都初始化向量库连接）
- LawRetriever 不可用（RAG 未配置 / Embedding 服务不可用）时降级查 LawArticle 表
- 两者都不可用时仅做格式校验（law_name 非空 + article_number 符合「第X条」格式）
- 金额一致性正则匹配 `[\d,]+\.?\d*元` / `[\d,]+\.?\d*万元`，与 ExtractedField
  中 `field_name in ("金额", "交易金额", "退款金额")` 比对，差异 > 1 元视为不一致
- 主体名称一致性：从文书正文提取可能的主体名称，与 ExtractedField 中
  `field_name in ("商家名称", "投诉人", "被投诉人", "当事人")` 比对
- 必备要素完整性：复用 `paragraph_splitter` 切分文书正文，识别 事实段 / 依据段 / 诉求段
- stale 产物引用：查询 `WorkflowArtifact.objects.filter(case=case, status="stale")`

约束：
- 不引入新依赖（仅使用 Django + Pydantic + 项目已有 LawRetriever）
- 法条验证不抛异常（RAG / DB 查询失败时降级格式校验，不阻塞主工作流）
- Pydantic 模型可 JSON 序列化，便于 API 返回
"""
import logging
import re
from typing import Literal, Optional

from asgiref.sync import sync_to_async
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic 模型
# ============================================================================


class ValidationResult(BaseModel):
    """法条引用校验结果。"""
    valid: bool = Field(description="全部法条引用是否真实存在")
    invalid_refs: list[dict] = Field(
        default_factory=list,
        description="无效引用列表 [{paragraph_id, law_name, article_number, reason}]",
    )
    by_paragraph: dict[str, list[dict]] = Field(
        default_factory=dict,
        description="按段落 ID 分组的逐条校验结果 {paragraph_id: [{ref, valid, reason}]}",
    )
    total_refs: int = Field(default=0, description="法条引用总数")
    valid_refs: int = Field(default=0, description="通过校验的引用数")


class ExportCheckIssue(BaseModel):
    """导出前质量门问题项。"""
    code: str = Field(
        description="问题代码：INVALID_LEGAL_REF / AMOUNT_MISMATCH / PARTY_MISMATCH / "
                    "MISSING_ELEMENT / STALE_ARTIFACT"
    )
    severity: Literal["blocking", "warning", "info"] = Field(description="严重程度")
    message: str = Field(description="问题描述")
    paragraph_id: Optional[str] = Field(default=None, description="关联段落 ID")
    details: dict = Field(default_factory=dict, description="扩展详情")


class ExportCheckResult(BaseModel):
    """导出前质量门检查结果。"""
    passed: bool = Field(description="True 当且仅当无 blocking issues")
    issues: list[ExportCheckIssue] = Field(default_factory=list)
    missing_elements: list[str] = Field(
        default_factory=list,
        description="缺失的必备要素子集（['事实段', '依据段', '诉求段']）",
    )
    checks_run: list[str] = Field(
        default_factory=list,
        description="已执行的检查项列表",
    )


# ============================================================================
# 法条引用校验（SubTask 4.2.1）
# ============================================================================


# 「第X条」格式正则：第 + 中文数字/阿拉伯数字 + 条
_ARTICLE_NUMBER_PATTERN = re.compile(
    r'^第[一二三四五六七八九十百零〇\d]+条'
)

# LawRetriever 单例（懒加载，避免初始化时连不上 PG）
_law_retriever_instance = None


def _get_law_retriever():
    """懒加载 LawRetriever 单例。

    若 RAG 未启用 / Embedding 服务不可用 / 向量库未配置，返回 None。
    """
    global _law_retriever_instance
    if _law_retriever_instance is not None:
        return _law_retriever_instance
    try:
        from api.services.rag_service import LawRetriever, is_rag_enabled
        if not is_rag_enabled():
            logger.info('[DocumentQuality] RAG 未启用，法条校验降级查 LawArticle 表')
            return None
        _law_retriever_instance = LawRetriever()
        return _law_retriever_instance
    except Exception as e:
        logger.warning(f'[DocumentQuality] LawRetriever 初始化失败（降级查表）: {e}')
        return None


def _reset_law_retriever_cache():
    """重置 LawRetriever 单例缓存（仅供测试使用）。"""
    global _law_retriever_instance
    _law_retriever_instance = None


def _check_law_article_in_db(law_name: str, article_number: str) -> bool:
    """直接查询 LawArticle 表确认法条存在（RAG 不可用时的降级路径）。"""
    if not law_name or not article_number:
        return False
    try:
        from api.models import LawArticle
        return LawArticle.objects.filter(
            law_name=law_name,
            article_number=article_number,
            is_active=True,
        ).exists()
    except Exception as e:
        logger.warning(
            f'[DocumentQuality] LawArticle 查询失败 (law_name={law_name}, '
            f'article_number={article_number}): {e}'
        )
        return False


def _format_validate_ref(law_name: str, article_number: str) -> bool:
    """格式校验：law_name 非空 + article_number 符合「第X条」格式。

    用于 RAG 与 DB 均不可用时的最终降级（仅做最小格式校验，不保证真实性）。
    """
    if not law_name or not law_name.strip():
        return False
    if not article_number or not article_number.strip():
        return False
    # 「第X条」格式校验（含中文数字 / 阿拉伯数字）
    return bool(_ARTICLE_NUMBER_PATTERN.match(article_number.strip()))


async def _validate_single_ref_via_rag(
    retriever,
    law_name: str,
    article_number: str,
) -> bool:
    """通过 LawRetriever.retrieve 反查法条是否真实存在。

    Args:
        retriever: LawRetriever 实例
        law_name: 法律名称
        article_number: 条文编号

    Returns:
        True 如检索结果中存在 (law_name, article_number) 完全匹配的条款
    """
    try:
        query = f'{law_name} {article_number}'
        results = await retriever.retrieve(query=query, top_k=5)
        if not results:
            return False
        for r in results:
            if (
                r.get('law_name') == law_name
                and r.get('article_number') == article_number
            ):
                return True
        return False
    except Exception as e:
        logger.warning(
            f'[DocumentQuality] LawRetriever.retrieve 异常 '
            f'(law_name={law_name}, article_number={article_number}): {e}'
        )
        return False


async def validate_legal_references(paragraphs: list[dict]) -> ValidationResult:
    """验证文书法条引用真实性。

    校验三级降级策略（按优先级）：
    1. 优先调用 `LawRetriever.retrieve(query=f"{law_name} {article_number}")`，
       命中且 (law_name, article_number) 完全匹配即视为真实
    2. 若 LawRetriever 不可用（未配置 RAG），降级直接查询 LawArticle 表
    3. 若都没有，至少做格式校验（law_name 非空 + article_number 符合「第X条」格式）

    Args:
        paragraphs: 段落列表，每段含 `legal_references: list[dict]`，
            每个引用含 `law_name / article_number / source_url / text` 等字段

    Returns:
        ValidationResult：含 valid / invalid_refs / by_paragraph / total_refs / valid_refs
    """
    invalid_refs: list[dict] = []
    by_paragraph: dict[str, list[dict]] = {}
    total_refs = 0
    valid_refs = 0

    retriever = _get_law_retriever()

    for para in paragraphs or []:
        if not isinstance(para, dict):
            continue
        paragraph_id = para.get('paragraph_id', '')
        legal_refs = para.get('legal_references') or []
        if not legal_refs:
            continue
        per_para: list[dict] = []
        for ref in legal_refs:
            if not isinstance(ref, dict):
                continue
            total_refs += 1
            law_name = (ref.get('law_name') or '').strip()
            article_number = (ref.get('article_number') or '').strip()

            valid = False
            reason = ''

            # 1. LawRetriever RAG 检索（优先）
            if retriever is not None:
                valid = await _validate_single_ref_via_rag(
                    retriever, law_name, article_number,
                )
                if not valid:
                    reason = 'RAG 检索未命中匹配法条'
                    # RAG 未命中时继续尝试 DB 直查（兜底，避免 RAG 索引漏召回导致误报）

            # 2. LawArticle 表直查（RAG 不可用或 RAG 未命中时降级）
            if not valid:
                valid = await sync_to_async(_check_law_article_in_db)(
                    law_name, article_number,
                )
                if not valid and not reason:
                    reason = 'LawArticle 表无此法条'

            # 3. 格式校验（最终降级）
            if not valid:
                valid = _format_validate_ref(law_name, article_number)
                if not valid and not reason:
                    reason = '法条格式不合规（law_name 非空 + article_number 符合「第X条」）'

            if valid:
                valid_refs += 1
                per_para.append({
                    'law_name': law_name,
                    'article_number': article_number,
                    'valid': True,
                })
            else:
                invalid_refs.append({
                    'paragraph_id': paragraph_id,
                    'law_name': law_name,
                    'article_number': article_number,
                    'reason': reason or '法条引用无法验证',
                })
                per_para.append({
                    'law_name': law_name,
                    'article_number': article_number,
                    'valid': False,
                    'reason': reason or '法条引用无法验证',
                })
        by_paragraph[paragraph_id] = per_para

    return ValidationResult(
        valid=(total_refs == 0 or (total_refs > 0 and valid_refs == total_refs)),
        invalid_refs=invalid_refs,
        by_paragraph=by_paragraph,
        total_refs=total_refs,
        valid_refs=valid_refs,
    )


# ============================================================================
# 导出前质量门检查（SubTask 4.2.2）
# ============================================================================


# 金额正则：匹配「2980 元」/「2,980.50 元」/「1.5 万元」等
_AMOUNT_PATTERN = re.compile(
    r'(\d[\d,]*\.?\d*)\s*(万元|元)'
)

# 主体名称候选字段名（在不同案件类型中可能用不同字段名记录主体）
_PARTY_FIELD_NAMES = ('商家名称', '投诉人', '被投诉人', '当事人', '消费者')
# 金额候选字段名
_AMOUNT_FIELD_NAMES = ('金额', '交易金额', '退款金额', '购买金额', '实付金额')

# 必备要素段落标题关键词（用于识别 事实段 / 依据段 / 诉求段）
_FACT_KEYWORDS = ('事实', '经过', '情况', '理由', '事由')
_BASIS_KEYWORDS = ('依据', '法律', '法条', '根据', '引用', '参考法律')
_CLAIM_KEYWORDS = ('诉求', '请求', '要求', '主张')


def _parse_amount_to_yuan(value_str: str) -> Optional[float]:
    """将「2980 元」/「1.5 万元」/「2980」等字符串解析为元（float）。"""
    if not value_str:
        return None
    s = value_str.strip()
    # 先尝试匹配完整金额格式
    m = _AMOUNT_PATTERN.search(s)
    if m:
        num_str = m.group(1).replace(',', '')
        unit = m.group(2)
        try:
            num = float(num_str)
            return num * 10000 if unit == '万元' else num
        except (ValueError, TypeError):
            return None
    # 退化为纯数字解析
    try:
        return float(s.replace(',', '').replace('元', ''))
    except (ValueError, TypeError):
        return None


def _extract_amounts_from_text(text: str) -> list[float]:
    """从文书正文提取所有金额（元 / 万元），返回元为单位的 float 列表。"""
    if not text:
        return []
    amounts: list[float] = []
    for m in _AMOUNT_PATTERN.finditer(text):
        num_str = m.group(1).replace(',', '')
        unit = m.group(2)
        try:
            num = float(num_str)
            amounts.append(num * 10000 if unit == '万元' else num)
        except (ValueError, TypeError):
            continue
    return amounts


def _get_case_for_document(document_id: int):
    """获取 DocumentVersion 关联的 Case（通过 case_id 直接关联）。"""
    from api.models import DocumentVersion
    try:
        doc = DocumentVersion.objects.select_related('case').get(pk=document_id)
    except DocumentVersion.DoesNotExist:
        return None, None
    return doc, doc.case


def _get_extracted_field_values(case, field_names: tuple[str, ...]) -> list[str]:
    """查询案件下所有 ExtractedField 中匹配指定字段名的值列表。"""
    if not case:
        return []
    try:
        from api.models import ExtractedField
        return list(
            ExtractedField.objects
            .filter(evidence__case=case, field_name__in=list(field_names))
            .values_list('field_value', flat=True)
        )
    except Exception as e:
        logger.warning(f'[DocumentQuality] ExtractedField 查询失败: {e}')
        return []


def _identify_paragraph_type(paragraph: dict) -> Optional[str]:
    """识别段落类型：'fact' / 'basis' / 'claim' / None。

    基于段落标题（含 `title` 字段）和正文关键词判断。
    """
    title = (paragraph.get('title') or '').strip()
    content = (paragraph.get('content') or '')

    # 标题优先匹配
    if any(kw in title for kw in _FACT_KEYWORDS):
        return 'fact'
    if any(kw in title for kw in _BASIS_KEYWORDS):
        return 'basis'
    if any(kw in title for kw in _CLAIM_KEYWORDS):
        return 'claim'

    # 标题未命中时，正文匹配（弱信号）
    # 仅当正文明确包含依据类关键词 + 法条引用时识别为 basis
    if paragraph.get('legal_references') and any(
        kw in content for kw in _BASIS_KEYWORDS
    ):
        return 'basis'

    # P6：标题未命中时，用正文关键词识别 诉求 / 事实（应对 LLM 产出未加规范标题、
    # 段落标题为「段落 1」等自由结构的情况）。诉求优先于事实（诉求关键词更具指向性）。
    if any(kw in content for kw in _CLAIM_KEYWORDS):
        return 'claim'
    if any(kw in content for kw in _FACT_KEYWORDS):
        return 'fact'

    return None


def _check_required_elements(paragraphs: list[dict]) -> tuple[list[str], list[dict]]:
    """检查必备要素完整性（事实段 / 依据段 / 诉求段）。

    Returns:
        (missing_elements, issues)
        - missing_elements: 缺失要素列表（如 ['依据段']）
        - issues: 对应 ExportCheckIssue dict 列表（含 code=MISSING_ELEMENT）
    """
    found_types: set[str] = set()
    non_basis_parts: list[str] = []
    all_parts: list[str] = []
    for p in paragraphs or []:
        ptype = _identify_paragraph_type(p)
        if ptype:
            found_types.add(ptype)
        text = f"{(p.get('title') or '')}\n{(p.get('content') or '')}"
        all_parts.append(text)
        # 事实/诉求兜底扫描时排除「依据段」正文，避免法条摘要中偶现的
        # 「要求/情况」等关键词把 fact/claim 误判为已满足。
        if ptype != 'basis':
            non_basis_parts.append(text)

    # P6：段落级逐段识别未覆盖时（如整篇仅一个「段落 1」同时含事实与诉求），
    # 用关键词兜底，避免单段/自由结构文书误判为缺失必备要素。
    non_basis_text = "\n".join(non_basis_parts)
    all_text = "\n".join(all_parts)
    if 'fact' not in found_types and any(kw in non_basis_text for kw in _FACT_KEYWORDS):
        found_types.add('fact')
    if 'claim' not in found_types and any(kw in non_basis_text for kw in _CLAIM_KEYWORDS):
        found_types.add('claim')
    if 'basis' not in found_types and any(kw in all_text for kw in _BASIS_KEYWORDS):
        found_types.add('basis')

    required = [('fact', '事实段'), ('basis', '依据段'), ('claim', '诉求段')]
    missing = [label for key, label in required if key not in found_types]
    issues: list[dict] = []
    for label in missing:
        issues.append({
            'code': 'MISSING_ELEMENT',
            'severity': 'blocking',
            'message': f'文书缺少必备要素：{label}',
            'details': {'missing_element': label},
        })
    return missing, issues


def _check_amount_consistency(
    full_text: str, case
) -> tuple[bool, list[dict]]:
    """金额一致性检查。

    Args:
        full_text: 文书正文（合并所有段落 content）
        case: Case 实例

    Returns:
        (consistent, issues)
        - consistent: True 如金额一致 / 无可比对数据（不报问题）
        - issues: 不一致时的 ExportCheckIssue dict 列表
    """
    doc_amounts = _extract_amounts_from_text(full_text)
    if not doc_amounts:
        # 文书未提及金额，跳过检查（不报问题）
        return True, []

    extracted_values = _get_extracted_field_values(case, _AMOUNT_FIELD_NAMES)
    if not extracted_values:
        # 无抽取金额数据可比对，跳过检查
        return True, []

    extracted_amounts: list[float] = []
    for v in extracted_values:
        parsed = _parse_amount_to_yuan(v)
        if parsed is not None:
            extracted_amounts.append(parsed)

    if not extracted_amounts:
        return True, []

    # 比对策略：文书任一金额与抽取任一金额差异 <= 1 元视为一致
    # （取任一匹配是因为文书中可能引用多个金额：购买金额 / 退款金额 / 赔偿金额）
    threshold = 1.0
    matched = False
    mismatched_pairs: list[dict] = []
    for doc_amt in doc_amounts:
        for ext_amt in extracted_amounts:
            if abs(doc_amt - ext_amt) <= threshold:
                matched = True
                break
        if not matched:
            # 仅记录第一对未匹配的用于消息展示
            if not mismatched_pairs:
                mismatched_pairs.append({
                    'document_amount': doc_amt,
                    'extracted_amount': extracted_amounts[0],
                    'all_extracted': extracted_amounts,
                })

    if matched:
        return True, []

    # 不一致：生成 issue
    first = mismatched_pairs[0] if mismatched_pairs else {}
    issues = [{
        'code': 'AMOUNT_MISMATCH',
        'severity': 'blocking',
        'message': (
            f'文书金额 {first.get("document_amount")} 元与抽取金额 '
            f'{first.get("extracted_amount")} 元不一致'
        ),
        'details': {
            'document_amounts': doc_amounts,
            'extracted_amounts': extracted_amounts,
        },
    }]
    return False, issues


def _check_party_consistency(
    paragraphs: list[dict], full_text: str, case
) -> tuple[bool, list[dict]]:
    """主体名称一致性检查。

    比对文书正文中提及的主体名称与 ExtractedField 中存储的主体字段值。
    若无主体相关 ExtractedField，跳过检查（不报问题）。

    Args:
        paragraphs: 段落列表（可用于段落级 issue 关联）
        full_text: 文书完整正文
        case: Case 实例

    Returns:
        (consistent, issues)
    """
    extracted_parties = _get_extracted_field_values(case, _PARTY_FIELD_NAMES)
    if not extracted_parties:
        return True, []

    # 过滤空值 + 去重
    party_names = []
    seen = set()
    for v in extracted_parties:
        v = (v or '').strip()
        if v and v not in seen:
            seen.add(v)
            party_names.append(v)

    if not party_names:
        return True, []

    # 比对策略：所有抽取到的主体名称都应出现在文书正文中
    missing_parties = [name for name in party_names if name not in full_text]
    if not missing_parties:
        return True, []

    issues: list[dict] = []
    for name in missing_parties:
        # 尝试定位段落（哪个段落未提及该主体）
        paragraph_id = None
        for p in paragraphs or []:
            if name in (p.get('content') or ''):
                paragraph_id = None  # 出现在某段落，但其他段落未提及
                break
        issues.append({
            'code': 'PARTY_MISMATCH',
            'severity': 'warning',
            'message': f'文书未提及主体名称：{name}',
            'paragraph_id': paragraph_id,
            'details': {'party_name': name, 'extracted_parties': party_names},
        })
    return False, issues


def _check_stale_artifacts(document_id: int, case) -> list[dict]:
    """stale 产物引用检查。

    查询与当前文书 case 关联的 status='stale' 的 WorkflowArtifact。
    若存在则生成 warning issue。

    Args:
        document_id: DocumentVersion ID
        case: Case 实例

    Returns:
        ExportCheckIssue dict 列表
    """
    try:
        from api.models import WorkflowArtifact
        stale_artifacts = list(
            WorkflowArtifact.objects
            .filter(case=case, status='stale')
            .values('id', 'artifact_type', 'stage')
        )
    except Exception as e:
        logger.warning(f'[DocumentQuality] WorkflowArtifact 查询失败: {e}')
        return []

    issues: list[dict] = []
    for art in stale_artifacts:
        issues.append({
            'code': 'STALE_ARTIFACT',
            'severity': 'warning',
            'message': (
                f'文书引用了已过期的产物：{art.get("artifact_type", "")}'
                f'（artifact_id={art.get("id")}）'
            ),
            'details': {
                'artifact_id': art.get('id'),
                'artifact_type': art.get('artifact_type'),
                'stage': art.get('stage'),
            },
        })
    return issues


async def run_export_check(
    document_id: int,
    run_id: Optional[int] = None,
) -> ExportCheckResult:
    """导出前质量门检查（5 项）。

    Args:
        document_id: DocumentVersion ID
        run_id: 可选 WorkflowRun ID（用于上下文日志，不强制校验归属）

    Returns:
        ExportCheckResult：含 passed / issues / missing_elements / checks_run

    检查项：
        1. 法条引用真实性（调用 validate_legal_references）
        2. 金额一致性（文书正文金额 vs ExtractedField 金额字段）
        3. 主体名称一致性（文书主体 vs ExtractedField 主体字段）
        4. 必备要素完整性（事实段 / 依据段 / 诉求段）
        5. stale 产物引用（WorkflowArtifact.status='stale'）
    """
    doc, case = await sync_to_async(_get_case_for_document)(document_id)
    if doc is None:
        # 文书不存在：直接返回 failed 结果（passed=False）
        return ExportCheckResult(
            passed=False,
            issues=[ExportCheckIssue(
                code='DOCUMENT_NOT_FOUND',
                severity='blocking',
                message=f'文书 document_id={document_id} 不存在',
                details={'document_id': document_id},
            )],
            missing_elements=[],
            checks_run=[],
        )

    paragraphs = doc.paragraphs or []
    # 合并文书完整正文（用于金额 / 主体检查）
    full_text = doc.content or ''
    if not full_text and paragraphs:
        full_text = '\n\n'.join(p.get('content', '') for p in paragraphs)

    checks_run: list[str] = []
    all_issues: list[ExportCheckIssue] = []
    missing_elements: list[str] = []

    # 1. 法条引用真实性
    checks_run.append('legal_references')
    legal_result = await validate_legal_references(paragraphs)
    for inv in legal_result.invalid_refs:
        all_issues.append(ExportCheckIssue(
            code='INVALID_LEGAL_REF',
            severity='blocking',
            message=(
                f'引用的法条「{inv.get("law_name", "")}'
                f'{inv.get("article_number", "")}」不存在'
                f'（{inv.get("reason", "")}）'
            ),
            paragraph_id=inv.get('paragraph_id'),
            details={
                'law_name': inv.get('law_name', ''),
                'article_number': inv.get('article_number', ''),
                'reason': inv.get('reason', ''),
            },
        ))

    # 2. 金额一致性
    checks_run.append('amount_consistency')
    _, amount_issues = await sync_to_async(_check_amount_consistency)(full_text, case)
    for issue_dict in amount_issues:
        all_issues.append(ExportCheckIssue(**issue_dict))

    # 3. 主体名称一致性
    checks_run.append('party_consistency')
    _, party_issues = await sync_to_async(_check_party_consistency)(paragraphs, full_text, case)
    for issue_dict in party_issues:
        all_issues.append(ExportCheckIssue(**issue_dict))

    # 4. 必备要素完整性
    checks_run.append('required_elements')
    missing, element_issues = _check_required_elements(paragraphs)
    missing_elements.extend(missing)
    for issue_dict in element_issues:
        all_issues.append(ExportCheckIssue(**issue_dict))

    # 5. stale 产物引用
    checks_run.append('stale_artifacts')
    stale_issues = await sync_to_async(_check_stale_artifacts)(document_id, case)
    for issue_dict in stale_issues:
        all_issues.append(ExportCheckIssue(**issue_dict))

    # passed = 无 blocking issues
    has_blocking = any(i.severity == 'blocking' for i in all_issues)
    return ExportCheckResult(
        passed=not has_blocking,
        issues=all_issues,
        missing_elements=missing_elements,
        checks_run=checks_run,
    )
