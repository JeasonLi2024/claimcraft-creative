# -*- coding: utf-8 -*-
"""反证答辩书生成节点（async）：Jinja2 骨架 + LLM 重写（v10 反向维权）。

与 complaint_node.py 平行，主要差异：
- 输出"商家反证答辩书"而非"消费者投诉书"
- 持久化到 RespondTemplate 表（而非 ComplaintTemplate）
- 语气策略：反证模式默认 firm（坚定反驳不实指控）
- 复用 evidence_chain 节点输出 + 7 个法律工具 + 主动预检索法条
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

# 反证模式默认语气：坚定反驳不实指控
DEFAULT_RESPOND_TONE = "firm"
# 金额阈值（用于在 firm 之上进一步强调）
FIRM_TONE_AMOUNT_THRESHOLD = 1000

# Store namespace 常量（对齐 spec.md Requirement: LangGraph Store Node Access Pattern）
_RESPOND_SKELETON_KEY = "respond_complaint_skeleton"


def _templates_namespace(case_id) -> tuple:
    """构造案件模板缓存 namespace：("case", str(case_id), "templates")。"""
    return ("case", str(case_id), "templates")


def _get_cached_skeleton(runtime, case_id, current_prompt_version: str):
    """从 Store 读取缓存的 respond_complaint_skeleton，并执行缓存失效检测。

    缓存失效策略（对齐 spec.md Scenario: Case template cache hit）：
    - 若缓存的 prompt_bundle_version 与当前不一致 → delete 并返回 None

    Returns:
        (skeleton_dict, was_invalidated): skeleton_dict 为 None 表示未命中或已失效。
    """
    if runtime is None or getattr(runtime, "store", None) is None:
        return None, False
    try:
        item = runtime.store.get(
            _templates_namespace(case_id), _RESPOND_SKELETON_KEY
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
        try:
            runtime.store.delete(
                _templates_namespace(case_id), _RESPOND_SKELETON_KEY
            )
        except Exception:
            pass
        return None, True
    return value, False


def _put_cached_skeleton(runtime, case_id, skeleton: dict, prompt_version: str) -> None:
    """将 respond_complaint_skeleton 写入 Store（含 prompt_bundle_version 元数据）。"""
    if runtime is None or getattr(runtime, "store", None) is None:
        return
    try:
        cache_payload = {
            **skeleton,
            "prompt_bundle_version": prompt_version,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        runtime.store.put(
            _templates_namespace(case_id), _RESPOND_SKELETON_KEY, cache_payload
        )
    except Exception:
        pass


@traceable(name="反证答辩书生成节点", run_type="chain")
async def respond_complaint_node(state: CaseWorkflowState, runtime: Runtime = None) -> dict[str, Any]:
    """反证答辩书生成节点（async，Task 5.1 升级签名以访问 runtime.store）。

    流程：
    1. 启动时先查 runtime.store 缓存（respond_complaint_skeleton），命中则跳过 LLM 模板生成
    2. 调用 complaint_service.generate_complaint() 获取 Jinja2 骨架（复用同一生成器）
    3. 反证模式默认语气 firm
    4. 若 LLM 可用，重写正文为商家反证答辩书
    5. 写回 RespondTemplate 表（upsert）
    6. 输出 respond_draft
    7. Task 4.2 后处理：validate_legal_references + quality_gate + interrupt()
    """
    from api.models import Case, RespondTemplate
    from api.services.complaint_service import generate_complaint
    from api.agents.prompts.templates import (
        RESPOND_COMPLAINT_PROMPT,
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
        error_dicts = convert_string_errors_to_dicts(errors, stage="respond_complaint")
        node_result = build_node_result(
            node_name="respond_complaint",
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
            node_name="respond_complaint",
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
    # Task 5.1：优先使用 runtime.store，旧路径保留为降级回退
    user_pref_tone = None
    try:
        from api.services.user_preference_service import get_user_preference
        user_pref_tone = get_user_preference(
            runtime, str(case.owner_id), "complaint_style_tone"
        )
        if user_pref_tone is None:
            from api.agents.graph import _get_store
            store = _get_store()
            pref = store.get((str(case.owner_id), "preferences"), "complaint_style")
            if pref and pref.value:
                user_pref_tone = pref.value.get("tone")
    except Exception as e:
        logger.warning(f"读用户偏好失败（忽略，用默认语气）: {e}")

    # 1. 默认模板类型
    template_type = "platform"

    # Task 5.1.2：Store 缓存命中检测
    cached_skeleton, _was_invalidated = _get_cached_skeleton(
        runtime, case_id, current_prompt_version
    )

    # 2. Jinja2 骨架（缓存命中则跳过 LLM 模板生成）
    skeleton = None
    if cached_skeleton and isinstance(cached_skeleton, dict) and cached_skeleton.get("content"):
        logger.info(
            f"[反证答辩生成] Store 缓存命中 respond_complaint_skeleton (case={case_id})，"
            f"跳过 Jinja2 骨架生成"
        )
        skeleton = cached_skeleton
    else:
        try:
            skeleton = await sync_to_async(generate_complaint)(case, template_type)
        except Exception as e:
            logger.error(f"Jinja2 骨架生成失败: {e}", exc_info=True)
            errors.append(f"Jinja2 骨架生成失败: {e}")
            error_dicts = convert_string_errors_to_dicts(errors, stage="respond_complaint")
            node_result = build_node_result(
                node_name="respond_complaint",
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
                node_name="respond_complaint",
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

    # 4. 语气选择：反证模式默认 firm（坚定反驳）
    tone = _select_respond_tone(all_fields)
    # 用户偏好覆盖默认语气（store 长期记忆）
    if user_pref_tone in ("firm", "restrained", "legal"):
        tone = user_pref_tone
        logger.info(f"应用用户偏好语气: {tone}")

    # 4.1 Gate 3：评估输入数据充分性（input-quality-guard，与 complaint_node 对称）
    from api.agents.utils.data_sufficiency import (
        assess_data_sufficiency,
        build_sparse_data_notice,
    )
    acknowledged_low_quality = state.get("low_quality_evidence_acknowledged", False)
    data_sufficiency = assess_data_sufficiency(
        all_fields=all_fields,
        evidence_chain=state.get("evidence_chain", []),
        case_description=case.description or "",
        acknowledged_low_quality=acknowledged_low_quality,
    )
    data_is_sparse = data_sufficiency["level"] in ("sparse", "critically_sparse")
    if data_is_sparse:
        logger.info(
            f"[反证答辩生成] 输入数据{data_sufficiency['level']}"
            f"（score={data_sufficiency['score']}, "
            f"acknowledged={acknowledged_low_quality}），注入稀疏数据告知段落"
        )

    # 5. LLM 重写（若可用）
    final_content = skeleton.get("content", "")
    tool_call_log = []
    law_articles: list[dict] = []
    legal_references: list[dict] = []
    if llm_service.is_llm_available() and final_content.strip():
        try:
            await emit_progress(stage="skeleton_ready", message="反证答辩书骨架已生成，准备 LLM 重写...")

            facts_json = json.dumps(all_fields, ensure_ascii=False, indent=2)
            timeline_json = json.dumps(
                state.get("evidence_chain", []),
                ensure_ascii=False,
                indent=2,
            )

            # v10 工具集启用判断
            from api.agents.tools.law_tools import (
                is_tools_enabled, get_all_law_tools, _get_max_iterations,
                invoke_llm_with_tools, pre_retrieve_law_articles,
            )
            tools_enabled = is_tools_enabled()

            # 主动预检索法条（强制首次，失败降级）
            await emit_progress(stage="rag_retrieval", message="正在检索相关法条...")
            case_keywords = _extract_respond_keywords(case, all_fields)
            law_articles = await pre_retrieve_law_articles(case_keywords, top_k=5)
            law_articles_section = _format_respond_law_section(law_articles)
            # Task 4.1.3：序列化法条引用（用于段落 legal_references 匹配）
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

            prompt = RESPOND_COMPLAINT_PROMPT.format(
                tone=tone,
                skeleton=final_content,
                facts_json=facts_json,
                timeline_json=timeline_json,
                tools_section=tools_section,
                law_articles_section=law_articles_section,
                scenario_description=SCENARIO_DESCRIPTIONS.get(
                    case.case_type, SCENARIO_DESCRIPTIONS["other"]
                ),
            )

            # Gate 3：数据稀疏时追加告知段落，强约束 LLM 不得捏造事实
            if data_is_sparse:
                prompt += "\n\n" + build_sparse_data_notice(
                    fields_count=len(all_fields),
                    chain_count=len(state.get("evidence_chain", [])),
                    desc_len=len((case.description or "").strip()),
                )

            if tools_enabled:
                await emit_progress(
                    stage="llm_generating",
                    message="LLM 生成反证答辩书中（含工具调用）...",
                )
                # 绑定 7 个工具 + 多轮工具调用循环（与 complaint_node 一致）
                tools = get_all_law_tools()
                rewritten, tool_call_log = await invoke_llm_with_tools(
                    prompt=prompt,
                    tools=tools,
                    max_iterations=_get_max_iterations(),
                    errors=errors,
                    node_name="反证答辩生成",
                )
                logger.info(
                    f"[反证答辩生成] 工具调用完成，共 {len(tool_call_log)} 次"
                )
            else:
                await emit_progress(stage="llm_generating", message="LLM 生成反证答辩书中...")
                # 原逻辑：单次 LLM 重写
                rewritten = await sync_to_async(llm_service.chat_with_retry)([
                    {"role": "user", "content": prompt}
                ])

            if isinstance(rewritten, str) and rewritten.strip():
                final_content = rewritten.strip()
        except Exception as e:
            logger.warning(f"LLM 反证答辩重写失败，使用骨架: {e}")
            errors.append(f"LLM 反证答辩重写失败: {e}")

    # 6.0 统一追加「法律依据」（引用全部真实条文）与署名，与投诉书节点行为对齐：
    #     既满足「文书须注明引用到的全部条文」，也使导出前质量门可识别「依据段」。
    from api.agents.utils.paragraph_splitter import finalize_legal_document
    final_content = finalize_legal_document(
        final_content, legal_references, case.owner.username or "答辩人"
    )

    # 6. 持久化到 RespondTemplate 表（upsert）
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

    respond_template_instance = None
    try:
        respond_template_instance = await sync_to_async(lambda c=case, tt=template_type, sk=skeleton, fc=final_content, pg=paragraphs:
            RespondTemplate.objects.update_or_create(
                case=c,
                template_type=tt,
                defaults={
                    "title": sk.get("title", "反证答辩书"),
                    "content": fc,
                    "paragraphs": pg,
                },
            )
        )()
        if respond_template_instance is not None:
            # update_or_create 返回 (obj, created)
            respond_template_instance = respond_template_instance[0]
    except Exception as e:
        logger.error(f"持久化 RespondTemplate 失败: {e}", exc_info=True)
        errors.append(f"持久化 RespondTemplate 失败: {e}")

    # 6.2 Task 4.1.3：创建 DocumentVersion 记录 + WorkflowArtifact
    document_version_id = None
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
                document_type="respond_complaint",
                title=skeleton.get("title", "反证答辩书"),
                content=final_content,
                paragraphs=paragraphs,
                changelog="AI 生成反证答辩书初版",
                created_by_type="ai",
                workflow_version=workflow_version,
                respond_template=respond_template_instance,
            )
            document_version_id = doc_version.id
        except Exception as e:
            logger.error(f"创建 DocumentVersion 失败: {e}", exc_info=True)
            errors.append(f"创建 DocumentVersion 失败: {e}")

        # 创建 WorkflowArtifact（artifact_type='respond_complaint_draft'，content 含 paragraphs）
        if workflow_run_id:
            try:
                from api.agents.artifact_service import create_artifact
                source_refs = _collect_upstream_artifact_ids(state, "extract_result")
                await sync_to_async(create_artifact)(
                    workflow_run_id=workflow_run_id,
                    case_id=case.id,
                    artifact_type="respond_complaint_draft",
                    stage="document_generation",
                    node_name="respond_complaint",
                    content={
                        "title": skeleton.get("title", "反证答辩书"),
                        "content": final_content,
                        # P5：产物内容用 template_variant 与文书详情端点 template_type（种类）区分
                        "template_variant": template_type,
                        "tone": tone,
                        "legal_references": legal_references,
                        "paragraphs": paragraphs,
                        "document_version_id": document_version_id,
                        # Gate 3：数据充分性（供文书详情端点透出 → 前端 Banner）
                        "data_sufficiency": data_sufficiency,
                    },
                    summary={
                        "title": skeleton.get("title", "反证答辩书"),
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
                logger.error(f"创建 WorkflowArtifact(respond_complaint_draft) 失败: {e}", exc_info=True)
                errors.append(f"创建 WorkflowArtifact 失败: {e}")

    # 构造 NodeResult + partial update（同 complaint_node，Task 4.2 实现完整法条验证）
    error_dicts = convert_string_errors_to_dicts(errors, stage="respond_complaint")
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
    # provenance: 段落引用证据（每个法条引用 + 文书主体 + 段落级 provenance）
    provenance = [
        {
            "node": "respond_complaint",
            "evidence_id": None,
            "field_name": None,
            "source_ref": f"respond_complaint:legal:{a.get('law_name', '')}:{a.get('article_number', '')}",
            "ts": start_time.isoformat(),
        }
        for a in law_articles
    ]
    provenance.append({
        "node": "respond_complaint",
        "evidence_id": None,
        "field_name": None,
        "source_ref": f"respond_complaint:content:{template_type}",
        "ts": start_time.isoformat(),
    })
    # 段落级 provenance：含证据引用的段落
    for p in paragraphs:
        if p.get("evidence_codes"):
            provenance.append({
                "node": "respond_complaint",
                "evidence_id": None,
                "field_name": None,
                "source_ref": f"respond_complaint:paragraph:{p.get('paragraph_id', '')}:{','.join(p.get('evidence_codes', []))}",
                "ts": start_time.isoformat(),
            })
    node_result = build_node_result(
        node_name="respond_complaint",
        data={
            "draft_generated": has_content,
            "content_length": len(final_content) if has_content else 0,
            "tone": tone,
            "legal_references_count": len(law_articles),
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
                "legal_references_count": len(law_articles),
                "content_length": len(final_content) if has_content else 0,
                "tone": tone,
                "paragraph_count": len(paragraphs),
                "document_version_id": document_version_id,
                "legal_references_valid": legal_references_valid,
                "legal_validation_total_refs": legal_validation_result.total_refs,
                "legal_validation_valid_refs": legal_validation_result.valid_refs,
                "legal_validation_invalid_refs": legal_validation_result.invalid_refs,
                # Gate 3：数据充分性
                "data_sufficiency_score": data_sufficiency["score"],
                "data_sufficiency_level": data_sufficiency["level"],
                "missing_dimensions": data_sufficiency["missing_dimensions"],
            },
        ),
        warnings=[],
        errors=error_dicts,
        provenance=provenance,
        start_time=start_time,
        model_calls=1 + len(tool_call_log),
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
                f"反证答辩书引用了 {len(legal_validation_result.invalid_refs)} 条"
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
        node_name="respond_complaint",
        stage="document_generation",
        progress=0.90,
        state=state,
        node_result=node_result,
        legacy_fields={
            "complaint_draft": {
                "title": skeleton.get("title", "反证答辩书"),
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


def _select_respond_tone(extracted_fields: list[dict]) -> str:
    """反证模式语气选择：默认 firm（坚定反驳不实指控）。

    金额较大时可进一步强调，但仍保持 firm。
    用户偏好可在调用方覆盖。

    Args:
        extracted_fields: 抽取字段列表

    Returns:
        "firm"（默认）| "restrained"（金额极小，可降低强度）
    """
    for f in extracted_fields:
        if f.get("field_name") == "金额":
            try:
                amount = float(f.get("field_value", "0"))
                # 金额极小（≤ 阈值）时也可考虑 restrained，但反证模式默认坚定
                # 这里保持 firm 作为默认，避免被指控时显得软弱
                if amount <= FIRM_TONE_AMOUNT_THRESHOLD:
                    return "firm"
                return "firm"
            except (ValueError, TypeError):
                continue
    return DEFAULT_RESPOND_TONE


def _split_into_paragraphs(
    content: str,
    evidence_codes: list[str] | None = None,
    legal_references: list[dict] | None = None,
) -> list[dict]:
    """Task 4.1.3：将 LLM 生成的反证答辩书内容按段落标题切分为结构化段落。

    委托给 api.agents.utils.paragraph_splitter.split_into_paragraphs。
    """
    from api.agents.utils.paragraph_splitter import split_into_paragraphs
    return split_into_paragraphs(content, evidence_codes, legal_references)


def _collect_available_evidence_codes(state: CaseWorkflowState) -> list[str]:
    """从 state 收集当前案件所有可用证据编号（用于段落 evidence_codes 过滤）。"""
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
    """从 state.artifacts 收集指定类型的上游 WorkflowArtifact ID（用于 source_refs）。"""
    ids: list[int] = []
    for art in state.get("artifacts", []) or []:
        if not isinstance(art, dict):
            continue
        if art.get("kind") == artifact_type or art.get("artifact_type") == artifact_type:
            aid = art.get("artifact_id")
            if isinstance(aid, int) and aid not in ids:
                ids.append(aid)
    return ids


def _serialize_law_reference(article: dict) -> dict:
    """保留前端展示和溯源所需的本地法律文献字段（与 complaint_node 一致）。"""
    return {
        "law_name": article.get("law_name", ""),
        "article_number": article.get("article_number", ""),
        "summary": article.get("summary", ""),
        "content": article.get("content", ""),
        "source_url": article.get("source_url", ""),
    }


def _extract_respond_keywords(case, all_fields: list[dict]) -> list[str]:
    """从案件描述和抽取字段提取用于 RAG 检索的关键词（反证视角）。

    与 complaint 视角的关键词略不同，更强调商家抗辩视角
    （如：商品质量、合同履约、消费者违约等）。
    """
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
                    keywords.append("违约责任")
                    keywords.append("合同履行")
            except (ValueError, TypeError):
                pass
        elif field_name in ("商品名", "商品名称"):
            keywords.append(field_value)

    # 案件类型相关关键词（反证视角）
    case_type = case.case_type if case else ""
    type_keywords_map = {
        "shopping": ["商品质量", "退换货", "消费者违约"],
        "service": ["服务履约", "合同义务"],
        "secondhand": ["二手交易", "描述相符"],
    }
    keywords.extend(type_keywords_map.get(case_type, []))

    return keywords


def _format_respond_law_section(law_articles: list[dict]) -> str:
    """格式化法条注入反证答辩书 prompt 的片段。

    复用 COMPLAINT_LAW_ARTICLES_SECTION_TEMPLATE，因为格式相同。
    """
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
        logger.warning(f"[反证答辩生成] 法条片段格式化失败: {e}")
        return COMPLAINT_LAW_ARTICLES_EMPTY_SECTION
