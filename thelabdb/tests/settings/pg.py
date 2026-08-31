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
    "thelabdb.pgviews",
    "thelabdb.tests.testsuniv",
    "thelabdb.tests.testspg",
]

SECRET_KEY = "secret"

# Pin this rather than inheriting it; the default flipped in Django 5.0 and
# the tox matrix straddles that change.
USE_TZ = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "postgres",
        "USER": "postgres",
        "PASSWORD": "",
        "HOST": "postgres",
        "PORT": 5432,
    },
}
