"""Django middleware for database transaction management.

This module provides middleware for automatically wrapping mutating HTTP requests
in database transactions, allowing safe methods to bypass transaction overhead.

It also provides a ``set_rollback`` function for use with Django REST Framework
exception handlers.
"""

from collections.abc import Callable
from contextlib import ExitStack
from typing import ClassVar

from django.db import connections, transaction
from django.http import HttpRequest, HttpResponse


class AtomicMutatingRequestsMiddleware:
    """Middleware that wraps mutating HTTP requests in database transactions.

    This middleware provides automatic transaction management for Django views by
    wrapping mutating requests (POST, PUT, PATCH, DELETE) in database transactions
    while allowing safe methods (GET, HEAD, OPTIONS, TRACE) to bypass the
    transaction overhead.

    This is similar to Django's ``ATOMIC_REQUESTS`` database setting, but with
    a key difference: safe HTTP methods bypass the transaction wrapper entirely,
    avoiding the overhead of starting and committing empty transactions.

    Like Django's ``make_view_atomic``, this middleware supports multiple database
    connections. Each configured database is wrapped in its own transaction.

    Attributes:
        safe_http_methods: HTTP methods that bypass transaction wrapping.
            Override this in a subclass to customize which methods are considered safe.
        databases: Database aliases to wrap in transactions. If ``None`` (the default),
            all configured databases are wrapped. Override in a subclass to limit
            which databases are wrapped.

    Example:
        Add to your Django settings::

            MIDDLEWARE = [
                # ... other middleware
                'thelabdb.AtomicMutatingRequestsMiddleware',
                # ... other middleware
            ]

        To customize safe methods, subclass the middleware::

            class CustomAtomicMiddleware(AtomicMutatingRequestsMiddleware):
                safe_http_methods = frozenset({"GET", "HEAD"})

        To limit which databases are wrapped::

            class SingleDbAtomicMiddleware(AtomicMutatingRequestsMiddleware):
                databases = frozenset({"default"})
    """

    #: HTTP methods that are considered safe and do not require transaction wrapping.
    #: These methods should not modify server state per RFC 7231.
    #: Override in a subclass to customize behavior.
    safe_http_methods: ClassVar[frozenset[str]] = frozenset(
        {"GET", "HEAD", "OPTIONS", "TRACE"}
    )

    #: Database aliases to wrap in transactions.
    #: If None (the default), all configured databases are wrapped.
    #: Override in a subclass to limit which databases are wrapped.
    databases: ClassVar[frozenset[str] | None] = None

    @classmethod
    def _get_databases(cls) -> frozenset[str]:
        """Get database aliases that this middleware should wrap.

        Returns:
            A frozenset of database aliases to wrap in transactions.
            If ``databases`` is None, returns all configured database aliases.
        """
        if cls.databases is not None:
            return cls.databases
        return frozenset(connections.settings.keys())

    @classmethod
    def set_rollback(
        cls,
        request: HttpRequest | None,
    ) -> None:
        """Mark current transactions/savepoints for rollback if in an atomic block.

        This function extends ``rest_framework.views.set_rollback`` to also work with
        :class:`AtomicMutatingRequestsMiddleware`. DRF's version only triggers rollback
        when ``ATOMIC_REQUESTS=True``, but our middleware wraps mutating requests in
        transactions without that setting.

        This function iterates over all database connections that this middleware
        manages and marks each one for rollback if appropriate.

        Behavior:
            - If ``ATOMIC_REQUESTS=True``: Always mark for rollback (original DRF behavior)
            - If ``ATOMIC_REQUESTS=False``: Only mark for rollback on mutating methods
            (POST, PUT, PATCH, DELETE) since those are what our middleware wraps

        Example:
            In a DRF exception handler::

                from thelabdb.middleware import AtomicMutatingRequestsMiddleware

                def exception_handler(exc, context):
                    request = context.get("request") if context else None
                    AtomicMutatingRequestsMiddleware.set_rollback(request)
                    # ... handle exception ...
        """
        managed_databases = cls._get_databases()
        for db in connections.all():
            if not db.in_atomic_block:
                continue
            # If ATOMIC_REQUESTS is enabled, use original DRF behavior
            if db.settings_dict["ATOMIC_REQUESTS"]:
                db.set_rollback(True)
            # Otherwise, only mark rollback for mutating requests on managed databases
            elif (
                db.alias in managed_databases
                and request is not None
                and request.method not in cls.safe_http_methods
            ):
                db.set_rollback(True)

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Initialize the middleware."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request.

        Wraps mutating requests in database transactions. Safe methods
        (GET, HEAD, OPTIONS, TRACE) bypass the transaction wrapper.

        Each configured database is wrapped in its own transaction, similar
        to Django's ``make_view_atomic`` behavior. This ensures proper
        transaction isolation across multiple database connections.
        """
        if request.method in self.safe_http_methods:
            return self.get_response(request)

        db_aliases = self._get_databases()
        with ExitStack() as stack:
            for alias in db_aliases:
                stack.enter_context(transaction.atomic(using=alias))
            return self.get_response(request)
