from datetime import date, datetime
from typing import cast

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import FieldError, ImproperlyConfigured
from django.db import connection
from django.db import models as dj_models
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes, force_str

import thelabdb.fields

from . import models

k1 = Fernet.generate_key()


class EncryptedFieldTest(TestCase):
    @override_settings(FERNET_KEYS=["secret"])
    def test_key_from_settings(self) -> None:
        f = thelabdb.fields.EncryptedTextField[str, str]()
        self.assertEqual(f.keys, settings.FERNET_KEYS)  # type:ignore[misc]

    def test_fallback_to_secret_key(self) -> None:
        """If no FERNET_KEY setting, use SECRET_KEY."""
        f = thelabdb.fields.EncryptedTextField[str, str]()
        self.assertEqual(f.keys, [settings.SECRET_KEY])

    @override_settings(FERNET_KEYS=["key1", "key2"])
    def test_key_rotation(self) -> None:
        """Can supply multiple `keys` for key rotation."""
        f = thelabdb.fields.EncryptedTextField[str, str]()

        enc1 = Fernet(f.fernet_keys[0]).encrypt(b"enc1")
        enc2 = Fernet(f.fernet_keys[1]).encrypt(b"enc2")

        self.assertEqual(f.fernet.decrypt(enc1), b"enc1")
        self.assertEqual(f.fernet.decrypt(enc2), b"enc2")

    @override_settings(FERNET_USE_HKDF=False, FERNET_KEYS=[k1])
    def test_no_hkdf(self) -> None:
        """Can set FERNET_USE_HKDF=False to avoid HKDF."""
        f = thelabdb.fields.EncryptedTextField[str, str]()
        fernet = Fernet(k1)
        self.assertEqual(fernet.decrypt(f.fernet.encrypt(b"foo")), b"foo")

    def test_not_allowed(self) -> None:
        for param in ["primary_key", "db_index", "unique"]:
            with self.subTest(param=param):
                with self.assertRaises(ImproperlyConfigured):
                    thelabdb.fields.EncryptedIntegerField(**{param: True})

    def test_get_integer_field_validators(self) -> None:
        f = thelabdb.fields.EncryptedIntegerField[int, int]()
        # Raises no error
        f.validators

    def test_nullable(self) -> None:
        """Encrypted/dual/hash field can be nullable."""
        models.EncryptedNullable._default_manager.create(value=None)
        found = models.EncryptedNullable._default_manager.get()
        self.assertIsNone(found.value)

    def test_isnull_false_lookup(self) -> None:
        """isnull False lookup succeeds on nullable fields"""
        test_val = 3
        models.EncryptedNullable._default_manager.create(value=None)
        models.EncryptedNullable._default_manager.create(value=test_val)
        found = models.EncryptedNullable._default_manager.get(value__isnull=False)
        self.assertEqual(found.value, test_val)

    def test_isnull_true_lookup(self) -> None:
        """isnull True lookup succeeds on nullable fields"""
        test_val = 3
        models.EncryptedNullable._default_manager.create(value=None)
        models.EncryptedNullable._default_manager.create(value=test_val)
        found = models.EncryptedNullable._default_manager.get(value__isnull=True)
        self.assertIsNone(found.value)


class EncryptedTextQueryTest(TestCase):
    model = models.EncryptedText
    values = ["foo", "bar"]

    def test_insert(self) -> None:
        """Data stored in DB is actually encrypted."""
        field = cast(
            thelabdb.fields.EncryptedTextField[str, str],
            self.model._meta.get_field("value"),
        )
        self.model._default_manager.create(value=self.values[0])
        with connection.cursor() as cur:
            cur.execute("SELECT value FROM %s" % self.model._meta.db_table)
            data = [
                force_str(field.fernet.decrypt(force_bytes(r[0])))
                for r in cur.fetchall()
            ]

        self.assertEqual(list(map(field.to_python, data)), [self.values[0]])

    def test_insert_and_select(self) -> None:
        """Data round-trips through insert and select."""
        self.model._default_manager.create(value=self.values[0])
        found = self.model._default_manager.get()

        self.assertEqual(found.value, self.values[0])

    def test_update_and_select(self) -> None:
        """Data round-trips through update and select."""
        self.model._default_manager.create(value=self.values[0])
        self.model._default_manager.update(value=self.values[1])
        found = self.model._default_manager.get()

        self.assertEqual(found.value, self.values[1])

    def test_lookups_raise_field_error(self) -> None:
        """Lookups are not allowed (they cannot succeed)."""
        self.model._default_manager.create(value=self.values[0])
        field_name = self.model._meta.get_field("value").__class__.__name__
        lookups = set(dj_models.Field.class_lookups) - {"isnull"}

        for lookup in lookups:
            with self.assertRaises(FieldError) as cm:
                self.model._default_manager.get(**{"value__" + lookup: self.values[0]})
            exc = cm.exception
            self.assertIn(field_name, str(exc))
            self.assertIn(lookup, str(exc))
            self.assertIn("does not support lookups", str(exc))


class EncryptedCharQueryTest(TestCase):
    model = models.EncryptedChar
    values = ["one", "two"]


class EncryptedEmailQueryTest(TestCase):
    model = models.EncryptedEmail
    values = ["a@example.com", "b@example.com"]


class EncryptedIntQueryTest(TestCase):
    model = models.EncryptedInt
    values = [1, 2]


class EncryptedDateQueryTest(TestCase):
    model = models.EncryptedDate
    values = [date(2015, 2, 5), date(2015, 2, 8)]


class EncryptedDateTimeQueryTest(TestCase):
    model = models.EncryptedDateTime
    values = [datetime(2015, 2, 5, 15), datetime(2015, 2, 8, 16)]
