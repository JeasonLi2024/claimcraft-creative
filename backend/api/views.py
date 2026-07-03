# -*- coding: utf-8 -*-
"""DRF 视图。"""
from django.db.models import Max, Q
from django.http import HttpResponse
from django.utils import timezone
from django_fsm import can_proceed
from rest_framework import status
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    ListAPIView,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Case, Evidence, ExtractedField, TimelineNode, CaseStatusLog
from api.serializers import (
    CaseSerializer,
    CaseListSerializer,
    CaseStatusLogSerializer,
    EvidenceSerializer,
    ExtractedFieldSerializer,
    TimelineNodeSerializer,
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

# 允许的图片扩展名与最大文件大小（10MB）
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
MAX_IMAGE_SIZE = 10 * 1024 * 1024


class CaseDetailView(APIView):
    """案件详情：GET /cases/<id>/ 返回案件详情含统计。"""

    def get(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CaseSerializer(case)
        return Response(serializer.data)


class EvidenceListCreateView(APIView):
    """证据列表与新增：GET/POST /cases/<id>/evidences/。"""

    def get(self, request, case_id):
        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)
        evidences = case.evidences.all().order_by('order', 'id')
        serializer = EvidenceSerializer(evidences, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request, case_id):
        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)

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
        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)

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
        try:
            evidence = Evidence.objects.get(pk=pk)
        except Evidence.DoesNotExist:
            return Response({'detail': '证据不存在'}, status=status.HTTP_404_NOT_FOUND)

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


class ExtractedFieldListView(APIView):
    """抽取字段列表：GET /evidences/<id>/extracted-fields/。"""

    def get(self, request, evidence_id):
        try:
            evidence = Evidence.objects.get(pk=evidence_id)
        except Evidence.DoesNotExist:
            return Response({'detail': '证据不存在'}, status=status.HTTP_404_NOT_FOUND)
        fields = evidence.extracted_fields.all()
        serializer = ExtractedFieldSerializer(fields, many=True)
        return Response(serializer.data)


class ExtractedFieldUpdateView(APIView):
    """抽取字段更新：PATCH /extracted-fields/<pk>/ 更新 field_value。"""

    def patch(self, request, pk):
        try:
            field = ExtractedField.objects.get(pk=pk)
        except ExtractedField.DoesNotExist:
            return Response({'detail': '抽取字段不存在'}, status=status.HTTP_404_NOT_FOUND)

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


class TimelineListView(APIView):
    """时间线列表：GET /cases/<id>/timeline/ 返回排序后的时间线。"""

    def get(self, request, case_id):
        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)
        nodes = timeline_service.get_sorted_timeline(case)
        serializer = TimelineNodeSerializer(nodes, many=True)
        return Response(serializer.data)


class TimelineRebuildView(APIView):
    """时间线重建：POST /cases/<id>/timeline/rebuild/。"""

    def post(self, request, case_id):
        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)
        nodes = timeline_service.rebuild_timeline(case)
        serializer = TimelineNodeSerializer(nodes, many=True)
        return Response(serializer.data)


class TimelineNodeUpdateView(APIView):
    """时间线节点更新：PATCH /timeline-nodes/<id>/ 更新 event 字段。"""

    def patch(self, request, pk):
        try:
            node = TimelineNode.objects.get(pk=pk)
        except TimelineNode.DoesNotExist:
            return Response({'detail': '时间线节点不存在'}, status=status.HTTP_404_NOT_FOUND)

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


class ComplaintView(APIView):
    """投诉文本：GET /cases/<id>/complaints/?template=<type>。"""

    def get(self, request, case_id):
        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)

        template_type = request.query_params.get('template', 'platform')
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
        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)

        template_type = request.data.get('template_type', 'platform')
        result = complaint_service.generate_complaint(case, template_type)
        if result is None:
            return Response(
                {'detail': f'未找到模板类型：{template_type}'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(result)


class MaskView(APIView):
    """敏感信息打码：POST /cases/<id>/mask/。"""

    def post(self, request, case_id):
        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)

        result = mask_service.mask_case_sensitive_info(case)
        return Response({
            'case_id': case.id,
            'count': len(result),
            'items': result,
        })


class ExportView(APIView):
    """导出文本：POST /cases/<id>/export/ 接收 {template_type, masked}。"""

    def post(self, request, case_id):
        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)

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
        qs = Case.objects.all()
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


class CaseUpdateDeleteView(RetrieveUpdateDestroyAPIView):
    """案件更新与删除：GET/PATCH/PUT/DELETE /cases/<id>/manage/。

    PATCH 仅更新 title/description/case_type（status 为只读，
    通过状态转换接口变更）。
    """

    queryset = Case.objects.all()
    serializer_class = CaseSerializer


class CaseStatusTransitionView(APIView):
    """案件状态转换：POST /cases/<id>/status/transition/。

    接收 {to_status, remark}，根据 FSM 校验并执行转换，
    成功后写入 CaseStatusLog。
    """

    def post(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return Response(
                {'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND
            )

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
        return CaseStatusLog.objects.filter(case_id=self.kwargs['pk'])


class MaskImageView(APIView):
    """证据图片打码：POST /cases/<id>/mask-images/。

    对该案件所有图片证据执行打码，返回打码后证据列表。
    """

    def post(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return Response(
                {'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND
            )
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
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return Response(
                {'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND
            )
        buf = export_service.export_evidence_package(case)
        resp = HttpResponse(buf.read(), content_type='application/zip')
        resp['Content-Disposition'] = (
            f'attachment; filename="case_{case.id}_package.zip"'
        )
        return resp


class ExportPDFView(APIView):
    """PDF 投诉材料导出：GET /cases/<id>/export/pdf/?template=<type>。"""

    def get(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return Response(
                {'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND
            )
        template_type = request.query_params.get('template', 'platform')
        buf = pdf_service.generate_complaint_pdf(case, template_type=template_type)
        resp = HttpResponse(buf.read(), content_type='application/pdf')
        resp['Content-Disposition'] = (
            f'attachment; filename="case_{case.id}_{template_type}.pdf"'
        )
        return resp
