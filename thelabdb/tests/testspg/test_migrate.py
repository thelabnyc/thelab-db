from __future__ import annotations

from contextlib import closing

from django.db import connection, migrations, models
from django.db.migrations import Migration
from django.db.migrations.operations.base import Operation
from django.test import SimpleTestCase, TestCase

from thelabdb.pgviews.apps import ViewConfig
from thelabdb.pgviews.migrate import (
    MigrationName,
    TableName,
    _collect_affected_tables,
    drop_affected_views,
    get_affected_tables,
    get_view_classes,
    get_view_dependency_tables,
)


def _make_migration(
    name: str,
    app_label: str,
    operations: list[Operation],
) -> Migration:
    """Create a Migration instance with the given operations.

    Using object.__setattr__ to bypass mypy's class-variable assignment check,
    since Django's Migration.operations is typed as a ClassVar but is routinely
    overridden per-instance.
    """
    m = Migration(name, app_label)
    object.__setattr__(m, "operations", operations)
    return m


# ---------------------------------------------------------------------------
# Unit tests (SimpleTestCase — no DB needed)
# ---------------------------------------------------------------------------


class GetAffectedTablesTest(SimpleTestCase):
    """Test get_affected_tables() extracts table names from migration operations."""

    def test_add_field(self) -> None:
        op = migrations.AddField(
            model_name="product",
            name="title",
            field=models.CharField(max_length=100),
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)

    def test_remove_field(self) -> None:
        op = migrations.RemoveField(
            model_name="product",
            name="title",
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)

    def test_alter_field(self) -> None:
        op = migrations.AlterField(
            model_name="product",
            name="title",
            field=models.CharField(max_length=200),
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)

    def test_rename_field(self) -> None:
        op = migrations.RenameField(
            model_name="product",
            old_name="title",
            new_name="name",
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)

    def test_create_model(self) -> None:
        op = migrations.CreateModel(
            name="product",
            fields=[("id", models.AutoField(primary_key=True))],
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)

    def test_create_model_with_custom_db_table(self) -> None:
        op = migrations.CreateModel(
            name="product",
            fields=[("id", models.AutoField(primary_key=True))],
            options={"db_table": "my_custom_table"},
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("my_custom_table"), result)
        self.assertIn(TableName("catalogue_product"), result)

    def test_delete_model(self) -> None:
        op = migrations.DeleteModel(name="product")
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)

    def test_rename_model(self) -> None:
        op = migrations.RenameModel(old_name="product", new_name="item")
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)
        self.assertIn(TableName("catalogue_item"), result)

    def test_alter_model_table(self) -> None:
        op = migrations.AlterModelTable(name="product", table="new_table")
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)
        self.assertIn(TableName("new_table"), result)

    def test_run_sql_returns_none(self) -> None:
        op = migrations.RunSQL(sql="ALTER TABLE foo ADD COLUMN bar int;")
        result = get_affected_tables("catalogue", [op])
        self.assertIsNone(result)

    def test_run_python_returns_none(self) -> None:
        op = migrations.RunPython(code=lambda apps, schema: None)
        result = get_affected_tables("catalogue", [op])
        self.assertIsNone(result)

    def test_separate_database_and_state_with_run_sql(self) -> None:
        inner_op = migrations.RunSQL(sql="ALTER TABLE foo ADD COLUMN bar int;")
        op = migrations.SeparateDatabaseAndState(
            database_operations=[inner_op],
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNone(result)

    def test_separate_database_and_state_with_field_op(self) -> None:
        inner_op = migrations.AddField(
            model_name="product",
            name="title",
            field=models.CharField(max_length=100),
        )
        op = migrations.SeparateDatabaseAndState(
            database_operations=[inner_op],
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)

    def test_separate_database_and_state_ignores_state_operations(self) -> None:
        """RunPython in state_operations should NOT trigger conservative mode."""
        op = migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AddField(
                    model_name="product",
                    name="title",
                    field=models.CharField(max_length=100),
                ),
            ],
            state_operations=[
                migrations.RunPython(code=lambda apps, schema: None),
            ],
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)

    def test_resolves_db_table_from_registry(self) -> None:
        """Models in the app registry should use their actual db_table."""
        op = migrations.AddField(
            model_name="user",
            name="nickname",
            field=models.CharField(max_length=50),
        )
        result = get_affected_tables("auth", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("auth_user"), result)

    def test_falls_back_to_convention_for_unknown_model(self) -> None:
        """Models not in the registry should use the default naming convention."""
        op = migrations.AddField(
            model_name="product",
            name="title",
            field=models.CharField(max_length=100),
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)

    def test_alter_model_options_returns_empty(self) -> None:
        op = migrations.AlterModelOptions(
            name="product",
            options={"verbose_name": "Product"},
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result), 0)

    def test_alter_model_managers_returns_empty(self) -> None:
        op = migrations.AlterModelManagers(
            name="product",
            managers=[],
        )
        result = get_affected_tables("catalogue", [op])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result), 0)

    def test_multiple_operations_combined(self) -> None:
        ops: list[migrations.operations.base.Operation] = [
            migrations.AddField(
                model_name="product",
                name="title",
                field=models.CharField(max_length=100),
            ),
            migrations.RemoveField(
                model_name="category",
                name="slug",
            ),
        ]
        result = get_affected_tables("catalogue", ops)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)
        self.assertIn(TableName("catalogue_category"), result)

    def test_multiple_operations_with_run_sql_returns_none(self) -> None:
        ops: list[migrations.operations.base.Operation] = [
            migrations.AddField(
                model_name="product",
                name="title",
                field=models.CharField(max_length=100),
            ),
            migrations.RunSQL(sql="SELECT 1;"),
        ]
        result = get_affected_tables("catalogue", ops)
        self.assertIsNone(result)


class GetViewDependencyTablesTest(SimpleTestCase):
    """Test get_view_dependency_tables() extracts table names from SQL."""

    def test_simple_from(self) -> None:
        sql = "SELECT * FROM catalogue_product"
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("catalogue_product"), result)

    def test_from_with_schema(self) -> None:
        sql = "SELECT * FROM public.catalogue_product"
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("catalogue_product"), result)

    def test_join(self) -> None:
        sql = """
        SELECT p.id, c.name
        FROM catalogue_product p
        JOIN catalogue_category c ON p.category_id = c.id
        """
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("catalogue_product"), result)
        self.assertIn(TableName("catalogue_category"), result)

    def test_left_join(self) -> None:
        sql = """
        SELECT p.id, s.price
        FROM catalogue_product p
        LEFT JOIN stockrecord s ON p.id = s.product_id
        """
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("catalogue_product"), result)
        self.assertIn(TableName("stockrecord"), result)

    def test_multiple_joins(self) -> None:
        sql = """
        SELECT p.id
        FROM catalogue_product p
        INNER JOIN catalogue_category c ON p.category_id = c.id
        LEFT OUTER JOIN partner_stockrecord s ON p.id = s.product_id
        """
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("catalogue_product"), result)
        self.assertIn(TableName("catalogue_category"), result)
        self.assertIn(TableName("partner_stockrecord"), result)

    def test_subquery(self) -> None:
        sql = """
        SELECT * FROM catalogue_product
        WHERE id IN (SELECT product_id FROM offer_rangeproductset)
        """
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("catalogue_product"), result)
        self.assertIn(TableName("offer_rangeproductset"), result)

    def test_case_insensitive(self) -> None:
        sql = "select * from Catalogue_Product"
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("Catalogue_Product"), result)

    def test_non_public_schema(self) -> None:
        sql = "SELECT * FROM myschema.catalogue_product"
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("catalogue_product"), result)

    def test_quoted_identifier(self) -> None:
        sql = 'SELECT * FROM "MyTable"'
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("MyTable"), result)

    def test_quoted_schema_and_table(self) -> None:
        sql = 'SELECT * FROM "myschema"."MyTable"'
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("MyTable"), result)

    def test_unquoted_schema_quoted_table(self) -> None:
        sql = 'SELECT * FROM myschema."MyTable"'
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("MyTable"), result)

    def test_filters_sql_keywords(self) -> None:
        """SQL keywords like LATERAL should not appear as table names."""
        sql = """
        SELECT * FROM catalogue_product,
        LATERAL ts_stat('SELECT to_tsvector(name)')
        """
        result = get_view_dependency_tables(sql)
        self.assertIn(TableName("catalogue_product"), result)
        self.assertNotIn("lateral", result)
        self.assertNotIn("ts_stat", result)


class CollectAffectedTablesTest(SimpleTestCase):
    """Test _collect_affected_tables() aggregates across a full migration plan."""

    def test_single_migration(self) -> None:
        migration = _make_migration(
            "0001_test",
            "catalogue",
            [
                migrations.AddField(
                    model_name="product",
                    name="title",
                    field=models.CharField(max_length=100),
                ),
            ],
        )
        plan: list[tuple[Migration, bool]] = [(migration, False)]
        result = _collect_affected_tables(plan)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)
        self.assertEqual(
            result[TableName("catalogue_product")],
            {MigrationName("catalogue.0001_test")},
        )

    def test_multiple_migrations(self) -> None:
        m1 = _make_migration(
            "0001_test",
            "catalogue",
            [
                migrations.AddField(
                    model_name="product",
                    name="title",
                    field=models.CharField(max_length=100),
                ),
            ],
        )
        m2 = _make_migration(
            "0002_test",
            "orders",
            [
                migrations.RemoveField(
                    model_name="order",
                    name="notes",
                ),
            ],
        )
        plan: list[tuple[Migration, bool]] = [
            (m1, False),
            (m2, False),
        ]
        result = _collect_affected_tables(plan)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(TableName("catalogue_product"), result)
        self.assertEqual(
            result[TableName("catalogue_product")],
            {MigrationName("catalogue.0001_test")},
        )
        self.assertIn(TableName("orders_order"), result)
        self.assertEqual(
            result[TableName("orders_order")],
            {MigrationName("orders.0002_test")},
        )

    def test_run_sql_returns_none(self) -> None:
        migration = _make_migration(
            "0001_test",
            "myapp",
            [
                migrations.RunSQL(sql="SELECT 1;"),
            ],
        )
        plan: list[tuple[Migration, bool]] = [(migration, False)]
        result = _collect_affected_tables(plan)
        self.assertIsNone(result)

    def test_empty_plan(self) -> None:
        plan: list[tuple[Migration, bool]] = []
        result = _collect_affected_tables(plan)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result), 0)


# ---------------------------------------------------------------------------
# Registry tests (TestCase — needs app registry)
# ---------------------------------------------------------------------------


class GetViewClassesTest(TestCase):
    """Test get_view_classes() returns real View subclasses from the registry."""

    def test_returns_registered_views(self) -> None:
        view_classes = get_view_classes()
        view_names = {cls.__name__ for cls in view_classes}
        self.assertIn("MaterializedRelatedView", view_names)
        self.assertIn("RelatedView", view_names)
        self.assertIn("Superusers", view_names)

    def test_materialized_views_flagged_correctly(self) -> None:
        from thelabdb.pgviews.view import MaterializedView

        view_classes = get_view_classes()
        for cls in view_classes:
            if cls.__name__ == "MaterializedRelatedView":
                self.assertTrue(issubclass(cls, MaterializedView))
            elif cls.__name__ == "RelatedView":
                self.assertFalse(issubclass(cls, MaterializedView))


# ---------------------------------------------------------------------------
# Integration tests (TestCase — requires PG)
# ---------------------------------------------------------------------------


def _sync_views() -> None:
    """Re-create all views via ViewSyncer."""
    from thelabdb.pgviews.models import ViewSyncer

    vs = ViewSyncer()
    vs.run(force=True, update=True)


def _count_testspg_matviews() -> int:
    with closing(connection.cursor()) as cur:
        cur.execute(
            "SELECT COUNT(*) FROM pg_matviews WHERE matviewname LIKE 'testspg_%'"
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def _count_testspg_views() -> int:
    with closing(connection.cursor()) as cur:
        cur.execute("SELECT COUNT(*) FROM pg_views WHERE viewname LIKE 'testspg_%'")
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def _view_exists(view_name: str, materialized: bool = False) -> bool:
    catalog = "pg_matviews" if materialized else "pg_views"
    col = "matviewname" if materialized else "viewname"
    with closing(connection.cursor()) as cur:
        cur.execute(f"SELECT {col} FROM {catalog} WHERE {col} = %s", [view_name])
        return cur.fetchone() is not None


class DropAffectedViewsEmptyPlanTest(TestCase):
    """Empty plan → no views dropped."""

    def setUp(self) -> None:
        _sync_views()

    def test_empty_plan_drops_nothing(self) -> None:
        count_before = _count_testspg_matviews()
        self.assertGreater(count_before, 0)

        plan: list[tuple[Migration, bool]] = []
        drop_affected_views(connection, plan)

        count_after = _count_testspg_matviews()
        self.assertEqual(count_before, count_after)


class DropAffectedViewsUnrelatedTest(TestCase):
    """Plan with unrelated tables → no views dropped."""

    def setUp(self) -> None:
        _sync_views()

    def test_unrelated_plan_drops_nothing(self) -> None:
        count_before = _count_testspg_matviews()

        migration = _make_migration(
            "0001_test",
            "some_unrelated_app",
            [
                migrations.AddField(
                    model_name="widgetmodel",
                    name="nickname",
                    field=models.CharField(max_length=50),
                ),
            ],
        )
        plan: list[tuple[Migration, bool]] = [(migration, False)]
        drop_affected_views(connection, plan)

        count_after = _count_testspg_matviews()
        self.assertEqual(count_before, count_after)


class DropAffectedViewsTargetedTest(TestCase):
    """Plan targeting testspg_testmodel → only related views dropped."""

    def setUp(self) -> None:
        _sync_views()

    def test_targeted_drop(self) -> None:
        migration = _make_migration(
            "0001_test",
            "testspg",
            [
                migrations.AddField(
                    model_name="testmodel",
                    name="description",
                    field=models.TextField(default=""),
                ),
            ],
        )
        plan: list[tuple[Migration, bool]] = [(migration, False)]
        drop_affected_views(connection, plan)

        # MaterializedRelatedView depends on testspg_testmodel — should be dropped
        self.assertFalse(
            _view_exists("testspg_materializedrelatedview", materialized=True),
            "MV should have been dropped",
        )

        # RelatedView depends on testspg_testmodel — should be dropped
        self.assertFalse(
            _view_exists("testspg_relatedview", materialized=False),
            "Related regular view should have been dropped",
        )

        # Superusers depends on auth_user, NOT testspg_testmodel — should remain
        self.assertTrue(
            _view_exists("testspg_superusers", materialized=False),
            "Unrelated view should still exist",
        )


class DropAffectedViewsConservativeTest(TestCase):
    """RunSQL/RunPython/SeparateDatabaseAndState+RunSQL → all views dropped."""

    def setUp(self) -> None:
        _sync_views()

    def test_run_sql_drops_all(self) -> None:
        migration = _make_migration(
            "0001_test",
            "myapp",
            [
                migrations.RunSQL(sql="ALTER TABLE foo ADD COLUMN bar int;"),
            ],
        )
        plan: list[tuple[Migration, bool]] = [(migration, False)]
        drop_affected_views(connection, plan)

        self.assertEqual(
            _count_testspg_matviews(), 0, "All materialized views should be dropped"
        )
        self.assertEqual(
            _count_testspg_views(), 0, "All regular views should be dropped"
        )

    def test_run_python_drops_all(self) -> None:
        migration = _make_migration(
            "0001_test",
            "myapp",
            [
                migrations.RunPython(code=lambda apps, schema: None),
            ],
        )
        plan: list[tuple[Migration, bool]] = [(migration, False)]
        drop_affected_views(connection, plan)

        self.assertEqual(
            _count_testspg_matviews(), 0, "All materialized views should be dropped"
        )
        self.assertEqual(
            _count_testspg_views(), 0, "All regular views should be dropped"
        )

    def test_separate_database_and_state_with_run_sql_drops_all(self) -> None:
        migration = _make_migration(
            "0001_test",
            "myapp",
            [
                migrations.SeparateDatabaseAndState(
                    database_operations=[
                        migrations.RunSQL(sql="SELECT 1;"),
                    ],
                ),
            ],
        )
        plan: list[tuple[Migration, bool]] = [(migration, False)]
        drop_affected_views(connection, plan)

        self.assertEqual(
            _count_testspg_matviews(), 0, "All materialized views should be dropped"
        )
        self.assertEqual(
            _count_testspg_views(), 0, "All regular views should be dropped"
        )


# ---------------------------------------------------------------------------
# Signal handler tests (TestCase — requires PG)
# ---------------------------------------------------------------------------


class HandlePreMigrateTest(TestCase):
    """Tests for the handle_pre_migrate signal handler on ViewConfig."""

    def setUp(self) -> None:
        _sync_views()

    def _get_view_config(self) -> ViewConfig:
        from django.apps import apps as django_apps

        config = django_apps.get_app_config("pgviews")
        assert isinstance(config, ViewConfig)
        return config

    def test_handler_runs_once(self) -> None:
        """First call drops views; second call is a no-op."""
        config = self._get_view_config()
        # Reset the flag so our first call actually runs
        config._pre_migrate_run.clear()

        migration = _make_migration(
            "0001_test",
            "testspg",
            [
                migrations.AddField(
                    model_name="testmodel",
                    name="description",
                    field=models.TextField(default=""),
                ),
            ],
        )
        plan: list[tuple[Migration, bool]] = [(migration, False)]

        # First call — should drop affected views
        config.handle_pre_migrate(
            sender=config,
            app_config=config,
            using="default",
            plan=plan,
        )
        self.assertFalse(
            _view_exists("testspg_materializedrelatedview", materialized=True),
            "MV should have been dropped on first call",
        )

        # Recreate views and call again — should be no-op
        _sync_views()
        config.handle_pre_migrate(
            sender=config,
            app_config=config,
            using="default",
            plan=plan,
        )
        self.assertTrue(
            _view_exists("testspg_materializedrelatedview", materialized=True),
            "MV should still exist on second call (no-op)",
        )

    def test_handler_skips_empty_plan(self) -> None:
        config = self._get_view_config()
        config._pre_migrate_run.clear()

        count_before = _count_testspg_matviews()
        self.assertGreater(count_before, 0)

        config.handle_pre_migrate(
            sender=config,
            app_config=config,
            using="default",
            plan=[],
        )

        count_after = _count_testspg_matviews()
        self.assertEqual(count_before, count_after)

    def test_handler_skips_none_plan(self) -> None:
        config = self._get_view_config()
        config._pre_migrate_run.clear()

        count_before = _count_testspg_matviews()
        self.assertGreater(count_before, 0)

        config.handle_pre_migrate(
            sender=config,
            app_config=config,
            using="default",
            plan=None,
        )

        count_after = _count_testspg_matviews()
        self.assertEqual(count_before, count_after)

    def test_handler_respects_setting_disabled(self) -> None:
        """PGVIEWS_DROP_BEFORE_MIGRATE=False disables automatic dropping."""
        config = self._get_view_config()
        config._pre_migrate_run.clear()

        migration = _make_migration(
            "0001_test",
            "myapp",
            [
                migrations.RunSQL(sql="SELECT 1;"),
            ],
        )
        plan: list[tuple[Migration, bool]] = [(migration, False)]

        count_before = _count_testspg_matviews()
        self.assertGreater(count_before, 0)

        with self.settings(PGVIEWS_DROP_BEFORE_MIGRATE=False):
            config.handle_pre_migrate(
                sender=config,
                app_config=config,
                using="default",
                plan=plan,
            )

        count_after = _count_testspg_matviews()
        self.assertEqual(count_before, count_after)
