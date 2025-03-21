from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, assert_type
from uuid import UUID

from django.test import TestCase
from django_stubs_ext.db.models.manager import RelatedManager

from .models import (
    Color,
    Inventory,
    Product,
    ProductAttributes,
    ProductQty,
    ProductQtyField,
    Rating,
    RatingField,
    Size,
    Store,
    StoreID,
    StoreIDAutoField,
)

if TYPE_CHECKING:
    from django.db.models.fields import _FieldDescriptor

    # id is not defined as null=True (it's the primary key). But it should be
    # marked as being nullable since it will be null on unsaved instances
    assert_type(
        Store.id,
        _FieldDescriptor[StoreIDAutoField[StoreID | None, StoreID]],
    )
    assert_type(
        Store.rating,
        # Even though RatingField doesn't define it's type as maybe null, the
        # django mypy plugin picks up the null=True kwargs and updates the
        # get/set types.
        _FieldDescriptor[RatingField[Rating | None, Rating | None]],
    )
    assert_type(
        Inventory.qty_in_stock,
        _FieldDescriptor[ProductQtyField[ProductQty, ProductQty]],
    )
    assert_type(
        Inventory.qty_allocated,
        _FieldDescriptor[ProductQtyField[ProductQty, ProductQty]],
    )


class NewTypeFieldTest(TestCase):
    def setUp(self) -> None:
        self.store = Store()
        self.store.rating = Rating(4)
        self.store.save()
        self.store.refresh_from_db()

        self.product = Product()
        self.product.attrs = ProductAttributes(
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
        self.product.save()
        self.product.refresh_from_db()

        self.inv = Inventory()
        self.inv.store = self.store
        self.inv.product = self.product
        self.inv.qty_in_stock = ProductQty(10)
        self.inv.qty_allocated = ProductQty(10)
        self.inv.save()
        self.inv.refresh_from_db()

    def test_store_instance_types(self) -> None:
        assert_type(self.store.pk, StoreID)
        assert_type(self.store.id, StoreID)
        assert_type(self.store.rating, Rating | None)
        assert_type(self.store.inventory, RelatedManager[Inventory])
        # At runtime, NewType doesn't exist just an int
        self.assertIsInstance(self.store.id, int)
        self.assertIsInstance(self.store.rating, int)

    def test_product_instance_types(self) -> None:
        assert_type(self.product.pk, int)
        assert_type(self.product.id, int)
        assert_type(self.product.attrs, ProductAttributes)
        assert_type(self.product.inventory, RelatedManager[Inventory])

    def test_inventory_instance_types(self) -> None:
        assert_type(self.inv.store, Store)
        assert_type(self.inv.store_id, StoreID)
        assert_type(self.inv.store.rating, Rating | None)
        assert_type(self.inv.qty_in_stock, ProductQty)
        assert_type(self.inv.qty_allocated, ProductQty)
