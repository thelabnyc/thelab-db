import os

import django_stubs_ext

django_stubs_ext.monkeypatch()

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "thelabdb",
    "thelabdb.tests.testsuniv",
]

SECRET_KEY = "secret"

# Pin this rather than inheriting it; the default flipped in Django 5.0 and
# the tox matrix straddles that change.
USE_TZ = True

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "testdb.sqlite")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB,
        "TEST": {
            "NAME": DB,
        },
    },
}
