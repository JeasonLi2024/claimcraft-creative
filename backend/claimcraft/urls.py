# -*- coding: utf-8 -*-
"""claimcraft URL Configuration."""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings

from claimcraft.media_views import serve_media


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]

# 媒体文件服务（生产/开发均生效，不再依赖 DEBUG 开关）
# 注意：必须放在最后，避免被 /api/ 吞掉
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve_media),
]

# 开发环境额外挂载静态资源（collectstatic 产物）
if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
