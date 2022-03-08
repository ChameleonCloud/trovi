"""
Django settings for trovi project.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""
import logging
import os
import secrets
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-a-+g)^dtso--4cnaw*dlnst3fq+x$znmp=u$*39y2-h6q8=ejm",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_ENV", "DEBUG") == "DEBUG"
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)

# Security settings
SECURE_HSTS_SECONDS = 155520011
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Reverse-Proxy configuration
SECURE_SSL_REDIRECT = False
# Tells Django that connections with X-Forwarded-Proto: https are secure
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

TROVI_FQDN = os.getenv("TROVI_FQDN", "localhost")
TROVI_PORT = os.getenv("TROVI_PORT", "8808")

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    TROVI_FQDN,
]

# Artifact storage
CHAMELEON_KEYSTONE_ENDPOINT = os.getenv("CHAMELEON_KEYSTONE_ENDPOINT")
CHAMELEON_SWIFT_TEMP_URL_KEY = os.getenv("CHAMELEON_SWIFT_TEMP_URL_KEY")
os.environ["CHAMELEON_SWIFT_TEMP_URL_KEY"] = CHAMELEON_SWIFT_TEMP_URL_KEY or ""
CHAMELEON_SWIFT_CONTAINER = os.getenv("CHAMELEON_SWIFT_CONTAINER", "trovi-dev")
CHAMELEON_JUPYTERHUB_URL = os.getenv(
    "CHAMELEON_JUPYTERHUB_URL", "https://jupyter.chameleoncloud.org"
)
CHAMELEON_SWIFT_USERNAME = os.getenv("CHAMELEON_SWIFT_USERNAME")
CHAMELEON_SWIFT_PASSWORD = os.getenv("CHAMELEON_SWIFT_PASSWORD")
CHAMELEON_SWIFT_PROJECT_NAME = os.getenv("CHAMELEON_SWIFT_PROJECT_NAME")
CHAMELEON_SWIFT_PROJECT_DOMAIN_NAME = os.getenv("CHAMELEON_SWIFT_PROJECT_DOMAIN_NAME")
CHAMELEON_SWIFT_USER_DOMAIN_NAME = os.getenv(
    "CHAMELEON_SWIFT_USER_DOMAIN_NAME", "default"
)
CHAMELEON_SWIFT_REGION_NAME = os.getenv("CHAMELEON_SWIFT_REGION_NAME", "CHI@UC")

ZENODO_URL = os.getenv("ZENODO_URL", "https://zenodo.org")
ZENODO_DEFAULT_ACCESS_TOKEN = os.getenv("ZENODO_DEFAULT_ACCESS_TOKEN")

AUTH_TROVI_TOKEN_LIFESPAN_SECONDS = 300

AUTH_TROVI_ADMIN_USERS = set(os.getenv("TROVI_ADMIN_USERS", "").split(","))

ARTIFACT_STORAGE_FILENAME_MAX_LENGTH = 256

# Artifact policy
# Max reproduction requests should ideally never be lowered, only raised.
# Lowering the value will require complex custom migration logic
ARTIFACT_SHARING_MAX_REPRO_REQUESTS = 10

#####
#
# Email Configuration
#
#####
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("SMTP_HOST", "localhost")
EMAIL_PORT = os.getenv("SMTP_PORT", 25)
EMAIL_HOST_USER = os.getenv("SMTP_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("SMTP_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", f"no-reply@{TROVI_FQDN}")

# User News Outage Notification
OUTAGE_NOTIFICATION_EMAIL = os.getenv("OUTAGE_NOTIFICATION_EMAIL", "")

# Authentication
CHAMELEON_KEYCLOAK_SERVER_URL = os.environ.get("CHAMELEON_KEYCLOAK_SERVER_URL")
CHAMELEON_KEYCLOAK_REALM_NAME = os.environ.get("CHAMELEON_KEYCLOAK_REALM_NAME")
CHAMELEON_KEYCLOAK_TROVI_ADMIN_CLIENT_ID = os.environ.get(
    "CHAMELEON_KEYCLOAK_TROVI_ADMIN_CLIENT_ID"
)
CHAMELEON_KEYCLOAK_TROVI_ADMIN_CLIENT_SECRET = os.environ.get(
    "CHAMELEON_KEYCLOAK_TROVI_ADMIN_CLIENT_SECRET"
)
CHAMELEON_KEYCLOAK_DEFAULT_SIGNING_ALGORITHM = "RS256"

# Application definition

INSTALLED_APPS = [
    # Core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Plugins
    "rest_framework",
    "drf_spectacular",
    # Trovi
    "trovi.apps.TroviConfig",
    "trovi.api.apps.ApiConfig",
    "trovi.auth.apps.AuthConfig",
    "trovi.docs.apps.DocsConfig",
    "trovi.storage.apps.StorageConfig",
    "trovi.meta.apps.MetaConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "trovi.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "trovi.wsgi.application"


DATETIME_FORMAT = "%Y-%m-%dT%H:%M%Z"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DATETIME_FORMAT": DATETIME_FORMAT,
    "ORDERING_PARAM": "sort_by",
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_SCHEMA_CLASS": "trovi.common.schema.APIViewSetAutoSchema",
}


# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

if os.getenv("DB_ENGINE"):
    DATABASES = {
        "default": {
            "ENGINE": os.getenv("DB_ENGINE"),
            "NAME": os.getenv("DB_NAME"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

FILE_UPLOAD_HANDLERS = [
    "trovi.storage.handlers.StreamingFileUploadHandler",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
]

# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = "/static/"

# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

#####
#
# Logger config
#
#####
LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO")
LOG_VERBOSITY = os.getenv("DJANGO_LOG_VERBOSITY", "SHORT")
SQL_LEVEL = os.getenv("DJANGO_SQL_LEVEL", "INFO")
SQL_VERBOSITY = os.getenv("DJANGO_SQL_VERBOSITY", "SHORT")
CONSOLE_WIDTH = os.getenv("DJANGO_LOG_WIDTH", 100)
CONSOLE_INDENT = os.getenv("DJANGO_LOG_INDENT", 2)

# Ensure Python `warnings` are ingested by logging infra
logging.captureWarnings(True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
    },
    "formatters": {
        "default_short": {
            "format": "[DJANGO] %(levelname)s %(name)s.%(funcName)s: %(message)s"
        },
        "default_verbose": {
            "format": "[DJANGO] %(levelname)s %(asctime)s %(module)s %(name)s.%(funcName)s: %(message)s"
        },
        "sql_short": {
            "format": "[DJANGO-SQL] [%(duration).3f] %(sql)s",
        },
        "sql_verbose": {
            "()": "util.sql_format.SQLFormatter",
            "format": "[DJANGO-SQL] [%(duration).3f] %(statement)s",
        },
    },
    "handlers": {
        "console": {
            "level": LOG_LEVEL,
            "class": "logging.StreamHandler",
            "formatter": f"default_{LOG_VERBOSITY.lower()}",
        },
        "console-sql": {
            "filters": ["require_debug_true"],
            "level": SQL_LEVEL,
            "class": "logging.StreamHandler",
            "formatter": f"sql_{SQL_VERBOSITY.lower()}",
        },
    },
    "loggers": {
        "default": {"handlers": ["console"], "level": "DEBUG"},
        "console": {"handlers": ["console"], "level": "DEBUG"},
        "django": {"handlers": ["console"], "level": "INFO"},
        "py.warnings": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": True,
        },
        "django.db.backends": {
            "handlers": ["console-sql"],
            "level": "DEBUG",
            "propagate": False,
        },
        "pipeline": {"handlers": ["console"], "level": "INFO"},
        "pytas": {"handlers": ["console"], "level": "INFO"},
        "chameleon_cms_integrations": {"handlers": ["console"], "level": "INFO"},
        "openid": {"handlers": ["console"], "level": "INFO"},
        "chameleon": {"handlers": ["console"], "level": "INFO"},
        "auth": {"handlers": ["console"], "level": "INFO"},
        "tas": {"handlers": ["console"], "level": "INFO"},
        "projects": {"handlers": ["console"], "level": "INFO"},
        "sharing_portal": {"handlers": ["console"], "level": "INFO"},
        "allocations": {"handlers": ["console"], "level": "INFO"},
        "chameleon_mailman": {"handlers": ["console"], "level": "INFO"},
        "util": {"handlers": ["console"], "level": "INFO"},
    },
}

# Testing
TEST_RUNNER = "util.test.SampleDataTestRunner"

# Documentation
SPECTACULAR_SETTINGS = {
    "TITLE": "Trovi API",
    "DESCRIPTION": "A collection of shared artifacts.",
    "VERSION": "0",
}

# Constraints
URN_MAX_CHARS = 254
GITHUB_USERNAME_MAX_CHARS = 40
GITHUB_REPO_NAME_MAX_CHARS = 40
GIT_BRANCH_NAME_MAX_CHARS = 28
SLUG_MAX_CHARS = 16
EMAIL_ADDRESS_MAX_CHARS = 254
SHARING_KEY_LENGTH = 33

AUTH_TROVI_TOKEN_LIFESPAN_SECONDS = 300  # 5 minutes
AUTH_JWT_MAX_FIELD_LENGTH = 255
# In prod, JWT signing keys should be ephemeral, tied on Trovi's runtime.
# This serves the purpose of both rotating keys over time,
# and ensuring that all keys from before a particular revision
# are automatically revoked
AUTH_TROVI_TOKEN_SIGNING_KEY = os.environ.get(
    "TROVI_TOKEN_SIGNING_KEY", secrets.token_urlsafe(nbytes=256)
)
AUTH_TROVI_TOKEN_SIGNING_ALGORITHM = "HS256"
AUTH_IDP_SIGNING_KEY_REFRESH_RETRY_ATTEMPTS = 5
AUTH_IDP_SIGNING_KEY_REFRESH_RETRY_SECONDS = 2
# TODO allow this to be pluggable by third party IdPs
AUTH_APPROVED_AUTHORIZED_PARTIES = set(
    os.environ.get("AUTH_APPROVED_AUTHORIZED_PARTIES").split(",")
)
AUTH_TOKEN_CONVERSION_CACHE_SIZE = 256

ARTIFACT_TITLE_MAX_CHARS = 70
ARTIFACT_SHORT_DESCRIPTION_MAX_CHARS = 70
ARTIFACT_LONG_DESCRIPTION_MAX_CHARS = 5000

ARTIFACT_TAG_MAX_CHARS = 32

ARTIFACT_AUTHOR_NAME_MAX_CHARS = 200
ARTIFACT_AUTHOR_AFFILIATION_MAX_CHARS = 200

ARTIFACT_LINK_LABEL_MAX_CHARS = 40

STORAGE_BACKEND_AUTH_RETRY_ATTEMPTS = 5
