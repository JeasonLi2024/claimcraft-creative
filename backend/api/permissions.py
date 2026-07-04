# -*- coding: utf-8 -*-
"""DRF 自定义权限。"""
from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """检查请求用户是否为资源所有者。"""

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        if hasattr(obj, 'case'):
            return obj.case.owner == request.user
        if hasattr(obj, 'evidence') and hasattr(obj.evidence, 'case'):
            return obj.evidence.case.owner == request.user
        return False
