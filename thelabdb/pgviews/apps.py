from __future__ import annotations

from typing import Any
import logging

from django import apps
from django.apps.config import AppConfig
from django.conf import settings
from django.db import connections
from django.db.migrations import Migration
from django.db.models import signals

logger = logging.getLogger(__name__)


class ViewConfig(apps.AppConfig):
    """The base configuration for Django PGViews. We use this to setup our
    pre_migrate and post_migrate signal handlers.
    """

    name = "thelabdb.pgviews"
    verbose_name = "Django Postgres Views"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Per-database counters/flags so multi-DB migrations don't interfere
        self._post_migrate_counter: dict[str, int] = {}
        self._pre_migrate_run: dict[str, bool] = {}

    def handle_pre_migrate(
        self,
        sender: AppConfig,
        app_config: AppConfig,
        using: str = "default",
        plan: list[tuple[Migration, bool]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Drop affected views before migrations run.

        Only executes on the first pre_migrate signal per migration cycle
        per database. Subsequent signals (one per app) are no-ops.

        Set ``PGVIEWS_DROP_BEFORE_MIGRATE = False`` in Django settings to
        disable automatic view dropping entirely.
        """
        if not getattr(settings, "PGVIEWS_DROP_BEFORE_MIGRATE", True):
            return

        if self._pre_migrate_run.get(using, False):
            return

        self._pre_migrate_run[using] = True

        if not plan:
            return

        # Import here to avoid circular imports at app-init time
        from .migrate import drop_affected_views

        drop_affected_views(connections[using], plan)

    def handle_post_migrate(
        self,
        sender: AppConfig,
        app_config: AppConfig,
        using: str = "default",
        **kwargs: Any,
    ) -> None:
        """Forcibly sync the views after all apps have migrated."""
        counter = self._post_migrate_counter.get(using, 0) + 1
        self._post_migrate_counter[using] = counter
        total = len(
            [a for a in apps.apps.get_app_configs() if a.models_module is not None]
        )

        if counter == total:
            logger.info("All applications have migrated, time to sync")
            # Import here otherwise Django doesn't start properly
            # (models in app init are not allowed)
            from .models import ViewSyncer

            vs = ViewSyncer()
            vs.run(force=True, update=True, connection=connections[using])

            # Reset flags for this database's next migration cycle
            self._post_migrate_counter[using] = 0
            self._pre_migrate_run[using] = False

    def ready(self) -> None:
        """Find and setup the apps to set the migrate hooks for."""
        signals.pre_migrate.connect(self.handle_pre_migrate)
        signals.post_migrate.connect(self.handle_post_migrate)
