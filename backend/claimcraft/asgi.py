# -*- coding: utf-8 -*-
"""ASGI config for claimcraft project."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

application = get_asgi_application()
