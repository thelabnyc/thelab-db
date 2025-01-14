from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from ...models import ViewSyncer


class Command(BaseCommand):
    """
    Create/update Postgres views for all installed apps.
    """

    help = """Create/update Postgres views for all installed apps."""

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--no-update",
            action="store_false",
            dest="update",
            default=True,
            help="""Don't update existing views, only create new ones.""",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            default=False,
            help="""Force replacement of pre-existing views where
            breaking changes have been made to the schema.""",
        )

    def handle(self, force: bool, update: bool, **options: Any) -> None:
        vs = ViewSyncer()
        vs.run(force, update)
