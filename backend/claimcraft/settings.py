# -*- coding: utf-8 -*-
"""
Django settings for claimcraft project.

为 Demo 开箱即用，默认使用 SQLite3。
如需切换到 MySQL，请将下方 DATABASES 中的 sqlite3 配置注释掉，
并启用 MySQL 配置块；同时确保 MySQL 服务可用且已创建 claimcraft 数据库。
"""

import os
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# 自动加载项目根目录的 .env 文件（本地开发直连时生效；Docker 部署时由
# docker-compose 的 environment 段注入，此处为 no-op，不会覆盖已存在的环境变量）
try:
    from dotenv import load_dotenv
    _env_path = BASE_DIR.parent / '.env'
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass


# ============================================================
# LangSmith 观察配置（必须在 LangChain/LangGraph 初始化前设置）
# ============================================================
# 官方文档：https://docs.langchain.com/langsmith/trace-with-langchain
# SDK 读取的环境变量：LANGSMITH_TRACING / LANGSMITH_API_KEY /
#                    LANGSMITH_ENDPOINT / LANGSMITH_PROJECT /
#                    LANGSMITH_REGION / LANGSMITH_WORKSPACE_ID
# 旧变量名（仍兼容）：LANGCHAIN_TRACING_V2 / LANGCHAIN_API_KEY 等
if os.environ.get('LANGSMITH_TRACING', 'false').lower() == 'true':
    if not os.environ.get('LANGSMITH_API_KEY'):
        import warnings
        warnings.warn(
            "LANGSMITH_TRACING=true 但未设置 LANGSMITH_API_KEY，"
            "trace 不会上报。请在 .env 中配置 LANGSMITH_API_KEY。"
        )
    # 区域端点解析：LANGSMITH_REGION 优先，回退到 LANGSMITH_ENDPOINT
    # 支持区域：us（默认）/ eu（欧洲）/ ap（亚太，暂用默认）/ cn（国内中转）
    _REGION_ENDPOINTS = {
        'us': 'https://api.smith.langchain.com',
        'eu': 'https://eu.api.smith.langchain.com',
        'ap': 'https://api.smith.langchain.com',
        'cn': 'https://api.smith.langchain.com',
    }
    _region = os.environ.get('LANGSMITH_REGION', '').strip().lower()
    if _region and _region in _REGION_ENDPOINTS:
        os.environ.setdefault('LANGSMITH_ENDPOINT', _REGION_ENDPOINTS[_region])
    # 兼容旧变量名（部分 LangChain 组件仍读取 LANGCHAIN_* 前缀）
    os.environ.setdefault('LANGCHAIN_TRACING_V2', 'true')
    os.environ.setdefault('LANGCHAIN_API_KEY', os.environ.get('LANGSMITH_API_KEY', ''))
    os.environ.setdefault('LANGCHAIN_ENDPOINT', os.environ.get('LANGSMITH_ENDPOINT', ''))
    os.environ.setdefault('LANGCHAIN_PROJECT', os.environ.get('LANGSMITH_PROJECT', ''))
    # Workspace ID 透传：langsmith SDK 自动读取 LANGSMITH_WORKSPACE_ID
    # 无需 setdefault 到 LANGCHAIN_* —— langsmith SDK 直接读 LANGSMITH_WORKSPACE_ID


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-claimcraft-demo-secret-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 第三方
    'rest_framework',
    'corsheaders',
    # 业务应用
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'claimcraft.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'claimcraft.wsgi.application'
ASGI_APPLICATION = 'claimcraft.asgi.application'


# Database
# 默认 MySQL，所有参数支持环境变量（Docker 部署时由 docker-compose 注入）
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'claimcraft'),
        'USER': os.environ.get('DB_USER', 'root'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'Xx041123@#'),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

# --- SQLite3 配置（如需回退，将上方 MySQL 块替换为下方 sqlite3 块即可） ---
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'zh-hans'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_TZ = False


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (用户上传证据图片等)
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# CORS 配置（开发环境简化）
CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_ALL_ORIGINS = True


# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': None,
}
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}
