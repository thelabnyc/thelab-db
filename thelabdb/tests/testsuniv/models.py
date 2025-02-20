from datetime import datetime, timezone
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import NewType, Optional
from uuid import UUID

from django.db import models
import pydantic

import thelabdb.fields


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


StoreID = NewType("StoreID", int)


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
    discontinued_dt: Optional[datetime] = None


class Product(models.Model):
    attrs = thelabdb.fields.PydanticField(ProductAttributes)
