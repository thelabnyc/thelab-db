from typing import Any, cast

from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.models.sql import query

from . import compiler


class NonQuotingQuery(query.Query):
    """Query class that uses the NonQuotingCompiler."""

    def get_compiler(
        self,
        using: str | None = None,
        connection: Any | None = None,
        elide_empty: bool = True,
    ) -> Any:
        """Get the NonQuotingCompiler object."""
        if using is None and connection is None:
            raise ValueError("Need either using or connection")
        if using:
            connection = connections[using]

        conn = cast(BaseDatabaseWrapper, connection)
        for alias, annotation in self.annotation_select.items():
            conn.ops.check_expression_support(annotation)

        return compiler.NonQuotingCompiler(self, conn, using)
