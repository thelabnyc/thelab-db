from typing import Any, Union

from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.db.models.fields import Field
from django.db.models.fields.reverse_related import ForeignObjectRel


def get_fields_by_name(
    model_cls: type[models.Model],
    *field_names: str,
) -> "dict[str, Union[Field[Any, Any] | GenericForeignKey]]":
    """Return a dict of `models.Field` instances for named fields.

    Supports wildcard fetches using `'*'`.

        >>> get_fields_by_name(User, 'username', 'password')
        {'username': <django.db.models.fields.CharField: username>,
         'password': <django.db.models.fields.CharField: password>}

        >>> get_fields_by_name(User, '*')
        {'username': <django.db.models.fields.CharField: username>,
         ...,
         'date_joined': <django.db.models.fields.DateTimeField: date_joined>}
    """
    fields: "list[tuple[str, Field[Any, Any] | ForeignObjectRel | GenericForeignKey]]"
    if "*" in field_names:
        fields = [(field.name, field) for field in model_cls._meta.fields]
    else:
        fields = [
            (field_name, model_cls._meta.get_field(field_name))
            for field_name in field_names
        ]
    return {
        name: field for name, field in fields if not isinstance(field, ForeignObjectRel)
    }
