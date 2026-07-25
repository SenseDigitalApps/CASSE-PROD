"""
Django settings for app project.

Base configuration - shared across all environments.
"""
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import os
from urllib.parse import urlparse

# Load environment variables
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DJANGO_DEBUG', 'false').lower() == 'true'

ALLOWED_HOSTS = [host.strip() for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]
# In DEBUG mode allow phones on any LAN IP without updating .env when Wi‑Fi changes.
if DEBUG:
    ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'unfold',  # Django Unfold debe ir antes de django.contrib.admin
    'unfold.contrib.filters',  # Filtros adicionales para Unfold
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_spectacular',
    # Local apps
    'apps.common',
    'apps.users',
    'apps.authn',
    'apps.audit',
    'apps.health',
    'apps.integrations',
    'apps.catalogs',
    'apps.quotes',
    'apps.payments',
    'apps.vouchers',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'app.middleware.correlation.CorrelationIDMiddleware',  # Correlation ID for request tracking
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'app.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'app.wsgi.application'

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
DATABASE_URL = os.getenv('DATABASE_URL', 'postgres://postgres:postgres@localhost:5432/insurance_db')

# Parse DATABASE_URL
if DATABASE_URL:
    db_url = urlparse(DATABASE_URL)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': db_url.path[1:] if db_url.path else 'insurance_db',
            'USER': db_url.username or 'postgres',
            'PASSWORD': db_url.password or 'postgres',
            'HOST': db_url.hostname or 'localhost',
            'PORT': db_url.port or 5432,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Custom Authentication Backend
# Allows login using email_primary instead of username
AUTHENTICATION_BACKENDS = [
    'apps.users.backends.EmailBackend',  # Custom backend for email_primary
    'django.contrib.auth.backends.ModelBackend',  # Fallback to default
]

# Password hashing
# Use Argon2 as the default password hasher (stronger than PBKDF2)
# Falls back to PBKDF2 if Argon2 is not available
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.ScryptPasswordHasher',
]

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

# Email Configuration
# Para desarrollo local: puede usar console backend o SMTP real según configuración
# Para producción: usa SMTP real
# Si EMAIL_USE_SMTP está en 'true', usa SMTP incluso en desarrollo
USE_SMTP = os.getenv('EMAIL_USE_SMTP', 'false').lower() == 'true'

if DEBUG and not USE_SMTP:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # Usar backend personalizado que configura HELO name correctamente
    EMAIL_BACKEND = 'apps.common.backends.email.CustomSMTPEmailBackend'

# SMTP Configuration
# Configuración para mail.sensedigital.com.co
EMAIL_HOST = os.getenv('EMAIL_HOST', 'mail.sensedigital.com.co')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '465'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'false').lower() == 'true'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'true').lower() == 'true'  # Puerto 465 usa SSL
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'casse@sensedigital.com.co')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '@Sense2025.')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'casse@sensedigital.com.co')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Configuración adicional para SMTP
EMAIL_TIMEOUT = 30
# HELO name para SMTP (debe ser un dominio válido)
EMAIL_HELO_NAME = os.getenv('EMAIL_HELO_NAME', 'mail.sensedigital.com.co')

# OTP Configuration
OTP_CODE_LENGTH = 6
OTP_EXPIRATION_MINUTES = 20
OTP_MAX_ATTEMPTS = 3
OTP_MAX_RESEND_PER_HOUR = 3
OTP_RESEND_COOLDOWN_SECONDS = 120  # 2 minutos

# Universal Assistance / Siebel SOAP Integration
UA_ENV = os.getenv('UA_ENV', 'qa')
UA_SIEBEL_BASE_URL = os.getenv(
    'UA_SIEBEL_BASE_URL',
    'https://siebelqa.universal-assistance.com:8443/siebel/app/eai_anon/esn',
)
_base = UA_SIEBEL_BASE_URL.rstrip('/')
UA_SIEBEL_ENDPOINT_URL = os.getenv(
    'UA_SIEBEL_ENDPOINT_URL',
    f'{_base}?SWEExtSource=SecureWebService&SWEExtCmd=Execute'
    if '?' not in _base else _base,
)
UA_SIEBEL_USERNAME = os.getenv('UA_SIEBEL_USERNAME', '')
UA_SIEBEL_PASSWORD = os.getenv('UA_SIEBEL_PASSWORD', '')
UA_ORGANIZATION_ID = os.getenv('UA_ORGANIZATION_ID', '')
UA_CONVENIO_INDIVIDUAL_ID = os.getenv('UA_CONVENIO_INDIVIDUAL_ID', '')
UA_CONVENIO_CAVIPETROL_ID = os.getenv('UA_CONVENIO_CAVIPETROL_ID', '')
UA_CHANNEL = os.getenv('UA_CHANNEL', 'Turismo')
UA_VENDOR_CODE = os.getenv('UA_VENDOR_CODE', 'CASSE-APP')
UA_DEFAULT_ORIGIN_COUNTRY = os.getenv('UA_DEFAULT_ORIGIN_COUNTRY', 'COLOMBIA')
UA_SOAP_TIMEOUT = int(os.getenv('UA_SOAP_TIMEOUT', '30'))
UA_CONTROL_NUMBER_PREFIX = os.getenv('UA_CONTROL_NUMBER_PREFIX', 'CASSE')
UA_LEAD_RETIRE_REASON_CODE = os.getenv('UA_LEAD_RETIRE_REASON_CODE', 'Venta Online')
QUOTE_EXPIRATION_HOURS = int(os.getenv('QUOTE_EXPIRATION_HOURS', '24'))

# Allianz Autos Individual (Call4 / ramos 1241-1243) — mTLS
ALLIANZ_ENV = os.getenv('ALLIANZ_ENV', 'uat')
ALLIANZ_ENDPOINT_URL = os.getenv(
    'ALLIANZ_ENDPOINT_URL',
    'https://secure-eu-uat-colombia.apis.allianz.com/drswoc16/services/AutosIndividualWS?codCia=3',
)
ALLIANZ_COMPANY = os.getenv('ALLIANZ_COMPANY', 'COL')
ALLIANZ_PARTNER_ID = os.getenv('ALLIANZ_PARTNER_ID', '')
ALLIANZ_AGENT_ID = os.getenv('ALLIANZ_AGENT_ID', '')
ALLIANZ_PARTNER_CODE = os.getenv('ALLIANZ_PARTNER_CODE', '')
ALLIANZ_AGENT_CODE = os.getenv('ALLIANZ_AGENT_CODE', '')
ALLIANZ_PRODUCT_CODE = os.getenv('ALLIANZ_PRODUCT_CODE', '1243')
ALLIANZ_DEFAULT_RISK_TYPE = os.getenv('ALLIANZ_DEFAULT_RISK_TYPE', 'L0008')
ALLIANZ_VEHICLE_ORIGIN = os.getenv('ALLIANZ_VEHICLE_ORIGIN', '480')
ALLIANZ_CAP = os.getenv('ALLIANZ_CAP', '3')
ALLIANZ_PFX_PATH = os.getenv(
    'ALLIANZ_PFX_PATH',
    str(BASE_DIR / 'certs' / 'allianz_uat.pfx'),
)
ALLIANZ_PFX_PASSWORD = os.getenv('ALLIANZ_PFX_PASSWORD', '')
ALLIANZ_CERT_PEM_PATH = os.getenv(
    'ALLIANZ_CERT_PEM_PATH',
    str(BASE_DIR / 'certs' / 'allianz_uat_cert.pem'),
)
ALLIANZ_KEY_PEM_PATH = os.getenv(
    'ALLIANZ_KEY_PEM_PATH',
    str(BASE_DIR / 'certs' / 'allianz_uat_key.pem'),
)
# Resolve relative cert paths against BASE_DIR (manage.py cwd can vary).
if ALLIANZ_PFX_PATH and not os.path.isabs(ALLIANZ_PFX_PATH):
    ALLIANZ_PFX_PATH = str(BASE_DIR / ALLIANZ_PFX_PATH)
if ALLIANZ_CERT_PEM_PATH and not os.path.isabs(ALLIANZ_CERT_PEM_PATH):
    ALLIANZ_CERT_PEM_PATH = str(BASE_DIR / ALLIANZ_CERT_PEM_PATH)
if ALLIANZ_KEY_PEM_PATH and not os.path.isabs(ALLIANZ_KEY_PEM_PATH):
    ALLIANZ_KEY_PEM_PATH = str(BASE_DIR / ALLIANZ_KEY_PEM_PATH)
ALLIANZ_SOAP_TIMEOUT = int(os.getenv('ALLIANZ_SOAP_TIMEOUT', '45'))
ALLIANZ_MOCK = os.getenv('ALLIANZ_MOCK', 'false').lower() in ('1', 'true', 'yes')

# Commercial assignment (stub until city/turn routing exists)
COMMERCIAL_DEFAULT_NAME = os.getenv('COMMERCIAL_DEFAULT_NAME', 'Laura Quintero')
COMMERCIAL_DEFAULT_EMAIL = os.getenv(
    'COMMERCIAL_DEFAULT_EMAIL',
    os.getenv('DEFAULT_FROM_EMAIL', 'casse@sensedigital.com.co'),
)
COMMERCIAL_DEFAULT_TITLE = os.getenv(
    'COMMERCIAL_DEFAULT_TITLE',
    'CASSE Seguros · Cuenta clave',
)
ENABLE_IN_APP_TRAVEL_PAYMENTS = os.getenv(
    'ENABLE_IN_APP_TRAVEL_PAYMENTS',
    'false',
).lower() in ('1', 'true', 'yes')
ENABLE_IN_APP_TRAVEL_VOUCHER_ISSUE = os.getenv(
    'ENABLE_IN_APP_TRAVEL_VOUCHER_ISSUE',
    'false',
).lower() in ('1', 'true', 'yes')

# Media files (voucher PDFs)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Default primary key field type
# https://docs.djangoproject.com/en/6.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Rate limiting for authentication endpoints
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',  # Anonymous users: 100 requests per hour
        'user': '1000/hour',  # Authenticated users: 1000 requests per hour
        'login': '5/minute',  # Login endpoint: 5 attempts per minute
    },
}

# Simple JWT
JWT_ACCESS_MINUTES = int(os.getenv('JWT_ACCESS_MINUTES', '15'))
JWT_REFRESH_DAYS = int(os.getenv('JWT_REFRESH_DAYS', '7'))

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=JWT_ACCESS_MINUTES),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=JWT_REFRESH_DAYS),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# CORS
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]
CORS_ALLOW_CREDENTIALS = True

# Celery Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Cache Configuration (using Redis for OTP storage)
# Parse Redis URL for cache configuration
redis_url_parsed = urlparse(REDIS_URL)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'KEY_PREFIX': 'casse',
        'TIMEOUT': 300,  # Default timeout (5 minutes)
    }
}

# DRF Spectacular (OpenAPI)
SPECTACULAR_SETTINGS = {
    'TITLE': 'CASSE API',
    'DESCRIPTION': 'API para App Integral de Seguros',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Django Unfold Settings
UNFOLD = {
    "SITE_TITLE": "CASSE Backend",
    "SITE_HEADER": "CASSE Backend Administration",
    "SITE_URL": "/",
    "SITE_ICON": None,
    "SITE_LOGO": None,
    "SITE_SYMBOL": "settings",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "ENVIRONMENT": None,
    "DASHBOARD_CALLBACK": None,
    "LOGIN": {
        "image": None,
        "redirect_after": None,
    },
    "STYLES": [
        "css/casse-admin.css",
    ],
    "SCRIPTS": [],
    "COLORS": {
        "primary": {
            # Paleta basada en el color primario de CASSE: Azul #3E5E8A
            "50": "239 243 248",   # Azul muy claro (base para fondos)
            "100": "215 225 238",  # Azul claro
            "200": "187 203 223",  # Azul claro medio
            "300": "159 181 208",  # Azul medio claro
            "400": "131 152 179",  # Azul claro de soporte (#8398B3)
            "500": "62 94 138",    # Azul primario CASSE (#3E5E8A)
            "600": "52 79 115",    # Azul medio oscuro
            "700": "42 64 92",     # Azul oscuro
            "800": "32 49 69",     # Azul muy oscuro
            "900": "22 34 46",     # Azul casi negro
            "950": "15 23 31",     # Azul negro
        },
        # Colores de acento (verde CASSE)
        "accent": {
            "50": "250 252 247",   # Verde muy claro
            "100": "245 250 235",  # Verde claro
            "200": "235 245 215",  # Verde claro medio
            "300": "225 240 195",  # Verde medio claro
            "400": "215 235 175",  # Verde medio
            "500": "205 221 100",  # Verde acento CASSE (#CDDD64)
            "600": "185 199 90",   # Verde medio oscuro
            "700": "165 177 80",   # Verde oscuro
            "800": "145 155 70",   # Verde muy oscuro
            "900": "125 133 60",   # Verde casi negro
            "950": "105 111 50",   # Verde negro
        },
        # Verde gris de soporte
        "secondary": {
            "50": "250 251 251",   # Verde gris muy claro
            "100": "245 247 247",  # Verde gris claro
            "200": "235 239 239",  # Verde gris claro medio
            "300": "225 231 231",  # Verde gris medio claro
            "400": "215 223 223",  # Verde gris medio
            "500": "208 217 215",  # Verde gris CASSE (#D0D9D7)
            "600": "187 195 194",  # Verde gris medio oscuro
            "700": "166 173 173",  # Verde gris oscuro
            "800": "145 151 152",  # Verde gris muy oscuro
            "900": "124 129 131",  # Verde gris casi negro
            "950": "103 107 110",  # Verde gris negro
        },
    },
    "EXTENSIONS": {
        "modeltranslation": {
            "flags": {
                "en": "🇬🇧",
                "fr": "🇫🇷",
                "nl": "🇳🇱",
            },
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [],
    },
}
