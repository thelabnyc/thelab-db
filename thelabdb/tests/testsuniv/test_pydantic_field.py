from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models.fields.json import KT
from django.test import TestCase

from .models import Color, Product, ProductAttributes, Size, StoreID


class PydanticFieldTest(TestCase):
    def setUp(self) -> None:
        self.valid_attrs = ProductAttributes(
            uuid=UUID("d22f82ba-c94e-47ba-92cb-3e1eac6dd0de"),
            online=True,
            in_store_locations=[
                StoreID(123),
                StoreID(456),
            ],
            price=Decimal("123.45"),
            color=Color.RED,
            size=Size.LG,
            first_available_dt=datetime(2025, 2, 10, 12, 0, 0, tzinfo=UTC),
        )
        self.valid_attrs_dict = self.valid_attrs.model_dump(mode="json")
        # Use model_construct to force an obj instance with invalid data
        self.invalid_attrs = ProductAttributes.model_construct(
            uuid=UUID("d22f82ba-c94e-47ba-92cb-3e1eac6dd0de"),
            online="this should be a bool",
        )
        self.invalid_attrs_dict = self.invalid_attrs.model_dump(mode="json")

    def test_insert(self) -> None:
        """
        Pydantic model is serialized to JSON and stored in DB as a JSON field.
        """
        Product._default_manager.create(attrs=self.valid_attrs)
        with connection.cursor() as cur:
            cur.execute("SELECT attrs FROM %s" % Product._meta.db_table)
            rows = [r[0] for r in cur.fetchall()]
        self.assertEqual(len(rows), 1)
        self.assertJSONEqual(rows[0], self.valid_attrs_dict)

    def test_insert_and_select(self) -> None:
        """Data round-trips through insert and select."""
        Product._default_manager.create(attrs=self.valid_attrs)
        p = Product._default_manager.get()
        self.assertIsInstance(p, Product)
        self.assertIsInstance(p.attrs, ProductAttributes)
        self.assertEqual(p.attrs, self.valid_attrs)
        # Test that Enums work
        self.assertEqual(p.attrs.size, Size.LG)
        self.assertEqual(p.attrs.color, Color.RED)
        # Test that NewType work
        self.assertEqual(p.attrs.in_store_locations[0], StoreID(123))
        # Test that datetimes work
        self.assertIsInstance(p.attrs.first_available_dt, datetime)

    def test_update_and_select(self) -> None:
        """Data round-trips through update and select."""
        Product._default_manager.create(attrs=self.valid_attrs)

        attrs2 = self.valid_attrs.model_copy(deep=True)
        attrs2.online = False
        attrs2.in_store_locations = []
        Product._default_manager.update(attrs=attrs2)

        found = Product._default_manager.get()
        self.assertNotEqual(found.attrs, self.valid_attrs)
        self.assertEqual(found.attrs, attrs2)

    def test_query_properties(self) -> None:
        """Can use JSONField-style queries on model properties"""
        Product._default_manager.create(attrs=self.valid_attrs)

        objs = Product._default_manager.filter(attrs__color=Color.RED).all()
        self.assertEqual(objs.count(), 1)

        objs = Product._default_manager.filter(attrs__color=Color.BLUE).all()
        self.assertEqual(objs.count(), 0)

    def test_annotated_select(self) -> None:
        """Can use annotate() to extract properties from the field"""
        Product._default_manager.create(attrs=self.valid_attrs)
        p = (
            Product._default_manager.annotate(
                locations=KT("attrs__in_store_locations"),
                price=KT("attrs__price"),
            )
            .values("locations", "price")
            .first()
        )
        # TODO: This works, but the output is always just a string. Figure out
        # a better way to handle that.
        self.assertJSONEqual(p["locations"], [123, 456])  # type:ignore[index]
        self.assertEqual(p["price"], "123.45")  # type:ignore[index]

    def test_clean_valid(self) -> None:
        """Ensure Model.clean() passes when the model has valid data"""
        p = Product()
        p.attrs = self.valid_attrs
        p.full_clean()

    def test_clean_invalid_properties(self) -> None:
        """Ensure Model.clean() errs when the model has invalid data"""
        p = Product()
        p.attrs = self.invalid_attrs
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_clean_invalid_type(self) -> None:
        """
        Ensure Model.clean() errs when the attrs is set to something other than
        the model type
        """
        p = Product()
        p.attrs = 42  # type:ignore[assignment]
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_select_invalid(self) -> None:
        """Loading invalid data, by default, throws a ValidationError"""
        Product._default_manager.create(attrs=self.invalid_attrs)
        with self.assertRaises(ValidationError):
            Product._default_manager.get()

    def test_select_invalid_coerced(self) -> None:
        """Allow massaging invalid data upon load (e.g. for data migrations)"""
        coerce_fn = Mock()
        coerce_fn.return_value = self.valid_attrs_dict

        attrs_field = Product._meta.get_field("attrs")
        attrs_field.coerce_invalid_data = coerce_fn

        Product._default_manager.create(attrs=self.invalid_attrs)
        try:
            p = Product._default_manager.get()
            coerce_fn.assert_called_once_with(self.invalid_attrs_dict)
            self.assertIsInstance(p.attrs, ProductAttributes)
            self.assertEqual(p.attrs, self.valid_attrs)
        finally:
            attrs_field.coerce_invalid_data = None

    def test_select_invalid_forced(self) -> None:
        """Allows force loading invalid data"""
        attrs_field = Product._meta.get_field("attrs")
        attrs_field.force_load_invalid_data = True

        Product._default_manager.create(attrs=self.invalid_attrs)
        try:
            p = Product._default_manager.get()
            self.assertIsInstance(p.attrs, ProductAttributes)
            # Have to compare the dumped versions, since the UUID and dates
            # won't be correctly instantiated. They'll just be strings.
            # "Forced" isn't magic—we warned you the data would be invalid.
            self.assertEqual(p.attrs.model_dump(), self.invalid_attrs_dict)
        finally:
            attrs_field.force_load_invalid_data = False
