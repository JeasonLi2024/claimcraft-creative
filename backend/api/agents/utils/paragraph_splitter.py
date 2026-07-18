# -*- coding: utf-8 -*-
"""文书段落切分工具（Task 4.1.3）。

将 LLM 生成的文书正文（Markdown 格式）按段落标题切分为结构化段落列表，
每段含 content / evidence_codes / legal_references / source_regions。

设计选择（对齐 spec.md 阶段 4 推荐选项 B）：
- 不修改 LLM prompt 避免回归
- 在节点输出层做后处理，按段落标题切分 + 关键词匹配 evidence_codes / legal_references

段落边界识别（按优先级）：
1. Markdown 标题：`# ` / `## ` / `### `
2. 中文序号：`一、` / `二、` ... / `十一、` 等
3. 阿拉伯数字序号：`1.` / `2.` ... （行首）
4. 「第X条」模式

每段结构：
    {
        "paragraph_id": "p1",
        "title": "当事人信息",
        "content": "投诉人：张三...",
        "evidence_codes": ["E1", "E2"],
        "legal_references": [{"law_name": "...", "article_number": "..."}],
        "source_regions": []
    }
"""
import re
from typing import Any

# 段落标题正则：
# - Markdown 标题（#/##/###）
# - 中文序号（一、二、...、十、十一、...）
# - 阿拉伯数字序号（1. / 2. / 01. 等，行首）
# - 「第X条」模式
_PARAGRAPH_TITLE_PATTERN = re.compile(
    r'^\s*('
    r'#{1,3}\s+.+'                # Markdown 标题
    r'|[一二三四五六七八九十百]+、.+'  # 中文序号
    r'|\d+[\.、].+'                # 阿拉伯数字序号
    r'|第[一二三四五六七八九十百零\d]+条.*'
    r')\s*$'
)

# 证据编号正则：E1 / E2 / EV001 / EV002 等
_EVIDENCE_CODE_PATTERN = re.compile(r'\bE\d+\b|\bEV\d+\b')

# 中文数字映射（用于「第X条」解析，预留扩展）
_CHINESE_NUM_MAP = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
}


def _extract_evidence_codes(text: str, available_codes: list[str]) -> list[str]:
    """从段落正文中提取出现的证据编号。

    Args:
        text: 段落正文
        available_codes: 当前案件可用的证据编号列表（用于过滤误匹配）

    Returns:
        去重后的证据编号列表（保持首次出现顺序）
    """
    if not text:
        return []
    found = _EVIDENCE_CODE_PATTERN.findall(text)
    if not found:
        return []
    # 仅保留在 available_codes 中存在的（避免误匹配如 "E1" 出现在无关上下文）
    # 若 available_codes 为空（无法预知），则保留全部匹配
    available_set = set(available_codes) if available_codes else None
    seen: set[str] = set()
    result: list[str] = []
    for code in found:
        if available_set is not None and code not in available_set:
            continue
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


def _match_legal_references(text: str, legal_refs: list[dict]) -> list[dict]:
    """匹配段落正文中引用的法条。

    匹配规则：段落数据来源法条列表中任一法条的 law_name 或 article_number
    出现在段落正文中，则视为该段落引用了此法条。

    Args:
        text: 段落正文
        legal_refs: 法条列表 [{law_name, article_number, ...}]

    Returns:
        匹配到的法条列表（深拷贝，避免污染入参）
    """
    if not text or not legal_refs:
        return []
    matched: list[dict] = []
    for ref in legal_refs:
        law_name = ref.get('law_name', '') or ''
        article_number = ref.get('article_number', '') or ''
        # 至少匹配 law_name 或 article_number 之一
        if (law_name and law_name in text) or (
            article_number and article_number in text
        ):
            matched.append(dict(ref))
    return matched


def _strip_title_prefix(title: str) -> str:
    """去除标题前缀（#/序号），保留可读标题文本。"""
    if not title:
        return ''
    t = title.strip()
    # Markdown 标题
    if t.startswith('#'):
        return re.sub(r'^#{1,3}\s+', '', t).strip()
    # 中文序号 / 阿拉伯数字序号 / 第X条：去掉前缀，保留描述
    # 例如 "一、当事人信息" → "当事人信息"
    m = re.match(
        r'^([一二三四五六七八九十百]+、|\d+[\.、]|第[一二三四五六七八九十百零\d]+条[、:：\.]?)\s*(.*)',
        t,
    )
    if m:
        return m.group(2).strip()
    return t


def finalize_legal_document(
    content: str,
    references: list[dict] | None,
    signer_name: str,
) -> str:
    """在文书正文末尾追加「法律依据」与「署名」两节（若尚未存在）。

    - 法律依据：列出所有引用到的真实法律条文（来自法律数据库检索/工具调用），
      满足「文书须注明引用到的全部条文」的要求；标题含「法律/依据」关键词，
      使导出前质量门可识别为「依据段」。
    - 署名：文书落款。

    references 每项为 dict，含 law_name / article_number / summary / content / source_url。
    幂等：已存在「法律依据」或「参考法律文件」小节时不重复追加。
    """
    text = (content or "").strip()
    has_basis_section = ("## 法律依据" in text) or ("## 参考法律文件" in text)
    valid_refs = [r for r in (references or []) if isinstance(r, dict)]
    if valid_refs and not has_basis_section:
        lines = ["## 法律依据"]
        for ref in valid_refs:
            title = "《{}》{}".format(
                ref.get("law_name", ""), ref.get("article_number", "")
            )
            summary = ref.get("summary") or ref.get("content") or ""
            source = ref.get("source_url") or "本地法律文献数据库"
            lines.append(f"- **{title}**：{summary}（来源：{source}）")
        text = f"{text}\n\n" + "\n".join(lines)
    if signer_name and "## 署名" not in text:
        text = f"{text}\n\n## 署名\n{signer_name}"
    return text.strip()


def split_into_paragraphs(
    content: str,
    evidence_codes: list[str] | None = None,
    legal_references: list[dict] | None = None,
) -> list[dict]:
    """将 LLM 生成的文书内容按段落标题切分为结构化段落。

    Args:
        content: 文书正文（Markdown 格式）
        evidence_codes: 当前案件可用的证据编号列表（用于段落 evidence_codes 匹配过滤）
        legal_references: 文书引用的法条列表（用于段落 legal_references 匹配）

    Returns:
        段落字典列表，每段含：
            - paragraph_id: "p1", "p2", ...
            - title: 段落标题（去除前缀）
            - content: 段落正文（含标题行）
            - evidence_codes: 该段落引用的证据编号
            - legal_references: 该段落引用的法条
            - source_regions: 段落来源区域（默认空，由上游证据链接填充）
    """
    if not content or not content.strip():
        return []

    avail_codes = evidence_codes or []
    legal_refs = legal_references or []

    lines = content.splitlines()
    paragraphs: list[dict] = []
    current_lines: list[str] = []
    current_title: str | None = None
    has_header = False

    def _flush():
        nonlocal current_lines, current_title
        if not current_lines:
            return
        body = '\n'.join(current_lines).strip()
        if not body:
            current_lines = []
            current_title = None
            return
        title = current_title or f'段落 {len(paragraphs) + 1}'
        paragraphs.append({
            'paragraph_id': f'p{len(paragraphs) + 1}',
            'title': title,
            'content': body,
            'evidence_codes': _extract_evidence_codes(body, avail_codes),
            'legal_references': _match_legal_references(body, legal_refs),
            'source_regions': [],
        })
        current_lines = []
        current_title = None

    for line in lines:
        if _PARAGRAPH_TITLE_PATTERN.match(line):
            # 遇到新段落标题，先 flush 上一段
            _flush()
            has_header = True
            current_title = _strip_title_prefix(line)
            current_lines.append(line)
        else:
            current_lines.append(line)

    # flush 最后一段
    _flush()

    # 若没有识别到任何标题（整篇无结构），则作为单段返回
    if not paragraphs:
        paragraphs.append({
            'paragraph_id': 'p1',
            'title': '正文',
            'content': content.strip(),
            'evidence_codes': _extract_evidence_codes(content, avail_codes),
            'legal_references': _match_legal_references(content, legal_refs),
            'source_regions': [],
        })
        return paragraphs

    # 若首段是标题但内容空（如首个 line 即标题），has_header 已处理
    return paragraphs


def merge_paragraphs_to_content(paragraphs: list[dict]) -> str:
    """将段落列表合并回正文（用于版本更新时重建 content）。

    Args:
        paragraphs: 段落字典列表

    Returns:
        合并后的正文（段落间以空行分隔）
    """
    if not paragraphs:
        return ''
    return '\n\n'.join(p.get('content', '') for p in paragraphs if p.get('content'))


def update_paragraph(
    paragraphs: list[dict],
    paragraph_id: str,
    new_content: str,
    evidence_codes: list[str] | None = None,
) -> tuple[list[dict], int]:
    """更新指定段落的 content / evidence_codes，返回新段落列表与目标索引。

    Args:
        paragraphs: 原段落列表
        paragraph_id: 目标段落 ID（如 "p2"）
        new_content: 新段落正文
        evidence_codes: 新证据编号列表（None 表示保留原值）

    Returns:
        (new_paragraphs, target_idx)：
            - new_paragraphs: 新段落列表（深拷贝，不修改入参）
            - target_idx: 更新的段落索引；未找到时为 -1

    Raises:
        ValueError: paragraphs 为空时
    """
    if not paragraphs:
        raise ValueError('paragraphs 列表为空')

    new_paragraphs = [dict(p) for p in paragraphs]
    target_idx = -1
    for i, p in enumerate(new_paragraphs):
        if p.get('paragraph_id') == paragraph_id:
            target_idx = i
            break
    if target_idx == -1:
        return new_paragraphs, -1

    new_paragraphs[target_idx] = {
        **new_paragraphs[target_idx],
        'content': new_content,
        'evidence_codes': (
            list(evidence_codes) if evidence_codes is not None
            else list(new_paragraphs[target_idx].get('evidence_codes', []))
        ),
    }
    return new_paragraphs, target_idx


# 类型导出（供类型检查器使用）
ParagraphList = list[dict[str, Any]]
