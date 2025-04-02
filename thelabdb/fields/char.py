from collections.abc import Sequence
from typing import Any, Self, TypeVar

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models

_ST = TypeVar("_ST", contravariant=True)
_GT = TypeVar("_GT", covariant=True)


class Creator[_ST, _GT]:
    """
    A placeholder class that provides a way to set the attribute on the model.
    """

    def __init__(self, field: models.Field[_ST, _GT]):
        self.field = field

    def __get__(
        self,
        obj: models.Model,
        type: type[models.Model] | None = None,
    ) -> Self | str | None:
        if obj is None:
            return self
        return obj.__dict__[self.field.name]  # type:ignore[no-any-return]

    def __set__(
        self,
        obj: models.Model,
        value: str | None,
    ) -> None:
        obj.__dict__[self.field.name] = self.field.to_python(value)


class UppercaseCharField(models.CharField[_ST, _GT]):
    """
    A simple subclass of `django.db.models.fields.CharField` that
    restricts all text to be uppercase.
    """

    def contribute_to_class(
        self,
        cls: type[models.Model],
        name: str,
        private_only: bool = False,
    ) -> None:
        super().contribute_to_class(cls, name, private_only)
        setattr(cls, self.name, Creator(self))

    def from_db_value(self, value: str | None, *args: Any, **kwargs: Any) -> str | None:
        return self.to_python(value)

    def to_python(self, value: str | None) -> str | None:
        val = super().to_python(value)
        if val is None:
            return None
        if isinstance(val, str):
            return val.upper()
        raise ValidationError(f"Cannot assign {val} to {self.__class__}")


class NullCharField(models.CharField[_ST, _GT]):
    """
    CharField that stores '' as None and returns None as ''
    Useful when using unique=True and forms. Implies null==blank==True.

    Django's CharField stores '' as None, but does not return None as ''.
    """

    description = "CharField that stores '' as None and returns None as ''"

    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ):
        if not kwargs.get("null", True) or not kwargs.get("blank", True):
            raise ImproperlyConfigured("NullCharField implies null==blank==True")
        kwargs["null"] = kwargs["blank"] = True
        super().__init__(**kwargs)

    def contribute_to_class(
        self,
        cls: type[models.Model],
        name: str,
        private_only: bool = False,
    ) -> None:
        super().contribute_to_class(cls, name, private_only)
        setattr(cls, self.name, Creator(self))

    def from_db_value(self, value: str | None, *args: Any, **kwargs: Any) -> str:
        """
        DB -> Python: If the DB value is null, load as empty string into Python.
        """
        value = self.to_python(value)
        # If the value was stored as null, return empty string instead
        return value if value is not None else ""

    def get_prep_value(self, value: str) -> str | None:
        """
        Python -> DB: If the python value is empty string, make the DB value null.
        """
        prepped = super().get_prep_value(value)
        return prepped if prepped != "" else None

    def deconstruct(
        self,
    ) -> tuple[str, str, Sequence[Any], dict[str, Any]]:
        """
        deconstruct() is needed by Django's migration framework
        """
        name, path, args, kwargs = super().deconstruct()
        del kwargs["null"]
        del kwargs["blank"]
        return name, path, args, kwargs
