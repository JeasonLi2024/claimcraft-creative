# -*- coding: utf-8 -*-
"""claimcraft URL Configuration."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]

# 开发环境 media 文件服务
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
