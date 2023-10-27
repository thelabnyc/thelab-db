import os

from .base import *  # noqa

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
