"""
Local development settings.
"""
from .base import *

DEBUG = True

# Allow physical devices on any LAN IP without updating .env each time Wi‑Fi changes.
ALLOWED_HOSTS = ['*']

# Additional local development configurations
# CORS: Allow all origins in development
CORS_ALLOW_ALL_ORIGINS = True

