from typing import Any, cast

from django.db.models.sql import compiler


class NonQuotingCompiler(compiler.SQLCompiler):
    """Compiler for functions/statements that doesn't quote the db_table
    attribute.
    """

    def quote_name_unless_alias(self, name: str) -> str:
        """Don't quote the name."""
        if name in self.quote_cache:
            return cast(str, self.quote_cache[name])

        self.quote_cache[name] = name
        return name

    def as_sql(self, *args: Any, **kwargs: Any) -> Any:
        """Messy hack to create some table aliases for us."""
        db_table = self.query.model._meta.db_table  # type:ignore[union-attr]
        self.query.table_map[db_table] = [""]
        return super().as_sql(*args, **kwargs)
