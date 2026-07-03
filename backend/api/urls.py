# -*- coding: utf-8 -*-
"""api 应用路由。"""
from django.urls import path

from api.views import (
    CaseDetailView,
    CaseListCreateView,
    CaseUpdateDeleteView,
    CaseStatusTransitionView,
    CaseStatusLogView,
    MaskImageView,
    EvidenceListCreateView,
    EvidenceUploadView,
    EvidenceDeleteView,
    ExtractedFieldListView,
    ExtractedFieldUpdateView,
    TimelineListView,
    TimelineRebuildView,
    TimelineNodeUpdateView,
    ComplaintView,
    ComplaintRegenerateView,
    MaskView,
    ExportView,
    ExportPackageView,
    ExportPDFView,
)

urlpatterns = [
    # T1 新增路由
    path('cases/', CaseListCreateView.as_view()),
    path('cases/<int:pk>/manage/', CaseUpdateDeleteView.as_view()),
    path('cases/<int:pk>/status/transition/', CaseStatusTransitionView.as_view()),
    path('cases/<int:pk>/status-logs/', CaseStatusLogView.as_view()),
    path('cases/<int:pk>/mask-images/', MaskImageView.as_view()),
    path('cases/<int:pk>/export/package/', ExportPackageView.as_view()),
    path('cases/<int:pk>/export/pdf/', ExportPDFView.as_view()),
    # 既有路由
    path('cases/<int:pk>/', CaseDetailView.as_view()),
    path('cases/<int:case_id>/evidences/', EvidenceListCreateView.as_view()),
    path('cases/<int:case_id>/evidences/upload/', EvidenceUploadView.as_view()),
    path('evidences/<int:pk>/', EvidenceDeleteView.as_view()),
    path('evidences/<int:evidence_id>/extracted-fields/', ExtractedFieldListView.as_view()),
    path('extracted-fields/<int:pk>/', ExtractedFieldUpdateView.as_view()),
    path('cases/<int:case_id>/timeline/', TimelineListView.as_view()),
    path('cases/<int:case_id>/timeline/rebuild/', TimelineRebuildView.as_view()),
    path('timeline-nodes/<int:pk>/', TimelineNodeUpdateView.as_view()),
    path('cases/<int:case_id>/complaints/', ComplaintView.as_view()),
    path('cases/<int:case_id>/complaints/regenerate/', ComplaintRegenerateView.as_view()),
    path('cases/<int:case_id>/mask/', MaskView.as_view()),
    path('cases/<int:case_id>/export/', ExportView.as_view()),
]
