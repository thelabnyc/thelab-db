from django.apps import apps
from django.conf import settings
import django

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "thelabdb",
    "thelabdb.pgviews",
]

SECRET_KEY = "secret"

if not apps.ready and not settings.configured:
    django.setup()

import django_stubs_ext  # NOQA

django_stubs_ext.monkeypatch()

setup = None
