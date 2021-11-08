"""
Django settings for trovi project.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""
import logging
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-a-+g)^dtso--4cnaw*dlnst3fq+x$znmp=u$*39y2-h6q8=ejm",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_ENV", "DEBUG") == "DEBUG"

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

ALLOWED_HOSTS = [
    # We don't need to add localhost here, since DEBUG mode automatically allows it
    # TODO future Trovi domain name, reverse-proxy
]

# OpenStack Properties
OPENSTACK_UC_REGION = os.environ.get("OPENSTACK_UC_REGION", "CHI@UC")
OPENSTACK_TACC_REGION = os.environ.get("OPENSTACK_TACC_REGION", "CHI@TACC")
OPENSTACK_SERVICE_USERNAME = os.environ.get("OPENSTACK_SERVICE_USERNAME", "")
OPENSTACK_SERVICE_PASSWORD = os.environ.get("OPENSTACK_SERVICE_PASSWORD", "")
OPENSTACK_SERVICE_PROJECT_ID = os.environ.get("OPENSTACK_SERVICE_PROJECT_ID", "")
OPENSTACK_SERVICE_PROJECT_NAME = os.environ.get(
    "OPENSTACK_SERVICE_PROJECT_NAME", "services"
)
OPENSTACK_AUTH_REGIONS = {
    OPENSTACK_UC_REGION: os.environ.get(
        "OPENSTACK_UC_AUTH_URL", "https://chi.uc.chameleoncloud.org:5000/v3"
    ),
    OPENSTACK_TACC_REGION: os.environ.get(
        "OPENSTACK_TACC_AUTH_URL", "https://chi.tacc.chameleoncloud.org:5000/v3"
    ),
}

# Artifact storage
ARTIFACT_SHARING_SWIFT_ENDPOINT = os.getenv("ARTIFACT_SHARING_SWIFT_ENDPOINT")
ARTIFACT_SHARING_SWIFT_TEMP_URL = os.getenv("ARTIFACT_SHARING_SWIFT_TEMP_URL")
ARTIFACT_SHARING_SWIFT_CONTAINER = os.getenv(
    "ARTIFACT_SHARING_SWIFT_CONTAINER", "trovi"
)
ARTIFACT_SHARING_JUPYTERHUB_URL = os.getenv(
    "ARTIFACT_SHARING_JUPYTERHUB_URL", "https://jupyter.chameleoncloud.org"
)
ZENODO_URL = os.getenv("ZENODO_URL", "https://zenodo.org")
ZENODO_DEFAULT_ACCESS_TOKEN = os.getenv("ZENODO_DEFAULT_ACCESS_TOKEN")

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
EMAIL_HOST = os.environ.get("SMTP_HOST", "localhost")
EMAIL_PORT = os.environ.get("SMTP_PORT", 25)
EMAIL_HOST_USER = os.environ.get("SMTP_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
# TODO replace chameleoncloud.org with trovi URL
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@chameleoncloud.org")

# User News Outage Notification
OUTAGE_NOTIFICATION_EMAIL = os.environ.get("OUTAGE_NOTIFICATION_EMAIL", "")


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
    # Trovi
    "trovi.apps.TroviConfig",
    "trovi.api.apps.ApiConfig",
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
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly"
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DATETIME_FORMAT": DATETIME_FORMAT,
    "ORDERING_PARAM": "sort_by"
}


# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

if os.environ.get("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("DB_NAME"),
            "HOST": os.environ.get("DB_HOST"),
            "PORT": os.environ.get("DB_PORT"),
            "USER": os.environ.get("DB_USER"),
            "PASSWORD": os.environ.get("DB_PASSWORD"),
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
LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "INFO")
LOG_VERBOSITY = os.environ.get("DJANGO_LOG_VERBOSITY", "SHORT")
SQL_LEVEL = os.environ.get("DJANGO_SQL_LEVEL", "INFO")
SQL_VERBOSITY = os.environ.get("DJANGO_SQL_VERBOSITY", "SHORT")
CONSOLE_WIDTH = os.environ.get("DJANGO_LOG_WIDTH", 100)
CONSOLE_INDENT = os.environ.get("DJANGO_LOG_INDENT", 2)

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

# Constraints
URN_MAX_CHARS = 254
GITHUB_USERNAME_MAX_CHARS = 40
GITHUB_REPO_NAME_MAX_CHARS = 40
GIT_BRANCH_NAME_MAX_CHARS = 28
SLUG_MAX_CHARS = 16
EMAIL_ADDRESS_MAX_CHARS = 254
SHARING_KEY_LENGTH = 33

ARTIFACT_TITLE_MAX_CHARS = 70
ARTIFACT_SHORT_DESCRIPTION_MAX_CHARS = 70
ARTIFACT_LONG_DESCRIPTION_MAX_CHARS = 5000

ARTIFACT_TAG_MAX_CHARS = 32

ARTIFACT_AUTHOR_NAME_MAX_CHARS = 200
ARTIFACT_AUTHOR_AFFILIATION_MAX_CHARS = 200

ARTIFACT_LINK_LABEL_MAX_CHARS = 40
