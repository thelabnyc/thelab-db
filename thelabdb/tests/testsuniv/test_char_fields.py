from typing import assert_type

from cryptography.fernet import Fernet
from django.db import connection
from django.test import TestCase

from . import models

k1 = Fernet.generate_key()


class UppercaseCharFieldTest(TestCase):
    def test_forces_text_uppercase(self) -> None:
        obj = models.UppercaseChar.objects.create(value="foo")
        assert_type(obj.value, str)
        self.assertEqual(obj.value, "FOO")
        # Check actual DB representation
        with connection.cursor() as cur:
            cur.execute("SELECT value FROM %s" % models.UppercaseChar._meta.db_table)
            rows = [r[0] for r in cur.fetchall()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], "FOO")

    def test_forces_text_uppercase_unsaved(self) -> None:
        obj = models.UppercaseChar()
        obj.value = "foo"
        assert_type(obj.value, str)
        self.assertEqual(obj.value, "FOO")


class NullCharFieldTest(TestCase):
    def test_nonempty_string(self) -> None:
        obj = models.NullChar.objects.create(value="foo")
        assert_type(obj.value, str)
        self.assertEqual(obj.value, "foo")
        # Check actual DB representation
        with connection.cursor() as cur:
            cur.execute("SELECT value FROM %s" % models.NullChar._meta.db_table)
            rows = [r[0] for r in cur.fetchall()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], "foo")

    def test_empty_string(self) -> None:
        obj = models.NullChar.objects.create(value="")
        assert_type(obj.value, str)
        self.assertEqual(obj.value, "")
        # Check actual DB representation
        with connection.cursor() as cur:
            cur.execute("SELECT value FROM %s" % models.NullChar._meta.db_table)
            rows = [r[0] for r in cur.fetchall()]
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0])

    def test_nonempty_string_unsaved(self) -> None:
        obj = models.NullChar()
        obj.value = "foo"
        assert_type(obj.value, str)
        self.assertEqual(obj.value, "foo")

    def test_empty_string_unsaved(self) -> None:
        obj = models.NullChar()
        obj.value = ""
        assert_type(obj.value, str)
        self.assertEqual(obj.value, "")
