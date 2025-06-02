from collections.abc import Callable, Sequence
from typing import Any
import json

from django.core.exceptions import ValidationError
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.models import Model, expressions
from django.db.models.expressions import Expression
from django.db.models.fields.json import JSONField
from django.utils.translation import gettext_lazy as _
from django_stubs_ext import StrOrPromise
from thelabtyping.result import Err, Ok, Result
import pydantic
import pydantic_core


def _pyd_validation_error_to_django(
    err: pydantic.ValidationError,
) -> ValidationError:
    """
    Convert the Pydantic error into a Django error
    """
    return ValidationError(
        str(err),
        code="invalid",
        params={
            "details": err.errors(),
        },
    )


def _validate[T: pydantic.BaseModel](
    model_cls: type[T],
    value: str | bytes | dict[str, Any],
) -> Result[T, pydantic_core.ValidationError]:
    try:
        if isinstance(value, str) or isinstance(value, bytes):
            return Ok(model_cls.model_validate_json(value))
        return Ok(model_cls.model_validate(value))
    except pydantic_core.ValidationError as e:
        return Err(e)


class PydanticField[T: pydantic.BaseModel](JSONField[T, T]):
    """
    Subclass of Django's
    [JSONField](https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.JSONField).
    that uses a [Pydantic model](https://docs.pydantic.dev/latest/api/base_model/)
    for data validation both incoming and outgoing from the database.
    Essentially, a much more type-safe JSON field.
    """

    description = "A Pydantic model stored as JSON in the DB"

    model_cls: type[T]
    coerce_invalid_data: Callable[[Any], Any] | None
    force_load_invalid_data: bool

    def __init__(
        self,
        model_cls: type[T],
        verbose_name: StrOrPromise | None = None,
        name: str | None = None,
        coerce_invalid_data: Callable[[Any], Any] | None = None,
        force_load_invalid_data: bool = False,
        **kwargs: Any,
    ) -> None:
        self.model_cls = model_cls
        self.coerce_invalid_data = coerce_invalid_data
        self.force_load_invalid_data = force_load_invalid_data
        super().__init__(
            verbose_name=verbose_name,
            name=name,
            **kwargs,
        )

    def deconstruct(self) -> tuple[str, str, Sequence[Any], dict[str, Any]]:
        name, path, args, kwargs = super().deconstruct()
        kwargs["model_cls"] = self.model_cls
        kwargs["coerce_invalid_data"] = self.coerce_invalid_data
        kwargs["force_load_invalid_data"] = self.force_load_invalid_data
        return name, path, args, kwargs

    def from_db_value(
        self,
        value: str | None,
        expression: Expression,
        connection: BaseDatabaseWrapper,
    ) -> T | None:
        """
        Convert DB value -> Python value
        """
        if value is None:
            return value
        # Some backends (SQLite at least) extract non-string values in their
        # SQL datatypes.
        # if isinstance(expression, KeyTransform) and not isinstance(value, str):
        #     return value

        # First thing to try: validate the data exactly as it came out of the
        # database. If that works, great! Return the resulting object.
        result = _validate(self.model_cls, value)
        if result.is_ok:
            return result.ok_value

        # If the data failed validation, second thing to try it to call the
        # `coerce_invalid_data` function (if one was provided), and allow it to
        # massage the data in some way. We then take the return value of that
        # and try running the validation code again. The expected use case of
        # this is allowing schema migrations of the Pydantic model, without
        # having to rewrite the whole table all at once. Instead, pass in a
        # "migrate" function and let it migrate rows on demand.
        try:
            parsed_value = json.loads(value, cls=self.decoder)
        except json.JSONDecodeError:
            raise ValidationError(
                _("Could not decode value as JSON"),
                code="invalid",
                params={"value": value},
            )

        if self.coerce_invalid_data is not None:
            coerced = self.coerce_invalid_data(parsed_value)
            result = _validate(self.model_cls, coerced)
            if result.is_ok:
                return result.ok_value

        # Last chance: if we're told to, use `model_construct` to bypass
        # validation and force the invalid data to load. This isn't recommended
        if self.force_load_invalid_data:
            forced = self.model_cls.model_construct(**parsed_value)
            return forced

        # All else has failed, so now we throw a ValidationError
        raise _pyd_validation_error_to_django(result.err_value)

    def get_db_prep_value(
        self,
        value: Any,
        connection: BaseDatabaseWrapper,
        prepared: bool = False,
    ) -> Any:
        """
        Convert Python value -> DB value
        """
        if not prepared:
            value = self.get_prep_value(value)
        if isinstance(value, expressions.Value) and isinstance(
            value.output_field, JSONField
        ):
            value = value.value
        elif isinstance(value, pydantic.BaseModel):
            value = value.model_dump(mode="json")
        elif hasattr(value, "as_sql"):
            return value

        return connection.ops.adapt_json_value(value, self.encoder)

    def validate(self, value: Any, model_instance: Model | None) -> None:
        # Dump the model data and then re-validate it. This catches if the
        # value was created by model_construct with invalid data
        if not isinstance(value, self.model_cls):
            raise ValidationError(
                _("Given value is type[%s], expected type[%s]")
                % (
                    type(value),
                    self.model_cls,
                )
            )
        dumped_val = value.model_dump(mode="json")
        result = _validate(self.model_cls, dumped_val)
        if result.is_err:
            raise _pyd_validation_error_to_django(result.err_value)
        # Use the dumped value to do all the upstream validation.
        super().validate(dumped_val, model_instance)


__all__ = [
    "PydanticField",
]
