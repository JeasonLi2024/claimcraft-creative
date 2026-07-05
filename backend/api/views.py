# -*- coding: utf-8 -*-
"""DRF 视图。"""
import logging
import time

from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_fsm import can_proceed
from datetime import timedelta
from rest_framework import status
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    ListAPIView,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import (
    Case, Evidence, ExtractedField, TimelineNode, CaseStatusLog,
    CaseTypePreset, ComplaintTemplateRule,
)
from api.serializers import (
    CaseSerializer,
    CaseListSerializer,
    CaseStatusLogSerializer,
    EvidenceSerializer,
    ExtractedFieldSerializer,
    TimelineNodeSerializer,
    UserSerializer,
    RegisterSerializer,
    CaseTypePresetSerializer,
)
from api.services import (
    evidence_service,
    timeline_service,
    complaint_service,
    mask_service,
    export_service,
    ocr_service,
    extraction_service,
    image_mask_service,
    pdf_service,
)

logger = logging.getLogger(__name__)

# 允许的图片扩展名与最大文件大小（10MB）
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
MAX_IMAGE_SIZE = 10 * 1024 * 1024


# ===== 鉴权视图 =====

class RegisterView(APIView):
    """用户注册：POST /auth/register/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class CurrentUserView(APIView):
    """当前登录用户：GET /auth/me/。"""

    def get(self, request):
        return Response(UserSerializer(request.user).data)


# ===== 案件视图 =====

class CaseDetailView(APIView):
    """案件详情：GET /cases/<id>/ 返回案件详情含统计。"""

    def get(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        serializer = CaseSerializer(case)
        return Response(serializer.data)


class CaseListCreateView(ListCreateAPIView):
    """案件列表与创建：GET/POST /cases/。

    GET 支持 ?search=&status=&case_type=，返回 CaseListSerializer 列表。
    POST 创建案件，status 由模型默认值决定为 draft。
    """

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CaseSerializer
        return CaseListSerializer

    def get_queryset(self):
        qs = Case.objects.filter(owner=self.request.user)
        params = self.request.query_params
        search = params.get('search')
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        status_filter = params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        case_type = params.get('case_type')
        if case_type:
            qs = qs.filter(case_type=case_type)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class CaseUpdateDeleteView(RetrieveUpdateDestroyAPIView):
    """案件更新与删除：GET/PATCH/PUT/DELETE /cases/<id>/manage/。

    PATCH 仅更新 title/description/case_type（status 为只读，
    通过状态转换接口变更）。
    """

    serializer_class = CaseSerializer

    def get_queryset(self):
        return Case.objects.filter(owner=self.request.user)


# ===== 证据视图 =====

class EvidenceListCreateView(APIView):
    """证据列表与新增：GET/POST /cases/<id>/evidences/。"""

    def get(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        evidences = case.evidences.all().order_by('order', 'id')
        serializer = EvidenceSerializer(evidences, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

        # 自动编号
        if 'code' not in data or not data.get('code'):
            data['code'] = evidence_service.generate_next_evidence_code(case)

        # order 设为当前最大 + 1
        max_order = case.evidences.aggregate(m=Max('order'))['m'] or 0
        if 'order' not in data or data.get('order') in (None, ''):
            data['order'] = max_order + 1

        serializer = EvidenceSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            serializer.save(case=case)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EvidenceUploadView(APIView):
    """证据图片上传：POST /cases/<id>/evidences/upload/。

    接收 multipart 文件（key: image），校验格式与大小，
    生成证据编号，保存图片，执行 OCR + 字段抽取，返回序列化结果。
    """

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        image_file = request.FILES.get('image')
        if not image_file:
            return Response({'detail': '未上传图片（key: image）'}, status=status.HTTP_400_BAD_REQUEST)

        # 校验扩展名
        name = image_file.name.lower()
        ext = name.rsplit('.', 1)[-1] if '.' in name else ''
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return Response(
                {'detail': f'不支持的图片格式：{ext}，仅支持 {sorted(ALLOWED_IMAGE_EXTENSIONS)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 校验大小
        if image_file.size > MAX_IMAGE_SIZE:
            return Response(
                {'detail': '图片大小超过 10MB 限制'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 自动编号与 order
        code = evidence_service.generate_next_evidence_code(case)
        max_order = case.evidences.aggregate(m=Max('order'))['m'] or 0

        # 取表单附加字段（可选）
        data = request.data
        evidence_type = data.get('evidence_type', '上传图片')
        description = data.get('description', f'{image_file.name} OCR 上传')
        source_time = data.get('source_time') or timezone.now()
        has_sensitive_info = data.get('has_sensitive_info', False)

        evidence = Evidence.objects.create(
            case=case,
            code=code,
            evidence_type=evidence_type,
            description=description,
            source_time=source_time,
            has_sensitive_info=bool(has_sensitive_info),
            order=max_order + 1,
            image=image_file,
            ocr_status='pending',
        )

        # OCR 识别
        try:
            text = ocr_service.ocr_image(evidence.image.path)
            evidence.extracted_text = text
            evidence.ocr_status = 'done'
            evidence.save()
        except Exception:
            evidence.ocr_status = 'failed'
            evidence.save()
            text = ''

        # 字段抽取（失败也不影响返回）
        try:
            extraction_service.extract_fields(evidence)
        except Exception:
            pass

        serializer = EvidenceSerializer(evidence, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EvidenceDeleteView(APIView):
    """证据删除：DELETE /evidences/<id>/。

    删除证据时同步清理时间线节点引用：
    - 删除引用该证据编号的 auto_generated 节点；
    - 从手动节点的 related_evidence_codes 中移除该证据编号，
      若手动节点清空后无任何引用，也一并删除（避免悬空节点）。
    """

    def delete(self, request, pk):
        evidence = get_object_or_404(
            Evidence, pk=pk, case__owner=request.user
        )

        code = evidence.code
        case = evidence.case
        evidence.delete()

        # 清理时间线节点引用
        if code:
            # 1. 删除引用该证据编号的自动节点
            case.timeline_nodes.filter(
                auto_generated=True, related_evidence_codes=code
            ).delete()
            # 2. 清理手动节点中 related_evidence_codes 包含该编号的节点
            for node in case.timeline_nodes.filter(auto_generated=False):
                codes = [c.strip() for c in (node.related_evidence_codes or '').split(',') if c.strip()]
                if code in codes:
                    codes = [c for c in codes if c != code]
                    node.related_evidence_codes = ','.join(codes)
                    node.save(update_fields=['related_evidence_codes'])

        return Response({'detail': '已删除'}, status=status.HTTP_204_NO_CONTENT)


# ===== 抽取字段视图 =====

class ExtractedFieldListView(APIView):
    """抽取字段列表：GET /evidences/<id>/extracted-fields/。"""

    def get(self, request, evidence_id):
        evidence = get_object_or_404(
            Evidence, pk=evidence_id, case__owner=request.user
        )
        fields = evidence.extracted_fields.all()
        serializer = ExtractedFieldSerializer(fields, many=True)
        return Response(serializer.data)


class ExtractedFieldUpdateView(APIView):
    """抽取字段更新：PATCH /extracted-fields/<pk>/ 更新 field_value。"""

    def patch(self, request, pk):
        field = get_object_or_404(
            ExtractedField, pk=pk, evidence__case__owner=request.user
        )

        data = request.data
        if 'field_value' in data:
            field.field_value = data['field_value']
        if 'field_name' in data:
            field.field_name = data['field_name']
        if 'confidence' in data:
            field.confidence = data['confidence']
        field.save()
        serializer = ExtractedFieldSerializer(field)
        return Response(serializer.data)

    def put(self, request, pk):
        return self.patch(request, pk)


# ===== 时间线视图 =====

class TimelineListView(APIView):
    """时间线列表：GET /cases/<id>/timeline/ 返回排序后的时间线。"""

    def get(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        nodes = timeline_service.get_sorted_timeline(case)
        serializer = TimelineNodeSerializer(nodes, many=True)
        return Response(serializer.data)


class TimelineRebuildView(APIView):
    """时间线重建：POST /cases/<id>/timeline/rebuild/。"""

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        nodes = timeline_service.rebuild_timeline(case)
        serializer = TimelineNodeSerializer(nodes, many=True)
        return Response(serializer.data)


class TimelineNodeUpdateView(APIView):
    """时间线节点更新：PATCH /timeline-nodes/<id>/ 更新 event 字段。"""

    def patch(self, request, pk):
        node = get_object_or_404(
            TimelineNode, pk=pk, case__owner=request.user
        )

        data = request.data
        if 'event' in data:
            node.event = data['event']
        # 允许顺带更新其它字段
        for field in ['datetime', 'related_evidence_codes', 'order']:
            if field in data:
                setattr(node, field, data[field])
        node.save()
        serializer = TimelineNodeSerializer(node)
        return Response(serializer.data)

    # 兼容 PUT
    def put(self, request, pk):
        return self.patch(request, pk)


# ===== 投诉视图 =====

class ComplaintView(APIView):
    """投诉文本：GET /cases/<id>/complaints/?template_type=<type>。"""

    def get(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        template_type = request.query_params.get('template_type', 'platform')
        result = complaint_service.generate_complaint(case, template_type)
        if result is None:
            return Response(
                {'detail': f'未找到模板类型：{template_type}'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(result)


class ComplaintRegenerateView(APIView):
    """投诉文本重新生成：POST /cases/<id>/complaints/regenerate/。

    接收 {template_type}（默认 platform），返回 {title, content, template_type}。
    """

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        template_type = request.data.get('template_type', 'platform')
        result = complaint_service.generate_complaint(case, template_type)
        if result is None:
            return Response(
                {'detail': f'未找到模板类型：{template_type}'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(result)


# ===== 打码视图 =====

class MaskView(APIView):
    """敏感信息打码：GET/POST /cases/<id>/mask/。

    GET：获取当前打码结果（实时计算，不修改数据库）。
    POST：同 GET，保持兼容。
    """

    def get(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        result = mask_service.mask_case_sensitive_info(case)
        return Response({
            'case_id': case.id,
            'count': len(result),
            'items': result,
        })

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        result = mask_service.mask_case_sensitive_info(case)
        return Response({
            'case_id': case.id,
            'count': len(result),
            'items': result,
        })


# ===== 导出视图 =====

class ExportView(APIView):
    """导出文本：POST /cases/<id>/export/ 接收 {template_type, masked}。"""

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        template_type = request.data.get('template_type', 'platform')
        masked = bool(request.data.get('masked', False))

        content = export_service.generate_export_text(
            case, template_type=template_type, masked=masked
        )
        filename = f'claimcraft_case_{case.id}_{template_type}.txt'
        return Response({
            'filename': filename,
            'content': content,
        })


# ===== T1 新增视图 =====

# to_status -> 转换方法名（cancelled 除外，需按当前状态二选一）
_STATUS_TRANSITION_METHODS = {
    'processing': 'to_processing',
    'submitted': 'to_submitted',
    'closed': 'to_closed',
}


class CaseStatusTransitionView(APIView):
    """案件状态转换：POST /cases/<id>/status/transition/。

    接收 {to_status, remark}，根据 FSM 校验并执行转换，
    成功后写入 CaseStatusLog。
    """

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)

        to_status = request.data.get('to_status')
        remark = request.data.get('remark', '')

        if not to_status:
            return Response(
                {'detail': '缺少 to_status'}, status=status.HTTP_400_BAD_REQUEST
            )

        # cancelled 需按当前状态选择对应取消方法
        if to_status == 'cancelled':
            if case.status == 'draft':
                method_name = 'cancel_from_draft'
            elif case.status == 'processing':
                method_name = 'cancel_from_processing'
            else:
                return Response(
                    {'detail': f'当前状态 {case.status} 不可取消'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            method_name = _STATUS_TRANSITION_METHODS.get(to_status)
            if not method_name:
                return Response(
                    {'detail': f'非法的目标状态：{to_status}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        method = getattr(case, method_name)
        if not can_proceed(method):
            return Response(
                {'detail': f'当前状态 {case.status} 不允许转换至 {to_status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = case.status
        method()
        case.save()
        CaseStatusLog.objects.create(
            case=case,
            from_status=old_status,
            to_status=to_status,
            remark=remark,
        )
        return Response({
            'id': case.id,
            'from_status': old_status,
            'to_status': to_status,
            'status': case.status,
        })


class CaseStatusLogView(ListAPIView):
    """案件状态日志：GET /cases/<id>/status-logs/。"""

    serializer_class = CaseStatusLogSerializer

    def get_queryset(self):
        return CaseStatusLog.objects.filter(
            case_id=self.kwargs['pk'], case__owner=self.request.user
        )


class MaskImageView(APIView):
    """证据图片打码：POST /cases/<id>/mask-images/。

    对该案件所有图片证据执行打码，返回打码后证据列表。
    """

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        results = image_mask_service.mask_case_images(case)
        serializer = EvidenceSerializer(
            results, many=True, context={'request': request}
        )
        return Response({
            'case_id': case.id,
            'count': len(results),
            'items': serializer.data,
        })


class ExportPackageView(APIView):
    """证据包导出：GET /cases/<id>/export/package/ 返回 ZIP 文件流。"""

    def get(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        buf = export_service.export_evidence_package(case)
        resp = HttpResponse(buf.read(), content_type='application/zip')
        resp['Content-Disposition'] = (
            f'attachment; filename="case_{case.id}_package.zip"'
        )
        return resp


class ExportPDFView(APIView):
    """PDF 投诉材料导出：GET /cases/<id>/export/pdf/?template_type=<type>。"""

    def get(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        template_type = request.query_params.get('template_type', 'platform')
        buf = pdf_service.generate_complaint_pdf(case, template_type=template_type)
        resp = HttpResponse(buf.read(), content_type='application/pdf')
        resp['Content-Disposition'] = (
            f'attachment; filename="case_{case.id}_{template_type}.pdf"'
        )
        return resp


# ===== Task 27：案件模板预设 =====

class CaseTypePresetListView(APIView):
    """案件类型预设列表：GET /case-presets/?case_type=<type>。

    返回所有预设，支持按 case_type 过滤。预设为全局共享，所有登录用户可见。
    """

    def get(self, request):
        qs = CaseTypePreset.objects.all()
        case_type = request.query_params.get('case_type')
        if case_type:
            qs = qs.filter(case_type=case_type)
        serializer = CaseTypePresetSerializer(qs, many=True)
        return Response(serializer.data)


class ApplyPresetView(APIView):
    """套用预设到案件：POST /cases/<id>/apply-preset/。

    接收 {preset_id}，根据预设创建：
    - 证据骨架（仅类型，无图片，描述占位"（待填写）"）
    - 时间线骨架（datetime 可为空，待用户后续补充）
    - 投诉模板规则（platform 类型，update_or_create）
    """

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        preset_id = request.data.get('preset_id')
        preset = get_object_or_404(CaseTypePreset, pk=preset_id)

        # 创建证据骨架（仅类型，无图片）
        created_evidences = []
        for i, ev_type in enumerate(preset.evidence_types):
            code = evidence_service.generate_next_evidence_code(case)
            ev = Evidence.objects.create(
                case=case,
                code=code,
                evidence_type=ev_type,
                description='（待填写）',
                source_time=timezone.now(),
                order=i,
            )
            created_evidences.append(ev)

        # 创建时间线骨架（datetime 可为 None）
        for i, node_data in enumerate(preset.timeline_skeleton):
            TimelineNode.objects.create(
                case=case,
                datetime=node_data.get('datetime'),
                event=node_data.get('event', ''),
                related_evidence_codes=node_data.get('related_evidence_codes', ''),
                order=i,
                auto_generated=False,
            )

        # 创建/更新投诉模板规则（platform 类型）
        if preset.complaint_template:
            ComplaintTemplateRule.objects.update_or_create(
                case=case,
                template_type='platform',
                defaults={
                    'rule_title': preset.name,
                    'rule_content': preset.complaint_template,
                }
            )

        return Response({
            'message': '预设套用成功',
            'evidences_created': len(created_evidences),
            'timeline_created': len(preset.timeline_skeleton),
            'complaint_template': bool(preset.complaint_template),
        })


# ===== Task 28：数据统计仪表盘 =====

class StatsView(APIView):
    """聚合统计：GET /stats/dashboard/ 按当前用户过滤。

    返回：案件类型分布、状态分布、证据总数、抽取字段总数、
    最近 30 天每日新建案件数、状态转换统计、案件总数。
    """

    def get(self, request):
        user_cases = Case.objects.filter(owner=request.user)

        # 案件类型分布
        case_type_dist = list(
            user_cases.values('case_type').annotate(count=Count('id')).order_by('case_type')
        )

        # 案件状态分布
        status_dist = list(
            user_cases.values('status').annotate(count=Count('id')).order_by('status')
        )

        # 证据总数
        evidence_total = Evidence.objects.filter(case__in=user_cases).count()

        # 抽取字段总数
        extracted_field_total = ExtractedField.objects.filter(
            evidence__case__in=user_cases
        ).count()

        # 最近 30 天每日新建案件数（TruncDate 跨数据库兼容）
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        recent_cases = list(
            user_cases.filter(created_at__gte=thirty_days_ago)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
        )

        # 状态转换统计（从 CaseStatusLog 聚合）
        status_transitions = list(
            CaseStatusLog.objects.filter(case__in=user_cases)
            .values('to_status')
            .annotate(count=Count('id'))
            .order_by('to_status')
        )

        return Response({
            'case_type_distribution': case_type_dist,
            'status_distribution': status_dist,
            'evidence_total': evidence_total,
            'extracted_field_total': extracted_field_total,
            'cases_recent_30days': recent_cases,
            'status_transitions': status_transitions,
            'case_total': user_cases.count(),
        })


# ===== B10：案件工作流（LangGraph 智能体）=====

class CaseWorkflowView(APIView):
    """案件工作流：POST /api/cases/<id>/run-workflow/

    基于 LangGraph StateGraph 构建 6 节点工作流（多证据聚合版）：
    OCR → 证据分类 → 字段抽取 → (HITL 校正?) → 证据链构造 → 投诉生成

    Body:
        evidence_ids: list[int] (可选，指定多个证据；不传则处理案件全部有图证据)
        resume: dict (可选，HITL 恢复时传入人工校正结果)

    响应：
        - 首次启动 + 无低置信度字段：status="completed"，含 complaint_draft
        - 首次启动 + 有低置信度字段：status="interrupted"，含 interrupt_data
        - HITL 恢复：status="completed"，含 complaint_draft
    """

    def post(self, request, pk):
        from asgiref.sync import async_to_sync
        from langgraph.types import Command
        from api.agents import build_case_workflow
        from api.services.langsmith_service import trace_for_case

        case = get_object_or_404(Case, pk=pk, owner=request.user)
        evidence_ids = request.data.get('evidence_ids', [])
        resume_value = request.data.get('resume')

        # 1. 获取或生成 thread_id（持久化到 Case 模型）
        if not case.thread_id:
            case.thread_id = f"case-{case.id}-{int(time.time())}"
            case.save(update_fields=['thread_id'])
        thread_id = case.thread_id

        # 2. 单例 workflow（不再每次重新编译）
        workflow = build_case_workflow()
        config = {"configurable": {"thread_id": thread_id}}

        # 3. 探测敏感证据（LangSmith 条件追踪：敏感证据 enabled=False 零数据保留）
        has_sensitive = case.evidences.filter(has_sensitive_info=True).exists()

        try:
            # 按 case 注入 LangSmith 追踪上下文（metadata + tags + project 路由）
            with trace_for_case(
                case_id=case.id,
                owner_id=request.user.id,
                case_type=case.case_type,
                has_sensitive=has_sensitive,
            ):
                if resume_value is not None:
                    # HITL 恢复（async 桥接：节点为 async def，需用 ainvoke + async_to_sync）
                    result = async_to_sync(workflow.ainvoke)(Command(resume=resume_value), config)
                else:
                    # 首次启动
                    initial_state = {
                        "case_id": case.id,
                        "evidence_ids": evidence_ids,
                        "evidence_ocr_results": [],
                        "evidence_classify_results": [],
                        "evidence_extract_results": [],
                        "needs_human_review": False,
                        "evidence_chain": [],
                        "complaint_draft": None,
                        "review_decision": None,
                        "errors": [],
                    }
                    result = async_to_sync(workflow.ainvoke)(initial_state, config)
        except Exception as e:
            logger.error(f"案件 {case.id} 工作流执行失败: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "case_id": case.id,
                    "thread_id": thread_id,
                    "error": f"工作流执行失败: {e}",
                    "errors": [str(e)],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 检查是否在 interrupt 处暂停
        interrupted = "__interrupt__" in result

        # 序列化 interrupt_data（Interrupt 对象不可直接 JSON 序列化）
        interrupt_data = None
        if interrupted:
            try:
                interrupts = result.get("__interrupt__", [])
                if interrupts:
                    interrupt_data = [
                        {"id": getattr(i, "id", None), "value": getattr(i, "value", str(i))}
                        for i in interrupts
                    ]
            except Exception as e:
                logger.warning(f"序列化 interrupt 失败: {e}", exc_info=True)
                interrupt_data = [{"error": f"序列化 interrupt 失败: {e}"}]

        return Response({
            "status": "interrupted" if interrupted else "completed",
            "case_id": case.id,
            "thread_id": thread_id,
            "interrupt_data": interrupt_data,
            "complaint_draft": result.get("complaint_draft"),
            "errors": result.get("errors", []),
        })


class CaseWorkflowHistoryView(APIView):
    """工作流状态历史：GET /api/cases/<id>/workflow/history/

    返回 checkpoint 列表摘要（时间、当前节点、错误数、是否含 complaint_draft），
    用于调试与审计。基于 langgraph `graph.get_state_history(config)`。

    安全：仅返回摘要（不暴露完整 state，避免敏感字段泄漏）；owner 校验同其他视图。
    """
    def get(self, request, pk):
        from api.agents import build_case_workflow
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        if not case.thread_id:
            return Response(
                {'detail': '案件尚未启动工作流'},
                status=status.HTTP_404_NOT_FOUND,
            )

        workflow = build_case_workflow()
        config = {"configurable": {"thread_id": case.thread_id}}
        history = []
        for state in workflow.get_state_history(config):
            values = state.values or {}
            history.append({
                'checkpoint_id': state.config.get('configurable', {}).get('checkpoint_id'),
                'created_at': state.created_at.isoformat() if state.created_at else None,
                'next': list(state.next) if state.next else [],
                'error_count': len(values.get('errors', [])),
                'has_complaint': bool(values.get('complaint_draft')),
                'evidence_processed': len(values.get('evidence_ocr_results', [])),
            })
        return Response({
            'case_id': case.id,
            'thread_id': case.thread_id,
            'history': history,
        })
