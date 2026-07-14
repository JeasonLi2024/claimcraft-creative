# -*- coding: utf-8 -*-
"""用户头像处理服务。"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Iterable

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from api.models import UserProfile


PILLOW_FORMAT_BY_EXTENSION = {
    'jpg': 'JPEG',
    'jpeg': 'JPEG',
    'png': 'PNG',
    'webp': 'WEBP',
}

RGB_OUTPUT_FORMATS = {'JPEG', 'WEBP'}


class AvatarValidationError(ValueError):
    """头像校验失败。"""


@dataclass
class AvatarSaveResult:
    profile: UserProfile
    deleted_files: list[str]


def _allowed_extensions() -> set[str]:
    return {
        extension.lower()
        for extension in settings.CLAIMCRAFT_AVATAR_ALLOWED_EXTENSIONS
    }


def _detect_extension(filename: str) -> str:
    _, ext = os.path.splitext(filename or '')
    return ext.lstrip('.').lower()


def _load_image(uploaded_file):
    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.load()
    except (AttributeError, OSError, UnidentifiedImageError) as exc:
        raise AvatarValidationError('上传文件不是有效图片') from exc

    image = ImageOps.exif_transpose(image)
    return image


def _validate_uploaded_file(uploaded_file):
    if uploaded_file is None:
        raise AvatarValidationError('未提供头像文件')

    extension = _detect_extension(getattr(uploaded_file, 'name', ''))
    if extension not in _allowed_extensions():
        raise AvatarValidationError('仅支持 jpg、jpeg、png、webp 格式头像')

    max_size = settings.CLAIMCRAFT_AVATAR_MAX_UPLOAD_BYTES
    if getattr(uploaded_file, 'size', 0) > max_size:
        raise AvatarValidationError(f'头像文件大小不能超过 {max_size // (1024 * 1024)} MB')

    image = _load_image(uploaded_file)
    return image, extension


def _normalize_for_format(image: Image.Image, image_format: str) -> Image.Image:
    if image_format in RGB_OUTPUT_FORMATS:
        if image.mode not in ('RGB', 'L'):
            return image.convert('RGB')
        if image.mode == 'L':
            return image.convert('RGB')
    return image


def _serialize_image(image: Image.Image, image_format: str, **save_kwargs) -> bytes:
    image = _normalize_for_format(image, image_format)
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, **save_kwargs)
    return buffer.getvalue()


def _extension_for_format(image_format: str) -> str:
    return {
        'JPEG': 'jpg',
        'PNG': 'png',
        'WEBP': 'webp',
    }.get(image_format.upper(), image_format.lower())


def _serialize_original_image(image: Image.Image, extension: str) -> tuple[bytes, str]:
    image_format = PILLOW_FORMAT_BY_EXTENSION.get(extension, 'PNG')
    save_kwargs = {}
    if image_format == 'JPEG':
        save_kwargs.update({'quality': 95, 'optimize': True})
    elif image_format == 'WEBP':
        save_kwargs.update({'quality': 95, 'method': 6})
    return _serialize_image(image, image_format, **save_kwargs), extension


def _build_display_image(image: Image.Image) -> bytes:
    display_size = settings.CLAIMCRAFT_AVATAR_DISPLAY_SIZE
    display_format = settings.CLAIMCRAFT_AVATAR_DISPLAY_FORMAT
    quality = settings.CLAIMCRAFT_AVATAR_DISPLAY_QUALITY

    display_image = ImageOps.fit(
        image.copy(),
        (display_size, display_size),
        method=Image.Resampling.LANCZOS,
    )
    return _serialize_image(
        display_image,
        display_format,
        quality=quality,
        method=6,
    )


def _delete_storage_paths(paths: Iterable[str]) -> list[str]:
    deleted = []
    for path in {path for path in paths if path}:
        if default_storage.exists(path):
            default_storage.delete(path)
            deleted.append(path)
    return deleted


def save_user_avatar(profile: UserProfile, uploaded_file) -> AvatarSaveResult:
    """保存用户头像原图与展示图。"""

    image, original_extension = _validate_uploaded_file(uploaded_file)
    original_bytes, original_extension = _serialize_original_image(
        image, original_extension
    )
    display_bytes = _build_display_image(image)
    display_extension = _extension_for_format(
        settings.CLAIMCRAFT_AVATAR_DISPLAY_FORMAT
    )

    old_paths = [
        profile.avatar_original.name,
        profile.avatar_display.name,
    ]

    new_original_name = f'avatar.{original_extension}'
    new_display_name = f'avatar.{display_extension}'

    new_paths = []
    try:
        profile.avatar_original.save(
            new_original_name,
            ContentFile(original_bytes),
            save=False,
        )
        new_paths.append(profile.avatar_original.name)
        profile.avatar_display.save(
            new_display_name,
            ContentFile(display_bytes),
            save=False,
        )
        new_paths.append(profile.avatar_display.name)
        profile.avatar_updated_at = timezone.now()
        profile.save()
    except Exception:
        _delete_storage_paths(new_paths)
        raise

    deleted_files = _delete_storage_paths(
        old_path for old_path in old_paths if old_path not in new_paths
    )
    return AvatarSaveResult(profile=profile, deleted_files=deleted_files)


def delete_user_avatar(profile: UserProfile) -> list[str]:
    """删除用户头像及其文件。"""

    old_paths = [
        profile.avatar_original.name,
        profile.avatar_display.name,
    ]
    if not any(old_paths):
        return []

    profile.avatar_original.delete(save=False)
    profile.avatar_display.delete(save=False)
    profile.avatar_updated_at = timezone.now()
    profile.save()
    return _delete_storage_paths(old_paths)
