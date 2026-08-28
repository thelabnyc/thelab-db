from contextlib import closing
from typing import Any

from django.contrib import auth
from django.core.management import call_command
from django.db import DatabaseError, connection
from django.db.models import signals
from django.dispatch import receiver
from django.test import TestCase

from thelabdb.pgviews import view
from thelabdb.pgviews.signals import all_views_synced, view_synced

from . import models


@receiver(signals.post_migrate)
def create_test_schema(sender: object, app_config: object, **kwargs: object) -> None:
    command = "CREATE SCHEMA IF NOT EXISTS {};".format("test_schema")
    print(f"\n\n{command}\n\n")
    with connection.cursor() as cursor:
        cursor.execute(command)


class ViewTestCase(TestCase):
    """Run the tests to ensure the post_migrate hooks were called."""

    def test_views_have_been_created(self) -> None:
        """Look at the PG View table to ensure views were created."""
        with closing(connection.cursor()) as cur:
            cur.execute(
                """SELECT COUNT(*) FROM pg_views
                        WHERE viewname LIKE 'testspg_%';"""
            )

            (count,) = cur.fetchone()
            self.assertEqual(count, 4)

            cur.execute(
                """SELECT COUNT(*) FROM pg_matviews
                        WHERE matviewname LIKE 'testspg_%';"""
            )

            (count,) = cur.fetchone()
            self.assertEqual(count, 3)

            cur.execute(
                """SELECT COUNT(*) FROM information_schema.views
                        WHERE table_schema = 'test_schema';"""
            )

            (count,) = cur.fetchone()
            self.assertEqual(count, 1)

    def test_clear_views(self) -> None:
        """Check the PG View table to see that the views were removed."""
        call_command("clear_pgviews")
        with closing(connection.cursor()) as cur:
            cur.execute(
                """SELECT COUNT(*) FROM pg_views
                        WHERE viewname LIKE 'testspg_%';"""
            )

            (count,) = cur.fetchone()
            self.assertEqual(count, 0)

            cur.execute(
                """SELECT COUNT(*) FROM information_schema.views
                        WHERE table_schema = 'test_schema';"""
            )

            (count,) = cur.fetchone()
            self.assertEqual(count, 0)

    def test_wildcard_projection(self) -> None:
        """Wildcard projections take all fields from a projected model."""
        foo_user = auth.models.User._default_manager.create(
            username="foo", is_superuser=True
        )
        foo_user.set_password("blah")
        foo_user.save()

        foo_superuser = models.Superusers._default_manager.get(
            username="foo",  # type:ignore[misc]
        )

        # TODO: mypy doesn't pick up projected fields
        self.assertEqual(foo_user.id, foo_superuser.id)
        self.assertEqual(
            foo_user.password,
            foo_superuser.password,  # type:ignore[attr-defined]
        )

    def test_limited_projection(self) -> None:
        """A limited projection only creates the projected fields."""
        foo_user = auth.models.User.objects.create(username="foo", is_superuser=True)
        foo_user.set_password("blah")
        foo_user.save()

        foo_simple = models.SimpleUser._default_manager.get(
            username="foo",  # type:ignore[misc]
        )

        # TODO: mypy doesn't pick up projected fields
        self.assertEqual(
            foo_simple.username,  # type:ignore[attr-defined]
            foo_user.username,
        )
        self.assertEqual(
            foo_simple.password,  # type:ignore[attr-defined]
            foo_user.password,
        )
        self.assertFalse(getattr(foo_simple, "date_joined", False))

    def test_related_delete(self) -> None:
        """Test views do not interfere with deleting the models"""
        test_model = models.TestModel()
        test_model.name = "Bob"
        test_model.save()
        test_model.delete()

    def test_materialized_view(self) -> None:
        """Test a materialized view works correctly"""
        self.assertEqual(
            models.MaterializedRelatedView.objects.count(),  # type:ignore[misc]
            0,
            "Materialized view should not have anything",
        )

        test_model = models.TestModel()
        test_model.name = "Bob"
        test_model.save()

        self.assertEqual(
            models.MaterializedRelatedView.objects.count(),  # type:ignore[misc]
            0,
            "Materialized view should not have anything",
        )

        models.MaterializedRelatedView.refresh()

        self.assertEqual(
            models.MaterializedRelatedView.objects.count(),  # type:ignore[misc]
            1,
            "Materialized view should have updated",
        )

        models.MaterializedRelatedViewWithIndex.refresh(concurrently=True)

        self.assertEqual(
            models.MaterializedRelatedViewWithIndex.objects.count(),  # type:ignore[misc]
            1,
            "Materialized view should have updated concurrently",
        )

    def test_signals(self) -> None:
        expected = {
            # The materialized view was already created by the post_migrate
            # handler, so syncing with update=False must leave it alone rather
            # than dropping and recreating it.
            models.MaterializedRelatedView: {
                "status": "EXISTS",
                "has_changed": False,
            },
            models.Superusers: {
                "status": "EXISTS",
                "has_changed": False,
            },
        }
        synced_views = []
        all_views_were_synced = [False]

        @receiver(view_synced)
        def on_view_synced(sender: type[Any], **kwargs: Any) -> None:
            synced_views.append(sender)
            if sender in expected:
                expected_kwargs = expected.pop(sender)
                self.assertEqual(
                    dict(
                        expected_kwargs, update=False, force=False, signal=view_synced
                    ),
                    kwargs,
                )

        @receiver(all_views_synced)
        def on_all_views_synced(sender: type[Any], **kwargs: Any) -> None:
            all_views_were_synced[0] = True

        call_command("sync_pgviews", update=False)

        # All views went through syncing
        self.assertEqual(len(synced_views), 8)
        self.assertEqual(all_views_were_synced[0], True)
        self.assertFalse(expected)


class CreateMaterializedViewTestCase(TestCase):
    """`create_view()` must detect pre-existing materialized views.

    Materialized views are not part of the SQL standard and therefore do not
    show up in `information_schema.views`. Probing the wrong catalog makes
    every existing materialized view appear to be missing, which causes
    needless drop and recreate cycles. `create_view()` instead resolves the
    name with `to_regclass()` and compares `pg_class.relkind`.
    """

    view_name = models.MaterializedRelatedView._meta.db_table
    view_query = models.MaterializedRelatedView.sql

    def _get_matview_oid(self, view_name: str | None = None) -> int | None:
        with closing(connection.cursor()) as cur:
            cur.execute(
                """SELECT c.oid FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = %s AND c.relkind = 'm' AND n.nspname = %s;""",
                [view_name or self.view_name, "public"],
            )
            row = cur.fetchone()
        return None if row is None else int(row[0])

    def _index_exists(self, index_name: str) -> bool:
        with closing(connection.cursor()) as cur:
            cur.execute(
                """SELECT COUNT(*) FROM pg_indexes
                WHERE schemaname = %s AND indexname = %s;""",
                ["public", index_name],
            )
            (count,) = cur.fetchone()
        return int(count) > 0

    def test_existing_materialized_view_is_detected_without_update(self) -> None:
        """An existing materialized view is left untouched when update=False."""
        models.TestModel._default_manager.create(name="Bob")
        models.MaterializedRelatedView.refresh()
        oid_before = self._get_matview_oid()
        self.assertIsNotNone(oid_before)

        status = view.create_view(
            connection,
            self.view_name,
            self.view_query,
            update=False,
            materialized=True,
        )

        self.assertEqual(status, "EXISTS")
        # The oid comparison is what proves the view was not dropped and
        # recreated; a recreated view would materialize the same rows but
        # under a new pg_class oid.
        self.assertEqual(self._get_matview_oid(), oid_before)
        self.assertEqual(
            models.MaterializedRelatedView.objects.count(),  # type:ignore[misc]
            1,
        )

    def test_existing_materialized_view_reports_updated(self) -> None:
        """An existing materialized view reports UPDATED when update=True."""
        oid_before = self._get_matview_oid()
        self.assertIsNotNone(oid_before)

        status = view.create_view(
            connection,
            self.view_name,
            self.view_query,
            update=True,
            materialized=True,
        )

        self.assertEqual(status, "UPDATED")
        # update=True still drops and recreates the view, so it must exist
        # afterwards under a new oid.
        oid_after = self._get_matview_oid()
        self.assertIsNotNone(oid_after)
        self.assertNotEqual(oid_after, oid_before)

    def test_missing_materialized_view_is_created(self) -> None:
        """A materialized view that does not exist yet is created."""
        with closing(connection.cursor()) as cur:
            cur.execute(f"DROP MATERIALIZED VIEW {self.view_name} CASCADE;")
        self.assertIsNone(self._get_matview_oid())

        status = view.create_view(
            connection,
            self.view_name,
            self.view_query,
            update=False,
            materialized=True,
        )

        self.assertEqual(status, "CREATED")
        self.assertIsNotNone(self._get_matview_oid())

    def test_existing_plain_view_is_still_detected(self) -> None:
        """A pre-existing plain view is still detected as EXISTS."""
        status = view.create_view(
            connection,
            models.RelatedView._meta.db_table,
            models.RelatedView.sql,
            update=False,
            materialized=False,
        )
        self.assertEqual(status, "EXISTS")

    def test_no_update_leaves_a_missing_concurrent_index_uncreated(self) -> None:
        """Pins a known gap: `update=False` does not reconcile the index.

        When `concurrent_index` is declared on a model whose materialized view
        already exists, a `--no-update` sync returns EXISTS without creating
        the unique index, so `refresh(concurrently=True)` stays broken until
        the view is recreated. Emitting the index DDL here would make
        `--no-update` write to the database, so the gap is deliberately left
        for a follow-up and asserted as-is; update this test when it is fixed.
        """
        view_name = models.MaterializedRelatedViewWithIndex._meta.db_table
        index_name = f"{view_name}_id_index"
        with closing(connection.cursor()) as cur:
            cur.execute(f"DROP INDEX {index_name};")
        self.assertFalse(self._index_exists(index_name))
        oid_before = self._get_matview_oid(view_name)
        self.assertIsNotNone(oid_before)

        status = view.create_view(
            connection,
            view_name,
            models.MaterializedRelatedViewWithIndex.sql,
            update=False,
            materialized=True,
            index="id",
        )

        self.assertEqual(status, "EXISTS")
        self.assertEqual(self._get_matview_oid(view_name), oid_before)
        self.assertFalse(self._index_exists(index_name))

    def test_materialized_over_existing_plain_view_raises(self) -> None:
        """Converting a plain view to a materialized one is refused."""
        plain_view_name = models.RelatedView._meta.db_table
        with self.assertRaises(ValueError) as ctx:
            view.create_view(
                connection,
                plain_view_name,
                models.RelatedView.sql,
                update=False,
                materialized=True,
            )
        message = str(ctx.exception)
        self.assertIn(plain_view_name, message)
        self.assertIn("materialized view", message)

    def test_plain_over_existing_materialized_view_raises(self) -> None:
        """Converting a materialized view to a plain one is refused."""
        with self.assertRaises(ValueError) as ctx:
            view.create_view(
                connection,
                self.view_name,
                self.view_query,
                update=False,
                materialized=False,
            )
        message = str(ctx.exception)
        self.assertIn(self.view_name, message)
        self.assertIn("materialized view", message)


class DependantViewTestCase(TestCase):
    def test_sync_depending_views(self) -> None:
        """Test the sync_pgviews command for views that depend on other views.

        This test drops `testspg_dependantview` and its dependencies
        and recreates them manually, thereby simulating an old state
        of the views in the db before changes to the view model's sql is made.
        Then we sync the views again and verify that everything was updated.
        """

        with closing(connection.cursor()) as cur:
            cur.execute("DROP VIEW testspg_relatedview CASCADE;")

            cur.execute(
                """CREATE VIEW testspg_relatedview as
                SELECT id AS model_id, name FROM testspg_testmodel;"""
            )

            cur.execute(
                """CREATE VIEW testspg_dependantview as
                        SELECT name from testspg_relatedview;"""
            )

            cur.execute("""SELECT name from testspg_relatedview;""")
            cur.execute("""SELECT name from testspg_dependantview;""")

        call_command("sync_pgviews", "--force")

        with closing(connection.cursor()) as cur:
            cur.execute(
                """SELECT COUNT(*) FROM pg_views
                        WHERE viewname LIKE 'testspg_%';"""
            )

            (count,) = cur.fetchone()
            self.assertEqual(count, 4)

            with self.assertRaises(DatabaseError):
                cur.execute("""SELECT name from testspg_relatedview;""")

            with self.assertRaises(DatabaseError):
                cur.execute("""SELECT name from testspg_dependantview;""")

    def test_sync_depending_materialized_views(self) -> None:
        """Refresh views that depend on materialized views."""
        with closing(connection.cursor()) as cur:
            cur.execute(
                """DROP MATERIALIZED VIEW testspg_materializedrelatedview
                CASCADE;"""
            )

            cur.execute(
                """CREATE MATERIALIZED VIEW testspg_materializedrelatedview as
                SELECT id AS model_id, name FROM testspg_testmodel;"""
            )

            cur.execute(
                """CREATE MATERIALIZED VIEW testspg_dependantmaterializedview
                as SELECT name from testspg_materializedrelatedview;"""
            )
            cur.execute("""SELECT name from testspg_materializedrelatedview;""")
            cur.execute("""SELECT name from testspg_dependantmaterializedview;""")

        call_command("sync_pgviews", "--force")

        with closing(connection.cursor()) as cur:
            cur.execute(
                """SELECT COUNT(*) FROM pg_views
                        WHERE viewname LIKE 'testspg_%';"""
            )

            (count,) = cur.fetchone()
            self.assertEqual(count, 4)

            with self.assertRaises(DatabaseError):
                cur.execute(
                    """SELECT name from
                    testspg_dependantmaterializedview;"""
                )
                cur.execute("""SELECT name from testspg_materializedrelatedview; """)

            with self.assertRaises(DatabaseError):
                cur.execute(
                    """SELECT name from
                    testspg_dependantmaterializedview;"""
                )
