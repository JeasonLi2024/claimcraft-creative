# -*- coding: utf-8 -*-
"""WSGI config for claimcraft project."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')

application = get_wsgi_application()
