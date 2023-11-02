import os

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
