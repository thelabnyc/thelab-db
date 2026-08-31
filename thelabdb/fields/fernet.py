from collections.abc import Callable
from typing import Any, TypeVar

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import FieldError, ImproperlyConfigured
from django.db import models
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.models.expressions import Col
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.functional import cached_property

from . import hkdf

Validator = Callable[[str | None], None]

_ST_contra = TypeVar("_ST_contra", contravariant=True)
_GT_co = TypeVar("_GT_co", covariant=True)


class EncryptedField(models.Field[_ST_contra, _GT_co]):
    """
    A field that encrypts values using Fernet symmetric encryption. Designed to
    be used as a class mixin, along with another built-in field type.

    For example:

    ```py
    from django.db import models
    from thelabdb.fields import EncryptedField

    class EncryptedTextField(EncryptedField, models.TextField):
        pass
    ```
    """

    _internal_type = "BinaryField"

    def __init__(self, *args: Any, **kwargs: Any):
        if kwargs.get("primary_key"):
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} does not support primary_key=True."
            )
        if kwargs.get("unique"):
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} does not support unique=True."
            )
        if kwargs.get("db_index"):
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} does not support db_index=True."
            )
        super().__init__(*args, **kwargs)

    @cached_property
    def keys(self) -> list[str | bytes]:
        keys = getattr(settings, "FERNET_KEYS", None)
        if keys is None:
            keys = [settings.SECRET_KEY]
        return keys

    @cached_property
    def fernet_keys(self) -> list[bytes]:
        if getattr(settings, "FERNET_USE_HKDF", True):
            return [hkdf.derive_fernet_key(k) for k in self.keys]
        return [force_bytes(k) for k in self.keys]

    @cached_property
    def fernet(self) -> MultiFernet | Fernet:
        if len(self.fernet_keys) == 1:
            return Fernet(self.fernet_keys[0])
        return MultiFernet([Fernet(k) for k in self.fernet_keys])

    def get_internal_type(self) -> str:
        return self._internal_type

    def get_db_prep_save(
        self,
        value: Any,
        connection: BaseDatabaseWrapper,
    ) -> Any:
        value = super().get_db_prep_save(value, connection)
        if value is not None:
            retval = self.fernet.encrypt(force_bytes(value))
            return connection.Database.Binary(retval)  # type:ignore[attr-defined]
        return None

    def from_db_value(
        self,
        value: bytes | None,
        expression: Col,
        connection: BaseDatabaseWrapper,
        *args: Any,
    ) -> Any:
        if value is not None:
            value = bytes(value)
            return self.to_python(force_str(self.fernet.decrypt(value)))
        return None

    @cached_property
    def validators(
        self,
    ) -> list[Validator]:
        # Temporarily pretend to be whatever type of field we're masquerading
        # as, for purposes of constructing validators (needed for
        # IntegerField and subclasses).
        self.__dict__["_internal_type"] = super().get_internal_type()
        try:
            return super().validators
        finally:
            del self.__dict__["_internal_type"]


def get_prep_lookup[T](self: models.Lookup[T]) -> Any:
    """Raise errors for unsupported lookups"""
    raise FieldError(
        f"{self.lhs.field.__class__.__name__} '{self.lookup_name}' does not support lookups"
    )


# Register all field lookups (except 'isnull') to our handler
for name, lookup in models.Field.class_lookups.items():
    # Dynamically create classes that inherit from the right lookups
    if name != "isnull":
        lookup_class = type(
            "EncryptedField" + name,
            (lookup,),
            {
                "get_prep_lookup": get_prep_lookup,
            },
        )
        EncryptedField.register_lookup(lookup_class)


class EncryptedTextField(
    EncryptedField[_ST_contra, _GT_co],
    models.TextField[_ST_contra, _GT_co],
):
    """
    Fernet encrypted version of Django's built-in
    [TextField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.TextField).
    """


class EncryptedCharField(
    EncryptedField[_ST_contra, _GT_co],
    models.CharField[_ST_contra, _GT_co],
):
    """
    Fernet encrypted version of Django's built-in
    [CharField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.CharField).
    """


class EncryptedEmailField(
    EncryptedField[_ST_contra, _GT_co],
    models.EmailField[_ST_contra, _GT_co],
):
    """
    Fernet encrypted version of Django's built-in
    [EmailField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.EmailField).
    """


class EncryptedIntegerField(
    EncryptedField[_ST_contra, _GT_co],
    models.IntegerField[_ST_contra, _GT_co],
):
    """
    Fernet encrypted version of Django's built-in
    [IntegerField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.IntegerField).
    """

    def get_db_prep_value(
        self,
        value: int | None,
        connection: BaseDatabaseWrapper,
        prepared: bool = False,
    ) -> int | None:
        # This gets around calling DatabaseOperations.adapt_integerfield_value
        # when using Psycopg3
        return models.Field.get_db_prep_value(  # type:ignore[no-any-return]
            self,
            value,
            connection,
            prepared,
        )


class EncryptedDateField(
    EncryptedField[_ST_contra, _GT_co],
    models.DateField[_ST_contra, _GT_co],
):
    """
    Fernet encrypted version of Django's built-in
    [DateField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.DateField).
    """


class EncryptedDateTimeField(
    EncryptedField[_ST_contra, _GT_co],
    models.DateTimeField[_ST_contra, _GT_co],
):
    """
    Fernet encrypted version of Django's built-in
    [DateTimeField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.DateTimeField).
    """

    def from_db_value(
        self,
        value: bytes | None,
        expression: Col,
        connection: BaseDatabaseWrapper,
        *args: Any,
    ) -> Any:
        dt = super().from_db_value(value, expression, connection, *args)
        # Encrypted columns are BinaryField as far as the backend is concerned,
        # so the backend's own datetime converter never runs on them.
        if dt is not None and settings.USE_TZ and timezone.is_naive(dt):
            dt = timezone.make_aware(dt, connection.timezone)
        return dt


__all__ = [
    "EncryptedCharField",
    "EncryptedDateField",
    "EncryptedDateTimeField",
    "EncryptedEmailField",
    "EncryptedField",
    "EncryptedIntegerField",
    "EncryptedTextField",
]
