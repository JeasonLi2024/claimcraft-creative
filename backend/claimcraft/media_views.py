# -*- coding: utf-8 -*-
"""生产环境可用的媒体文件服务视图。

Django 自带的 ``django.conf.urls.static.static`` 仅在 ``DEBUG=True`` 时挂载，
生产（ASGI + uvicorn）下用户上传到 ``MEDIA_ROOT`` 的图片无法被访问，
前端 ``/media/...`` 请求会一路 404。本视图绕过这一限制：

* 仅允许 ``MEDIA_ROOT`` 子路径（防目录穿越）
* 命中文件时按扩展名返回 ``Content-Type``
* 简单缓存策略：图片一年不可变
"""
import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404


# 允许通过本视图返回的扩展名（白名单，防止把任意文件当媒体返回）
_ALLOWED_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico'}


def _safe_join(media_root: Path, rel_path: str) -> Path:
    """解析请求路径到 MEDIA_ROOT 下的真实文件，阻止 ../ 越权。"""
    # 去掉前导斜杠与 query/fragment
    rel_path = rel_path.lstrip('/').split('?', 1)[0].split('#', 1)[0]
    # 规范化后必须仍在 media_root 之下
    candidate = (media_root / rel_path).resolve()
    try:
        candidate.relative_to(media_root.resolve())
    except ValueError:
        raise Http404('invalid media path')
    return candidate


def serve_media(request, path: str):
    """``/media/<path:path>`` 的生产环境处理器。"""
    media_root = Path(settings.MEDIA_ROOT)
    if not media_root.exists():
        raise Http404('media root not configured')

    file_path = _safe_join(media_root, path)
    if not file_path.is_file():
        raise Http404('media not found')

    # 扩展名白名单
    if file_path.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise Http404('unsupported media type')

    content_type, _ = mimetypes.guess_type(str(file_path))
    if content_type is None:
        content_type = 'application/octet-stream'

    response = FileResponse(file_path.open('rb'), content_type=content_type)
    # 用户上传内容一般不可变：强缓存一年
    response['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response
