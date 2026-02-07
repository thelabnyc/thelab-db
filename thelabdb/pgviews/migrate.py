"""Pre-migrate logic for intelligently dropping affected PostgreSQL views.

This module provides functions that analyze a Django migration plan to determine
which views need to be dropped before migrations run. Views are then recreated
by the post_migrate signal handler in apps.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NewType
import logging
import re

from django.apps import apps
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.migrations import Migration
from django.db.migrations.operations.base import Operation
from django.db.migrations.operations.fields import FieldOperation
from django.db.migrations.operations.models import (
    AlterModelTable,
    CreateModel,
    ModelOperation,
    ModelOptionOperation,
    RenameModel,
)
from django.db.migrations.operations.special import (
    RunPython,
    RunSQL,
    SeparateDatabaseAndState,
)

from .view import MaterializedView, View, clear_view

logger = logging.getLogger(__name__)

TableName = NewType("TableName", str)
MigrationName = NewType("MigrationName", str)

# Regex to extract table names from FROM/JOIN clauses in SQL.
# Handles optional schema prefixes (quoted or unquoted) and quoted identifiers.
_TABLE_REF_RE = re.compile(
    r"""(?:FROM|JOIN)\s+            # FROM or JOIN keyword
    (?:(?:"\w+"|\w+)\.)?            # optional schema prefix (quoted or unquoted)
    (?:"([^"]+)"|([A-Za-z_]\w+))   # table name: quoted identifier OR unquoted
    """,
    re.IGNORECASE | re.VERBOSE,
)

# SQL keywords and function names that might be false-positive table matches
_SQL_FALSE_POSITIVES = frozenset(
    {
        "lateral",
        "ts_stat",
        "generate_series",
        "unnest",
        "json_each",
        "jsonb_each",
        "json_array_elements",
        "jsonb_array_elements",
        "information_schema",
        "pg_catalog",
        "select",
        "where",
        "group",
        "order",
        "having",
        "limit",
        "offset",
        "union",
        "intersect",
        "except",
        "values",
        "dual",
    }
)


def get_view_dependency_tables(sql: str) -> set[TableName]:
    """Extract dependency table names from a view's SQL definition.

    Uses regex to find table references in FROM and JOIN clauses. This is
    best-effort and may not handle CTEs, complex subqueries, or other advanced
    SQL patterns. Conservative mode (triggered by RunSQL/RunPython) provides a
    safety net by dropping all views when the plan cannot be fully analyzed.
    """
    matches = _TABLE_REF_RE.findall(sql)
    # Each match is (quoted_name, unquoted_name) — exactly one is non-empty
    return {
        TableName(quoted or unquoted)
        for quoted, unquoted in matches
        if (quoted or unquoted).lower() not in _SQL_FALSE_POSITIVES
    }


def get_view_classes() -> list[type[View]]:
    """Get all View subclasses that have a sql attribute."""
    result: list[type[View]] = []
    for model_cls in apps.get_models():
        if (
            isinstance(model_cls, type)
            and issubclass(model_cls, View)
            and hasattr(model_cls, "sql")
        ):
            result.append(model_cls)
    return result


def _resolve_db_table(app_label: str, model_name_lower: str) -> TableName:
    """Resolve a model reference to its actual db_table name.

    Uses the provided app registry to find the model's configured db_table.
    Falls back to Django's default naming convention if the model isn't
    registered (e.g., it has been removed from code but the migration remains).
    """
    try:
        model = apps.get_model(app_label, model_name_lower)
        return TableName(model._meta.db_table)
    except LookupError:
        return TableName(f"{app_label}_{model_name_lower}")


def get_affected_tables(
    app_label: str,
    operations: Sequence[Operation],
) -> set[TableName] | None:
    """Extract the set of database table names affected by migration operations.

    Returns None if conservative mode is needed (RunSQL/RunPython detected).
    Returns an empty set for operations with no schema impact.
    """
    tables: set[TableName] = set()
    for op in operations:
        result = _get_tables_for_operation(app_label, op)
        if result is None:
            return None
        tables.update(result)
    return tables


def _get_tables_for_operation(
    app_label: str,
    op: Operation,
) -> set[TableName] | None:
    """Get affected tables for a single migration operation.

    Returns None for conservative mode (RunSQL/RunPython).
    """
    if isinstance(op, SeparateDatabaseAndState):
        # Only inspect database_operations — state_operations only affect
        # Django's in-memory state and never touch the actual database.
        return get_affected_tables(app_label, list(op.database_operations))

    if isinstance(op, (RunSQL, RunPython)):
        return None

    if isinstance(op, FieldOperation):
        return {_resolve_db_table(app_label, op.model_name_lower)}

    # AlterModelTable inherits from ModelOptionOperation but DOES affect
    # the schema, so check it before the no-op ModelOptionOperation branch.
    if isinstance(op, AlterModelTable):
        tables: set[TableName] = {_resolve_db_table(app_label, op.name_lower)}
        if op.table:
            tables.add(TableName(op.table))
        return tables

    # ModelOptionOperation (AlterModelOptions, AlterModelManagers) has no
    # schema impact — check before the generic ModelOperation branch.
    if isinstance(op, ModelOptionOperation):
        return set()

    # RenameModel affects both old and new table names — check before
    # the generic ModelOperation branch which only captures the old name.
    if isinstance(op, RenameModel):
        return {
            _resolve_db_table(app_label, op.old_name_lower),
            _resolve_db_table(app_label, op.new_name_lower),
        }

    if isinstance(op, ModelOperation):
        tables = {_resolve_db_table(app_label, op.name_lower)}

        # CreateModel may have a custom db_table in options
        if isinstance(op, CreateModel):
            db_table = op.options.get("db_table")
            if db_table:
                tables.add(TableName(db_table))

        return tables

    # Unknown operations are assumed to have no schema impact
    return set()


def _collect_affected_tables(
    plan: list[tuple[Migration, bool]],
) -> dict[TableName, set[MigrationName]] | None:
    """Aggregate affected tables across all pending migrations.

    Returns a mapping of ``{table_name: {migration_name, ...}}`` so callers
    can explain *why* a table is considered affected.

    Returns None if conservative mode is needed (RunSQL/RunPython detected).
    """
    tables: dict[TableName, set[MigrationName]] = {}
    for migration, _is_backwards in plan:
        app_label = migration.app_label
        migration_name = MigrationName(f"{app_label}.{migration.name}")
        result = get_affected_tables(app_label, migration.operations)
        if result is None:
            return None
        for table in result:
            tables.setdefault(table, set()).add(migration_name)
    return tables


def drop_affected_views(
    connection: BaseDatabaseWrapper,
    plan: list[tuple[Migration, bool]],
) -> None:
    """Analyze a migration plan and drop affected views.

    This is the main orchestrator: it collects affected tables from the plan,
    then drops only the views whose SQL references those tables. If any
    operation triggers conservative mode (RunSQL/RunPython), all views are
    dropped.

    Note: ``clear_view`` uses ``CASCADE``, so transitive view dependencies are
    handled implicitly by PostgreSQL (e.g., if view B depends on view A,
    dropping A cascades to B).
    """
    if not plan:
        return

    affected_tables = _collect_affected_tables(plan)

    if affected_tables is None:
        # Log which migrations triggered conservative mode
        migration_names: str = ", ".join(f"{m.app_label}.{m.name}" for m, _ in plan)
        logger.info(
            "Plan contains RunSQL/RunPython; dropping all views "
            "(conservative mode triggered by: %s)",
            migration_names,
        )

    view_classes = get_view_classes()
    for view_cls in view_classes:
        is_materialized = issubclass(view_cls, MaterializedView)
        python_name = f"{view_cls._meta.app_label}.{view_cls.__name__}"

        if affected_tables is None:
            # Conservative mode: drop all views
            logger.info(
                "Dropping view %s (%s) — conservative mode",
                python_name,
                view_cls._meta.db_table,
            )
        else:
            mv_deps = get_view_dependency_tables(view_cls.sql)
            overlapping: set[TableName] = mv_deps & affected_tables.keys()
            if not overlapping:
                continue
            # Log each migration that affects this view
            triggering: set[MigrationName] = set()
            for table in overlapping:
                triggering.update(affected_tables[table])
            logger.info(
                "Dropping view %s (%s) — depends on tables altered by: %s",
                python_name,
                view_cls._meta.db_table,
                ", ".join(sorted(triggering)),
            )

        clear_view(
            connection,
            view_cls._meta.db_table,
            materialized=is_materialized,
        )
