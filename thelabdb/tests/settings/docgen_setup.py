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

setup = None
import django  # noqa
from django.apps import apps  # noqa
from django.conf import settings  # noqa

if not apps.ready and not settings.configured:
    django.setup()
