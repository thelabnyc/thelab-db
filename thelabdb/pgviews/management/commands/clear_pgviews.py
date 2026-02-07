from typing import Any
import logging

from django.core.management.base import BaseCommand
from django.db import connection

from ...migrate import get_view_classes
from ...view import MaterializedView, clear_view

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Manually drop all Postgres views.

    The pre_migrate signal handler handles this automatically during
    migrations; use this command for manual intervention or if automatic
    dropping is disabled via ``PGVIEWS_DROP_BEFORE_MIGRATE``.
    """

    help = (
        "Manually drop all Postgres views. The pre_migrate signal handler "
        "handles this automatically during migrations."
    )

    def handle(self, **options: Any) -> None:
        """ """
        for view_cls in get_view_classes():
            python_name = f"{view_cls._meta.app_label}.{view_cls.__name__}"
            status = clear_view(
                connection,
                view_cls._meta.db_table,
                materialized=issubclass(view_cls, MaterializedView),
            )
            if status == "DROPPED":
                msg = "dropped"
            else:
                msg = "not dropped"
            logger.info(
                "%(python_name)s (%(view_name)s): %(msg)s"
                % {
                    "python_name": python_name,
                    "view_name": view_cls._meta.db_table,
                    "msg": msg,
                }
            )
