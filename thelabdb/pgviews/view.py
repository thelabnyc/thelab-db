"""Helpers to access Postgres views from the Django ORM."""

from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from typing import Any, Literal, Self, TypeVar, cast
import copy
import re

from django.apps import apps
from django.core import exceptions
from django.db import connection, models, transaction
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.models.query import QuerySet

from .db import get_fields_by_name

try:
    try:
        from psycopg import ProgrammingError
    except ImportError:
        from psycopg2 import ProgrammingError  # type:ignore[assignment]
except ImportError:
    raise exceptions.ImproperlyConfigured("Error loading psycopg2 or psycopg module")

FIELD_SPEC_REGEX = (
    r"^([A-Za-z_][A-Za-z0-9_]*)\."
    r"([A-Za-z_][A-Za-z0-9_]*)\."
    r"(\*|(?:[A-Za-z_][A-Za-z0-9_]*))$"
)
FIELD_SPEC_RE = re.compile(FIELD_SPEC_REGEX)

T = TypeVar("T", bound=models.Model)

ViewOpResult = Literal[
    "UPDATED", "CREATED", "FORCED", "FORCE_REQUIRED", "EXISTS", "DROPPED"
]


def hasfield(model_cls: type[models.Model], field_name: str) -> bool:
    """Like `hasattr()`, but for model fields.

    >>> from django.contrib.auth.models import User
    >>> hasfield(User, 'password')
    True
    >>> hasfield(User, 'foobarbaz')
    False
    """
    try:
        model_cls._meta.get_field(field_name)
        return True
    except exceptions.FieldDoesNotExist:
        return False


AppLabelModelName = tuple[str, str]

# Projections of models fields onto views which have been deferred due to
# model import and loading dependencies.
# Format: (app_label, model_name): {view_cls: [field_name, ...]}
DeferredProjections = defaultdict[
    AppLabelModelName,
    defaultdict[
        type[models.Model],
        list[str],
    ],
]
_DEFERRED_PROJECTIONS: DeferredProjections = defaultdict(lambda: defaultdict(list))


def realize_deferred_projections(
    sender: type[models.Model],
    *args: Any,
    **kwargs: Any,
) -> None:
    """Project any fields which were deferred pending model preparation."""
    app_label = sender._meta.app_label
    model_name = sender.__name__.lower()
    pending: dict[type[models.Model], list[str]] = _DEFERRED_PROJECTIONS.pop(
        (app_label, model_name),
        {},
    )
    for view_cls, field_names in pending.items():
        field_instances = get_fields_by_name(sender, *field_names)
        for name, field in field_instances.items():
            # Only assign the field if the view does not already have an
            # attribute or explicitly-defined field with that name.
            if hasattr(view_cls, name) or hasfield(view_cls, name):
                continue
            copy.copy(field).contribute_to_class(view_cls, name)


models.signals.class_prepared.connect(realize_deferred_projections)


@transaction.atomic()
def create_view(
    connection: BaseDatabaseWrapper,
    view_name: str,
    view_query: str,
    update: bool = True,
    force: bool = False,
    materialized: bool = False,
    index: str | None = None,
) -> ViewOpResult:
    """
    Create a named view on a connection.

    Returns True if a new view was created (or an existing one updated), or
    False if nothing was done.

    If ``update`` is True (default), attempt to update an existing view. If the
    existing view's schema is incompatible with the new definition, ``force``
    (default: False) controls whether or not to drop the old view and create
    the new one.
    """

    if "." in view_name:
        vschema, vname = view_name.split(".", 1)
    else:
        vschema, vname = "public", view_name

    cursor_wrapper = connection.cursor()
    cursor = cursor_wrapper.cursor
    try:
        force_required = False
        # Determine if view already exists.
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.views WHERE table_schema = %s and table_name = %s;",
            [vschema, vname],
        )
        view_exists = cursor.fetchone()[0] > 0
        if view_exists and not update:
            return "EXISTS"
        elif view_exists:
            # Detect schema conflict by copying the original view, attempting to
            # update this copy, and detecting errors.
            cursor.execute(
                "CREATE TEMPORARY VIEW check_conflict AS SELECT * FROM {};".format(
                    view_name
                )
            )
            try:
                with transaction.atomic():
                    cursor.execute(
                        "CREATE OR REPLACE TEMPORARY VIEW check_conflict AS {};".format(
                            view_query
                        )
                    )
            except ProgrammingError:
                force_required = True
            finally:
                cursor.execute("DROP VIEW IF EXISTS check_conflict;")

        ret: ViewOpResult
        if materialized:
            cursor.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view_name} CASCADE;")
            cursor.execute(f"CREATE MATERIALIZED VIEW {view_name} AS {view_query};")
            if index is not None:
                index_sub_name = "_".join([s.strip() for s in index.split(",")])
                cursor.execute(
                    "CREATE UNIQUE INDEX {0}_{1}_index ON {0} ({2})".format(
                        view_name, index_sub_name, index
                    )
                )
            ret = view_exists and "UPDATED" or "CREATED"
        elif not force_required:
            cursor.execute(f"CREATE OR REPLACE VIEW {view_name} AS {view_query};")
            ret = view_exists and "UPDATED" or "CREATED"
        elif force:
            cursor.execute(f"DROP VIEW IF EXISTS {view_name} CASCADE;")
            cursor.execute(f"CREATE VIEW {view_name} AS {view_query};")
            ret = "FORCED"
        else:
            ret = "FORCE_REQUIRED"

        return ret
    finally:
        cursor_wrapper.close()


def clear_view(
    connection: BaseDatabaseWrapper,
    view_name: str,
    materialized: bool = False,
) -> ViewOpResult:
    """
    Remove a named view on connection.
    """
    cursor_wrapper = connection.cursor()
    cursor = cursor_wrapper.cursor
    try:
        if materialized:
            cursor.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view_name} CASCADE")
        else:
            cursor.execute(f"DROP VIEW IF EXISTS {view_name} CASCADE")
    finally:
        cursor_wrapper.close()
    return "DROPPED"


class ViewMeta(models.base.ModelBase):
    def __new__(
        metacls,
        name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
    ) -> type[models.Model]:
        """Deal with all of the meta attributes, removing any Django does not want"""
        # Get attributes before Django
        dependencies: list[str] = attrs.pop("dependencies", [])
        projection: list[str] = attrs.pop("projection", [])
        concurrent_index: str | None = attrs.pop("concurrent_index", None)

        # Get projection
        deferred_projections = []
        for field_name in projection:
            if isinstance(field_name, models.Field):
                attrs[field_name.name] = copy.copy(field_name)
            elif isinstance(field_name, str):
                match = FIELD_SPEC_RE.match(field_name)
                if not match:
                    raise TypeError("Unrecognized field specifier: %r" % field_name)
                deferred_projections.append(match.groups())
            else:
                raise TypeError("Unrecognized field specifier: %r" % field_name)

        view_cls = cast(
            type[models.Model],
            models.base.ModelBase.__new__(metacls, name, bases, attrs),
        )

        # Get dependencies
        setattr(view_cls, "_dependencies", dependencies)
        # Materialized views can have an index allowing concurrent refresh
        setattr(view_cls, "_concurrent_index", concurrent_index)
        for app_label, model_name, field_name in deferred_projections:
            model_spec = (app_label, model_name.lower())

            _DEFERRED_PROJECTIONS[model_spec][view_cls].append(field_name)
            _realise_projections(app_label, model_name)

        return view_cls

    def add_to_class(self, name: str, value: Any) -> None:
        if name == "_base_manager":
            return
        super().add_to_class(name, value)  # type:ignore[misc]


class BaseManagerMeta:
    base_manager_name = "objects"


class View(models.Model, metaclass=ViewMeta):
    """Helper for exposing Postgres views as Django models."""

    _dependencies: list[str]
    _concurrent_index: str
    _deferred: bool = False
    sql: str

    class Meta:
        abstract = True
        managed = False


def _realise_projections(app_label: str, model_name: str) -> None:
    """Checks whether the model has been loaded and runs
    realise_deferred_projections() if it has.
    """
    try:
        model_cls = apps.get_model(app_label, model_name)
    except exceptions.AppRegistryNotReady:
        return
    if model_cls is not None and issubclass(model_cls, View):
        realize_deferred_projections(model_cls)


class ReadOnlyViewQuerySet(QuerySet[T]):
    def _raw_delete(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def delete(self) -> tuple[int, dict[str, int]]:
        raise NotImplementedError("Not allowed")

    def update(self, **kwargs: Any) -> int:
        raise NotImplementedError("Not allowed")

    def _update(self, **kwargs: Any) -> int:
        raise NotImplementedError("Not allowed")

    def create(self, **kwargs: Any) -> T:
        raise NotImplementedError("Not allowed")

    def update_or_create(
        self,
        defaults: Mapping[str, Any] | None = None,
        create_defaults: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[T, bool]:
        raise NotImplementedError("Not allowed")

    def bulk_create(
        self,
        objs: Iterable[T],
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Collection[str] | None = None,
        unique_fields: Collection[str] | None = None,
    ) -> list[T]:
        raise NotImplementedError("Not allowed")


class ReadOnlyViewManager(models.Manager[T]):
    def get_queryset(self) -> ReadOnlyViewQuerySet[T]:
        return ReadOnlyViewQuerySet(self.model, using=self._db)


class ReadOnlyView(View):
    """View which cannot be altered"""

    _base_manager: ReadOnlyViewManager[Self] = ReadOnlyViewManager()
    objects: ReadOnlyViewManager[Self] = ReadOnlyViewManager()

    class Meta(BaseManagerMeta):
        abstract = True
        managed = False


class MaterializedView(View):
    """A materialized view.
    More information:
    http://www.postgresql.org/docs/current/static/sql-creatematerializedview.html
    """

    @classmethod
    def refresh(self, concurrently: bool = False) -> None:
        cursor_wrapper = connection.cursor()
        cursor = cursor_wrapper.cursor
        try:
            if self._concurrent_index is not None and concurrently:
                cursor.execute(
                    "REFRESH MATERIALIZED VIEW CONCURRENTLY {}".format(
                        self._meta.db_table
                    )
                )
            else:
                cursor.execute(f"REFRESH MATERIALIZED VIEW {self._meta.db_table}")
        finally:
            cursor_wrapper.close()

    class Meta:
        abstract = True
        managed = False


class ReadOnlyMaterializedView(MaterializedView):
    """Read-only version of the materialized view"""

    _base_manager: ReadOnlyViewManager[Self] = ReadOnlyViewManager()
    objects: ReadOnlyViewManager[Self] = ReadOnlyViewManager()

    class Meta(BaseManagerMeta):
        abstract = True
        managed = False
