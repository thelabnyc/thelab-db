from datetime import datetime, timezone
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import NewType, TypeVar
from uuid import UUID

from django.db import models
import pydantic

import thelabdb.fields


class UppercaseChar(models.Model):
    value = thelabdb.fields.UppercaseCharField(max_length=25)


class NullChar(models.Model):
    value = thelabdb.fields.NullCharField(max_length=25)


class EncryptedText(models.Model):
    value = thelabdb.fields.EncryptedTextField()


class EncryptedChar(models.Model):
    value = thelabdb.fields.EncryptedCharField(max_length=25)


class EncryptedEmail(models.Model):
    value = thelabdb.fields.EncryptedEmailField()


class EncryptedInt(models.Model):
    value = thelabdb.fields.EncryptedIntegerField()


class EncryptedDate(models.Model):
    value = thelabdb.fields.EncryptedDateField()


class EncryptedDateTime(models.Model):
    value = thelabdb.fields.EncryptedDateTimeField()


class EncryptedNullable(models.Model):
    value = thelabdb.fields.EncryptedIntegerField(null=True)


_T = TypeVar("_T")
_ST = TypeVar("_ST", contravariant=True)
_GT = TypeVar("_GT", covariant=True)

StoreID = NewType("StoreID", int)
Rating = NewType("Rating", int)
ProductQty = NewType("ProductQty", int)


class StoreIDAutoField(models.AutoField[_ST, _GT]):
    _pyi_private_set_type: StoreID
    _pyi_private_get_type: StoreID
    _pyi_lookup_exact_type: StoreID


class RatingField(models.SmallIntegerField[_ST, _GT]):
    _pyi_private_set_type: Rating
    _pyi_private_get_type: Rating
    _pyi_lookup_exact_type: Rating


class ProductQtyField(models.IntegerField[_ST, _GT]):
    _pyi_private_set_type: ProductQty
    _pyi_private_get_type: ProductQty
    _pyi_lookup_exact_type: ProductQty


class Store(models.Model):
    id = StoreIDAutoField(primary_key=True)
    rating = RatingField("Store Rating", null=True)


class Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class Size(IntEnum):
    SM = 1
    MD = 2
    LG = 3


class ProductAttributes(pydantic.BaseModel):
    """Pydantic Model that stores a variety of different data types"""

    uuid: UUID
    online: bool
    in_store_locations: list[StoreID]
    price: Decimal
    color: Color
    size: Size
    first_available_dt: datetime = pydantic.Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    discontinued_dt: datetime | None = None


class Product(models.Model):
    attrs = thelabdb.fields.PydanticField(ProductAttributes)


class Inventory(models.Model):
    store = models.ForeignKey(
        Store,
        related_name="inventory",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        Product,
        related_name="inventory",
        on_delete=models.CASCADE,
    )
    qty_in_stock = ProductQtyField("Qty In Stock")
    qty_allocated = ProductQtyField("Qty Allocated")
