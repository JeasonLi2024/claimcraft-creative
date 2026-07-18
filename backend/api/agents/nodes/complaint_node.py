# -*- coding: utf-8 -*-
"""投诉生成节点（async）：Jinja2 骨架 + LLM 重写。

重构说明（v4 异步化）：
- def → async def，支持节点级 timeout
- Django ORM 调用用 sync_to_async 包装
- LLM 调用用 sync_to_async(chat_with_retry) 包装
- @traceable 装饰器

语气策略：
- 金额 > 1000 元 → firm（坚定）
- 金额 ≤ 1000 元 → restrained（克制）
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

from asgiref.sync import sync_to_async

from api.agents.state import CaseWorkflowState
from api.agents.schemas import QualityReport
from api.agents.utils.node_result_builder import (
    build_node_result,
    convert_string_errors_to_dicts,
    make_node_partial_update,
)
from api.agents.utils.progress import emit_progress
from api.services import llm_service

try:
    from langgraph.runtime import Runtime
except ImportError:  # pragma: no cover - langgraph 应已安装
    Runtime = object  # type: ignore[misc,assignment]

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def deco(fn):
            return fn
        return args[0] if args and callable(args[0]) else deco

logger = logging.getLogger(__name__)

# 金额阈值（决定语气）
FIRM_TONE_AMOUNT_THRESHOLD = 1000

# Store namespace 常量（对齐 spec.md Requirement: LangGraph Store Node Access Pattern）
_CASE_TEMPLATES_NS_TEMPLATE = ("case", "{case_id}", "templates")
_COMPLAINT_SKELETON_KEY = "complaint_skeleton"


def _templates_namespace(case_id) -> tuple:
    """构造案件模板缓存 namespace：("case", str(case_id), "templates")。"""
    return ("case", str(case_id), "templates")


def _get_cached_skeleton(runtime, case_id, current_prompt_version: str):
    """从 Store 读取缓存的 complaint_skeleton，并执行缓存失效检测。

    缓存失效策略（对齐 spec.md Scenario: Case template cache hit）：
    - 若缓存的 prompt_bundle_version 与当前不一致 → delete 并返回 None
    - 若 case_type 不一致 → delete 并返回 None（防御性，未来扩展）

    Returns:
        (skeleton_dict, was_invalidated): skeleton_dict 为 None 表示未命中或已失效。
    """
    if runtime is None or getattr(runtime, "store", None) is None:
        return None, False
    try:
        item = runtime.store.get(
            _templates_namespace(case_id), _COMPLAINT_SKELETON_KEY
        )
    except Exception:
        return None, False
    if item is None:
        return None, False
    value = getattr(item, "value", None)
    if not isinstance(value, dict):
        return None, False
    cached_prompt_version = value.get("prompt_bundle_version")
    if cached_prompt_version and current_prompt_version and cached_prompt_version != current_prompt_version:
        # 缓存失效：清空旧条目，回退到 LLM 重新生成
        try:
            runtime.store.delete(
                _templates_namespace(case_id), _COMPLAINT_SKELETON_KEY
            )
        except Exception:
            pass
        return None, True
    return value, False


def _put_cached_skeleton(runtime, case_id, skeleton: dict, prompt_version: str) -> None:
    """将 complaint_skeleton 写入 Store（含 prompt_bundle_version 元数据）。"""
    if runtime is None or getattr(runtime, "store", None) is None:
        return
    try:
        cache_payload = {
            **skeleton,
            "prompt_bundle_version": prompt_version,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        runtime.store.put(
            _templates_namespace(case_id), _COMPLAINT_SKELETON_KEY, cache_payload
        )
    except Exception:
        pass


@traceable(name="投诉生成节点", run_type="chain")
async def complaint_node(state: CaseWorkflowState, runtime: Runtime = None) -> dict[str, Any]:
    """投诉生成节点（async，Task 5.1 升级签名以访问 runtime.store）。

    流程：
    1. 启动时先查 runtime.store 缓存（complaint_skeleton），命中则跳过 LLM 模板生成
    2. 调用既有 complaint_service.generate_complaint() 获取 Jinja2 骨架
    3. 根据金额选择语气
    4. 若 LLM 可用，重写正文
    5. 写回 ComplaintTemplate 表（upsert）
    6. 输出 complaint_draft
    7. Task 4.2 后处理：validate_legal_references + quality_gate + interrupt()
    """
    from api.models import Case, ComplaintTemplate
    from api.services.complaint_service import generate_complaint
    from api.agents.prompts.templates import (
        COMPLAINT_REWRITE_PROMPT,
        TOOLS_ENABLED_SECTION,
        TOOLS_DISABLED_SECTION,
        SCENARIO_DESCRIPTIONS,
    )

    case_id = state["case_id"]
    errors = []
    start_time = datetime.now(timezone.utc)
    current_prompt_version = state.get("prompt_bundle_version", "")

    try:
        case = await sync_to_async(Case.objects.get)(pk=case_id)
    except Case.DoesNotExist:
        errors.append(f"案件 {case_id} 不存在")
        error_dicts = convert_string_errors_to_dicts(errors, stage="complaint")
        node_result = build_node_result(
            node_name="complaint",
            data={"draft_generated": False},
            quality=QualityReport(
                score=0.0,
                coverage=0.0,
                status="fail",
                blocking_issues=[],
                details={"reason": "case_not_found"},
            ),
            warnings=[],
            errors=error_dicts,
            provenance=[],
            start_time=start_time,
            model_calls=0,
        )
        return make_node_partial_update(
            node_name="complaint",
            stage="document_generation",
            progress=0.90,
            state=state,
            node_result=node_result,
            legacy_fields={
                "complaint_draft": None,
                "errors": error_dicts,
            },
        )

    # 读用户偏好（store 长期记忆，跨案件复用）
    # Task 5.1：优先使用 runtime.store（对齐 langgraph-persistence skill），
    # 旧路径（直接 _get_store()）保留为降级回退，确保未升级调用链仍可工作。
    user_pref_tone = None
    try:
        from api.services.user_preference_service import get_user_preference
        user_pref_tone = get_user_preference(
            runtime, str(case.owner_id), "complaint_style_tone"
        )
        if user_pref_tone is None:
            # 降级：直接读 store（旧 namespace 兼容）
            from api.agents.graph import _get_store
            store = _get_store()
            pref = store.get((str(case.owner_id), "preferences"), "complaint_style")
            if pref and pref.value:
                user_pref_tone = pref.value.get("tone")
    except Exception as e:
        logger.warning(f"读用户偏好失败（忽略，用默认语气）: {e}")

    # 1. 默认模板类型
    template_type = "platform"

    # Task 5.1.2：Store 缓存命中检测 — 若已有 complaint_skeleton，跳过 Jinja2 骨架生成。
    cached_skeleton, _was_invalidated = _get_cached_skeleton(
        runtime, case_id, current_prompt_version
    )

    # 2. Jinja2 骨架（Task 5.1.2：缓存命中则跳过 LLM 模板生成）
    skeleton = None
    if cached_skeleton and isinstance(cached_skeleton, dict) and cached_skeleton.get("content"):
        # 缓存命中：直接使用 Store 中的 skeleton，跳过 Jinja2 骨架生成
        logger.info(
            f"[投诉生成] Store 缓存命中 complaint_skeleton (case={case_id})，"
            f"跳过 Jinja2 骨架生成"
        )
        skeleton = cached_skeleton
    else:
        try:
            skeleton = await sync_to_async(generate_complaint)(case, template_type)
        except Exception as e:
            logger.error(f"Jinja2 骨架生成失败: {e}", exc_info=True)
            errors.append(f"Jinja2 骨架生成失败: {e}")
            error_dicts = convert_string_errors_to_dicts(errors, stage="complaint")
            node_result = build_node_result(
                node_name="complaint",
                data={"draft_generated": False},
                quality=QualityReport(
                    score=0.0,
                    coverage=0.0,
                    status="fail",
                    blocking_issues=[],
                    details={"reason": "skeleton_generation_failed"},
                ),
                warnings=[],
                errors=error_dicts,
                provenance=[],
                start_time=start_time,
                model_calls=0,
            )
            return make_node_partial_update(
                node_name="complaint",
                stage="document_generation",
                progress=0.90,
                state=state,
                node_result=node_result,
                legacy_fields={
                    "complaint_draft": None,
                    "errors": error_dicts,
                },
            )
        # 缓存未命中：写入 Store 供后续运行复用
        if skeleton and isinstance(skeleton, dict):
            _put_cached_skeleton(runtime, case_id, skeleton, current_prompt_version)

    # 3. 聚合所有证据字段
    extract_results = state.get("evidence_extract_results", [])
    all_fields = []
    for er in extract_results:
        for f in er.get("fields", []):
            all_fields.append(f)

    # 4. 语气选择（基于金额）
    tone = _select_tone(all_fields)
    # 用户偏好覆盖默认语气（store 长期记忆）
    if user_pref_tone in ("firm", "restrained"):
        tone = user_pref_tone
        logger.info(f"应用用户偏好语气: {tone}")

    # 5. LLM 重写（若可用）
    final_content = skeleton.get("content", "")
    tool_call_log = []
    legal_references = []
    if llm_service.is_llm_available() and final_content.strip():
        try:
            await emit_progress(stage="skeleton_ready", message="投诉书骨架已生成，准备 LLM 重写...")

            facts_json = json.dumps(all_fields, ensure_ascii=False, indent=2)
            timeline_json = json.dumps(
                state.get("evidence_chain", []),
                ensure_ascii=False,
                indent=2,
            )

            # v10 新增：Tools 工具集启用判断
            from api.agents.tools.law_tools import (
                is_tools_enabled, get_all_law_tools, _get_max_iterations,
                invoke_llm_with_tools, pre_retrieve_law_articles,
            )
            tools_enabled = is_tools_enabled()

            # v10 新增：主动预检索法条（强制首次，失败降级）
            await emit_progress(stage="rag_retrieval", message="正在检索相关法条...")
            case_keywords = _extract_complaint_keywords(case, all_fields)
            law_articles = await pre_retrieve_law_articles(case_keywords, top_k=5)
            law_articles_section = _format_complaint_law_section(law_articles)
            legal_references = [_serialize_law_reference(article) for article in law_articles]
            await emit_progress(
                stage="rag_done",
                message=f"法条检索完成，命中 {len(law_articles)} 条",
                detail={"candidate_count": len(law_articles)},
            )

            if tools_enabled:
                tools_section = TOOLS_ENABLED_SECTION
            else:
                tools_section = TOOLS_DISABLED_SECTION

            prompt = COMPLAINT_REWRITE_PROMPT.format(
                tone=tone,
                skeleton=final_content,
                facts_json=facts_json,
                timeline_json=timeline_json,
                tools_section=tools_section,
                law_articles_section=law_articles_section,
                scenario_description=SCENARIO_DESCRIPTIONS.get(case.case_type, SCENARIO_DESCRIPTIONS["other"]),
            )

            if tools_enabled:
                await emit_progress(
                    stage="llm_generating",
                    message="LLM 重写投诉书中（含工具调用）...",
                )
                # v10：绑定 7 个工具 + 多轮工具调用循环（使用通用函数）
                tools = get_all_law_tools()
                rewritten, tool_call_log = await invoke_llm_with_tools(
                    prompt=prompt,
                    tools=tools,
                    max_iterations=_get_max_iterations(),
                    errors=errors,
                    node_name="投诉生成",
                )
                logger.info(
                    f"[投诉生成] 工具调用完成，共 {len(tool_call_log)} 次"
                )
            else:
                await emit_progress(stage="llm_generating", message="LLM 重写投诉书中...")
                # 原逻辑：单次 LLM 重写
                rewritten = await sync_to_async(llm_service.chat_with_retry)([
                    {"role": "user", "content": prompt}
                ])

            if isinstance(rewritten, str) and rewritten.strip():
                final_content = rewritten.strip()
        except Exception as e:
            logger.warning(f"LLM 投诉重写失败，使用骨架: {e}")
            errors.append(f"LLM 投诉重写失败: {e}")

    # 6. 统一追加可核验的法律文件说明和用户名署名，保证工作流与详情页一致。
    final_content = _finalize_complaint_content(
        final_content, legal_references, case.owner.username or "投诉人"
    )

    # 6.1 Task 4.1.3：段落级结构化（后处理切分，不修改 LLM prompt 避免回归）
    available_evidence_codes = _collect_available_evidence_codes(state)
    paragraphs = _split_into_paragraphs(
        final_content,
        evidence_codes=available_evidence_codes,
        legal_references=legal_references,
    )

    # 6.2 Task 4.2.3：法条引用真实性校验（后处理，不阻塞 LLM 重写流程）
    # 三级降级策略：LawRetriever RAG → LawArticle DB 直查 → 格式校验
    from api.services.document_quality_service import (
        ValidationResult,
        validate_legal_references,
    )
    try:
        legal_validation_result = await validate_legal_references(paragraphs)
    except Exception as e:
        logger.warning(f"法条引用校验异常（降级为通过，不阻塞主流程）: {e}")
        legal_validation_result = ValidationResult(
            valid=True, total_refs=0, valid_refs=0,
        )
    legal_references_valid = legal_validation_result.valid

    # 7. 持久化到 ComplaintTemplate 表（upsert，含 paragraphs 段落结构）
    complaint_template_instance = None
    try:
        complaint_template_instance = await sync_to_async(lambda c=case, tt=template_type, sk=skeleton, fc=final_content, pg=paragraphs:
            ComplaintTemplate.objects.update_or_create(
                case=c,
                template_type=tt,
                defaults={
                    "title": sk.get("title", "投诉标题"),
                    "content": fc,
                    "paragraphs": pg,
                },
            )
        )()
        if complaint_template_instance is not None:
            # update_or_create 返回 (obj, created)
            complaint_template_instance = complaint_template_instance[0]
    except Exception as e:
        logger.error(f"持久化 ComplaintTemplate 失败: {e}", exc_info=True)
        errors.append(f"持久化 ComplaintTemplate 失败: {e}")

    # 7.1 Task 4.1.3：创建 DocumentVersion 记录 + WorkflowArtifact（仅当 workflow_run_id 存在）
    document_version_id = None
    workflow_artifact_id = None
    workflow_run_id = state.get("workflow_run_id")
    workflow_version = state.get("workflow_version", "")
    has_content = bool(final_content and final_content.strip())
    if has_content:
        try:
            from api.services.document_version_service import create_document_version
            from api.models import WorkflowRun
            workflow_run = None
            if workflow_run_id:
                workflow_run = await sync_to_async(WorkflowRun.objects.filter(pk=workflow_run_id).first)()

            doc_version = await sync_to_async(create_document_version)(
                case=case,
                workflow_run=workflow_run,
                document_type="complaint",
                title=skeleton.get("title", "投诉标题"),
                content=final_content,
                paragraphs=paragraphs,
                changelog="AI 生成投诉文书初版",
                created_by_type="ai",
                workflow_version=workflow_version,
                complaint_template=complaint_template_instance,
            )
            document_version_id = doc_version.id
        except Exception as e:
            logger.error(f"创建 DocumentVersion 失败: {e}", exc_info=True)
            errors.append(f"创建 DocumentVersion 失败: {e}")

        # 创建 WorkflowArtifact（artifact_type='complaint_draft'，content 含 paragraphs）
        if workflow_run_id:
            try:
                from api.agents.artifact_service import create_artifact
                # 收集上游 extract_result artifact IDs 作为 source_refs
                source_refs = _collect_upstream_artifact_ids(state, "extract_result")
                await sync_to_async(create_artifact)(
                    workflow_run_id=workflow_run_id,
                    case_id=case.id,
                    artifact_type="complaint_draft",
                    stage="document_generation",
                    node_name="complaint",
                    content={
                        "title": skeleton.get("title", "投诉标题"),
                        "content": final_content,
                        # P5：产物内容用 template_variant（投诉风格：platform/personal…），
                        # 与文书详情端点的 template_type（文书种类）区分，消除同名歧义。
                        "template_variant": template_type,
                        "tone": tone,
                        "legal_references": legal_references,
                        "paragraphs": paragraphs,
                        "document_version_id": document_version_id,
                    },
                    summary={
                        "title": skeleton.get("title", "投诉标题"),
                        "key_metrics": {
                            "content_length": len(final_content),
                            "paragraph_count": len(paragraphs),
                            "legal_references_count": len(legal_references),
                        },
                        "highlights": [p.get("title", "") for p in paragraphs[:3]],
                    },
                    source_refs=source_refs,
                    revision=state.get("revision", 0) + 1,
                )
            except Exception as e:
                logger.error(f"创建 WorkflowArtifact(complaint_draft) 失败: {e}", exc_info=True)
                errors.append(f"创建 WorkflowArtifact 失败: {e}")

    # 构造 NodeResult + partial update
    error_dicts = convert_string_errors_to_dicts(errors, stage="complaint")
    # 6.3 Task 4.2.3：使用 quality_gate_service 完整评估（含法条真实性校验结果）
    # 替换 Task 4.1 占位逻辑（legal_validation_pending / amount_consistency_pending）
    from api.services.quality_gate_service import (
        evaluate_document_generation,
        should_block_on_quality,
    )
    quality = evaluate_document_generation(
        complaint_draft={"content": final_content} if has_content else None,
        legal_references_valid=legal_references_valid,
    )
    # provenance: 段落引用证据（每个法条引用 + 文书主体 + 每个段落）
    provenance = [
        {
            "node": "complaint",
            "evidence_id": None,
            "field_name": None,
            "source_ref": f"complaint:legal:{ref.get('law_name', '')}:{ref.get('article_number', '')}",
            "ts": start_time.isoformat(),
        }
        for ref in legal_references
    ]
    provenance.append({
        "node": "complaint",
        "evidence_id": None,
        "field_name": None,
        "source_ref": f"complaint:content:{template_type}",
        "ts": start_time.isoformat(),
    })
    # 段落级 provenance：含证据引用的段落
    for p in paragraphs:
        if p.get("evidence_codes"):
            provenance.append({
                "node": "complaint",
                "evidence_id": None,
                "field_name": None,
                "source_ref": f"complaint:paragraph:{p.get('paragraph_id', '')}:{','.join(p.get('evidence_codes', []))}",
                "ts": start_time.isoformat(),
            })
    node_result = build_node_result(
        node_name="complaint",
        data={
            "draft_generated": has_content,
            "content_length": len(final_content) if has_content else 0,
            "tone": tone,
            "legal_references_count": len(legal_references),
            "tool_calls": len(tool_call_log),
            "paragraph_count": len(paragraphs),
            "document_version_id": document_version_id,
            "workflow_artifact_created": workflow_run_id is not None,
        },
        quality=QualityReport(
            score=quality.score,
            coverage=quality.coverage,
            status=quality.status,
            blocking_issues=quality.blocking_issues,
            details={
                **quality.details,
                "legal_references_count": len(legal_references),
                "content_length": len(final_content) if has_content else 0,
                "tone": tone,
                "paragraph_count": len(paragraphs),
                "document_version_id": document_version_id,
                "legal_references_valid": legal_references_valid,
                "legal_validation_total_refs": legal_validation_result.total_refs,
                "legal_validation_valid_refs": legal_validation_result.valid_refs,
                "legal_validation_invalid_refs": legal_validation_result.invalid_refs,
            },
        ),
        warnings=[],
        errors=error_dicts,
        provenance=provenance,
        start_time=start_time,
        model_calls=1 + len(tool_call_log),  # 主 LLM 重写 + 工具调用
    )

    # 6.4 Task 4.2.3：法条引用无效 + should_block_on_quality → interrupt
    # 对齐 stage_gate_node 模式：create_intervention 在 interrupt() 之前（幂等）
    if should_block_on_quality(quality) and not legal_references_valid:
        from langgraph.types import interrupt
        from api.services.intervention_service import create_intervention
        workflow_run_id_for_interrupt = state.get("workflow_run_id")
        base_revision = state.get("revision", 0)

        # 幂等创建介入记录（update_or_create by workflow_run + type + stage + base_revision）
        intervention = await sync_to_async(create_intervention)(
            workflow_run_id=workflow_run_id_for_interrupt,
            case_id=case.id,
            intervention_type="legal_confirmation",
            stage="document_generation",
            base_revision=base_revision,
            form_schema={
                "fields": [
                    {
                        "name": "confirmed_invalid_refs",
                        "label": "无效法条确认（确认继续导出或修正引用）",
                        "type": "textarea",
                        "required": True,
                    }
                ]
            },
            initial_values={
                "invalid_refs": legal_validation_result.invalid_refs,
            },
            impact={
                "downstream_nodes": [],
                "rerun_required": False,
                "invalid_refs_count": len(legal_validation_result.invalid_refs),
            },
        )

        # interrupt() payload 统一结构（对齐 stage_gate_node）
        payload = {
            "interrupt_type": "legal_confirmation",
            "intervention_id": intervention.id,
            "intervention_kind": "legal_confirmation",
            "required": True,
            "stage": "document_generation",
            "reason": (
                f"文书引用了 {len(legal_validation_result.invalid_refs)} 条"
                f"无法验证的法条，请确认后继续"
            ),
            "base_revision": base_revision,
            "invalid_refs": legal_validation_result.invalid_refs,
            "suggested_alternatives": [],  # 由后续 Task 5.x 填充
            "form_schema": intervention.form_schema,
            "initial_values": intervention.initial_values,
            "impact": intervention.impact,
        }
        interrupt(payload)

    return make_node_partial_update(
        node_name="complaint",
        stage="document_generation",
        progress=0.90,
        state=state,
        node_result=node_result,
        legacy_fields={
            "complaint_draft": {
                "title": skeleton.get("title", "投诉标题"),
                "content": final_content,
                "template_variant": template_type,
                "tone": tone,
                "legal_references": legal_references,
                "paragraphs": paragraphs,
                "document_version_id": document_version_id,
            },
            "complaint_tool_calls": tool_call_log,
            "errors": error_dicts,
        },
    )


def _select_tone(extracted_fields: list[dict]) -> str:
    """根据金额选择语气。

    Args:
        extracted_fields: 抽取字段列表

    Returns:
        "firm" | "restrained"
    """
    for f in extracted_fields:
        if f.get("field_name") == "金额":
            try:
                amount = float(f.get("field_value", "0"))
                if amount > FIRM_TONE_AMOUNT_THRESHOLD:
                    return "firm"
                return "restrained"
            except (ValueError, TypeError):
                continue
    return "restrained"


def _split_into_paragraphs(
    content: str,
    evidence_codes: list[str] | None = None,
    legal_references: list[dict] | None = None,
) -> list[dict]:
    """Task 4.1.3：将 LLM 生成的文书内容按段落标题切分为结构化段落。

    委托给 api.agents.utils.paragraph_splitter.split_into_paragraphs，
    此 wrapper 仅为节点内引用方便（保留节点内函数签名以匹配 spec 描述）。
    """
    from api.agents.utils.paragraph_splitter import split_into_paragraphs
    return split_into_paragraphs(content, evidence_codes, legal_references)


def _collect_available_evidence_codes(state: CaseWorkflowState) -> list[str]:
    """从 state 收集当前案件所有可用证据编号（用于段落 evidence_codes 过滤）。

    来源：evidence_preclassify_results / evidence_ocr_results /
    evidence_classify_results / evidence_extract_results 中的 evidence_code 字段。
    """
    codes: list[str] = []
    seen: set[str] = set()
    for key in (
        "evidence_preclassify_results",
        "evidence_ocr_results",
        "evidence_classify_results",
        "evidence_extract_results",
    ):
        for item in state.get(key, []) or []:
            code = item.get("evidence_code") if isinstance(item, dict) else None
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def _collect_upstream_artifact_ids(
    state: CaseWorkflowState, artifact_type: str
) -> list[int]:
    """从 state.artifacts 收集指定类型的上游 WorkflowArtifact ID（用于 source_refs）。

    state.artifacts 由各节点通过 make_node_partial_update 累积，
    每项含 {artifact_id, kind, stage, ...}。
    """
    ids: list[int] = []
    for art in state.get("artifacts", []) or []:
        if not isinstance(art, dict):
            continue
        # kind 字段记录 artifact_type
        if art.get("kind") == artifact_type or art.get("artifact_type") == artifact_type:
            aid = art.get("artifact_id")
            if isinstance(aid, int) and aid not in ids:
                ids.append(aid)
    return ids


def _extract_complaint_keywords(case, all_fields: list[dict]) -> list[str]:
    """从案件描述和抽取字段提取用于 RAG 检索的关键词。"""
    keywords = []
    description = case.description if case else ""

    if description:
        keywords.append(description[:200])

    # 从字段值提取关键词
    for f in all_fields:
        field_name = f.get("field_name", "")
        field_value = f.get("field_value", "")
        if field_name == "金额":
            try:
                amount = float(field_value)
                if amount > 1000:
                    keywords.append("欺诈")
                    keywords.append("退一赔三")
            except (ValueError, TypeError):
                pass
        elif field_name in ("商品名", "商品名称"):
            keywords.append(field_value)

    # 案件类型相关关键词
    case_type = case.case_type if case else ""
    type_keywords_map = {
        "shopping": ["网购", "商品", "退换货"],
        "service": ["服务", "违约"],
        "secondhand": ["二手", "交易"],
    }
    keywords.extend(type_keywords_map.get(case_type, []))

    return keywords


def _finalize_complaint_content(content: str, references: list[dict], signer_name: str) -> str:
    """追加「法律依据」（引用全部真实条文）与「署名」两节，委托共享实现。"""
    from api.agents.utils.paragraph_splitter import finalize_legal_document
    return finalize_legal_document(content, references, signer_name)


def _serialize_law_reference(article: dict) -> dict:
    """保留前端展示和溯源所需的本地法律文献字段。"""
    return {
        "law_name": article.get("law_name", ""),
        "article_number": article.get("article_number", ""),
        "summary": article.get("summary", ""),
        "content": article.get("content", ""),
        "source_url": article.get("source_url", ""),
    }


def _format_complaint_law_section(law_articles: list[dict]) -> str:
    """格式化法条注入投诉重写 prompt 的片段。"""
    from api.agents.prompts.templates import (
        COMPLAINT_LAW_ARTICLES_SECTION_TEMPLATE,
        COMPLAINT_LAW_ARTICLES_EMPTY_SECTION,
    )

    if not law_articles:
        return COMPLAINT_LAW_ARTICLES_EMPTY_SECTION

    try:
        law_articles_json = json.dumps(
            [
                {
                    "law_name": a["law_name"],
                    "article_number": a["article_number"],
                    "summary": a["summary"],
                    "content": a["content"][:200],
                }
                for a in law_articles
            ],
            ensure_ascii=False, indent=2
        )
        return COMPLAINT_LAW_ARTICLES_SECTION_TEMPLATE.format(
            law_articles_json=law_articles_json
        )
    except Exception as e:
        logger.warning(f"[投诉生成] 法条片段格式化失败: {e}")
        return COMPLAINT_LAW_ARTICLES_EMPTY_SECTION
