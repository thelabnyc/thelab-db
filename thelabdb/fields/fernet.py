from collections.abc import Callable
from typing import Any, TypeVar

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import FieldError, ImproperlyConfigured
from django.db import models
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.models.expressions import Col
from django.utils.encoding import force_bytes, force_str
from django.utils.functional import cached_property

from . import hkdf

Validator = Callable[[str | None], None]

_ST = TypeVar("_ST", contravariant=True)
_GT = TypeVar("_GT", covariant=True)


class EncryptedField(models.Field[_ST, _GT]):
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
                "%s does not support primary_key=True." % self.__class__.__name__
            )
        if kwargs.get("unique"):
            raise ImproperlyConfigured(
                "%s does not support unique=True." % self.__class__.__name__
            )
        if kwargs.get("db_index"):
            raise ImproperlyConfigured(
                "%s does not support db_index=True." % self.__class__.__name__
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
    ) -> str | int | None:
        if value is not None:
            value = bytes(value)
            return self.to_python(  # type:ignore[no-any-return]
                force_str(self.fernet.decrypt(value))
            )
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


def get_prep_lookup[_T](self: models.Lookup[_T]) -> Any:
    """Raise errors for unsupported lookups"""
    raise FieldError(
        "{} '{}' does not support lookups".format(
            self.lhs.field.__class__.__name__, self.lookup_name
        )
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
    EncryptedField[_ST, _GT],
    models.TextField[_ST, _GT],
):
    """
    Fernet encrypted version of Django's built-in
    [TextField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.TextField).
    """

    pass


class EncryptedCharField(
    EncryptedField[_ST, _GT],
    models.CharField[_ST, _GT],
):
    """
    Fernet encrypted version of Django's built-in
    [CharField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.CharField).
    """

    pass


class EncryptedEmailField(
    EncryptedField[_ST, _GT],
    models.EmailField[_ST, _GT],
):
    """
    Fernet encrypted version of Django's built-in
    [EmailField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.EmailField).
    """

    pass


class EncryptedIntegerField(
    EncryptedField[_ST, _GT],
    models.IntegerField[_ST, _GT],
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
    EncryptedField[_ST, _GT],
    models.DateField[_ST, _GT],
):
    """
    Fernet encrypted version of Django's built-in
    [DateField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.DateField).
    """

    pass


class EncryptedDateTimeField(
    EncryptedField[_ST, _GT],
    models.DateTimeField[_ST, _GT],
):
    """
    Fernet encrypted version of Django's built-in
    [DateTimeField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.DateTimeField).
    """

    pass


__all__ = [
    "EncryptedField",
    "EncryptedTextField",
    "EncryptedCharField",
    "EncryptedEmailField",
    "EncryptedIntegerField",
    "EncryptedDateField",
    "EncryptedDateTimeField",
]
