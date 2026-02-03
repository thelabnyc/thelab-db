"""Tests for AtomicMutatingRequestsMiddleware."""

from unittest.mock import MagicMock, patch

from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.test import SimpleTestCase, TransactionTestCase

from thelabdb.middleware import AtomicMutatingRequestsMiddleware

from .models import UppercaseChar


class AtomicMutatingRequestsMiddlewareTest(SimpleTestCase):
    """Unit tests for AtomicMutatingRequestsMiddleware using mocks."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_response = HttpResponse("OK")
        self.mock_get_response = MagicMock(return_value=self.mock_response)
        self.middleware = AtomicMutatingRequestsMiddleware(self.mock_get_response)

    def test_safe_methods_bypass_transaction(self) -> None:
        """Safe HTTP methods should not be wrapped in a transaction."""
        for method in AtomicMutatingRequestsMiddleware.safe_http_methods:
            with self.subTest(method=method):
                request = HttpRequest()
                request.method = method

                with patch("thelabdb.middleware.transaction.atomic") as mock_atomic:
                    response = self.middleware(request)

                mock_atomic.assert_not_called()
                self.assertEqual(response, self.mock_response)
                self.mock_get_response.assert_called_with(request)

    def test_mutating_methods_use_transaction(self) -> None:
        """Mutating HTTP methods should be wrapped in a transaction."""
        mutating_methods = ["POST", "PUT", "PATCH", "DELETE"]

        for method in mutating_methods:
            with self.subTest(method=method):
                self.mock_get_response.reset_mock()
                request = HttpRequest()
                request.method = method

                with (
                    patch("thelabdb.middleware.transaction.atomic") as mock_atomic,
                    patch(
                        "thelabdb.middleware.connections.settings",
                        {"default": {"ATOMIC_REQUESTS": False}},
                    ),
                ):
                    mock_context = MagicMock()
                    mock_atomic.return_value = mock_context
                    mock_context.__enter__ = MagicMock(return_value=None)
                    mock_context.__exit__ = MagicMock(return_value=False)

                    response = self.middleware(request)

                mock_atomic.assert_called_once_with(using="default")
                mock_context.__enter__.assert_called_once()
                mock_context.__exit__.assert_called_once()
                self.assertEqual(response, self.mock_response)

    def test_safe_http_methods_is_frozenset(self) -> None:
        """safe_http_methods should be a frozenset for immutability."""
        self.assertIsInstance(
            AtomicMutatingRequestsMiddleware.safe_http_methods, frozenset
        )

    def test_safe_http_methods_contains_expected_methods(self) -> None:
        """safe_http_methods should contain GET, HEAD, OPTIONS, TRACE."""
        expected = {"GET", "HEAD", "OPTIONS", "TRACE"}
        self.assertEqual(AtomicMutatingRequestsMiddleware.safe_http_methods, expected)

    def test_response_passthrough(self) -> None:
        """The middleware should return the response from get_response unchanged."""
        request = HttpRequest()
        request.method = "GET"

        response = self.middleware(request)

        self.assertIs(response, self.mock_response)

    def test_subclass_can_override_safe_methods(self) -> None:
        """Subclasses should be able to override safe_http_methods."""

        class CustomMiddleware(AtomicMutatingRequestsMiddleware):
            safe_http_methods = frozenset({"GET"})

        middleware = CustomMiddleware(self.mock_get_response)

        # GET should still be safe
        request = HttpRequest()
        request.method = "GET"
        with patch("thelabdb.middleware.transaction.atomic") as mock_atomic:
            middleware(request)
        mock_atomic.assert_not_called()

        # HEAD is no longer safe in our custom middleware
        request = HttpRequest()
        request.method = "HEAD"
        with (
            patch("thelabdb.middleware.transaction.atomic") as mock_atomic,
            patch(
                "thelabdb.middleware.connections.settings",
                {"default": {"ATOMIC_REQUESTS": False}},
            ),
        ):
            mock_context = MagicMock()
            mock_atomic.return_value = mock_context
            mock_context.__enter__ = MagicMock(return_value=None)
            mock_context.__exit__ = MagicMock(return_value=False)
            middleware(request)
        mock_atomic.assert_called_once_with(using="default")

    def test_multiple_databases_wrapped_in_transactions(self) -> None:
        """All configured databases should be wrapped in their own transactions."""
        request = HttpRequest()
        request.method = "POST"

        with (
            patch("thelabdb.middleware.transaction.atomic") as mock_atomic,
            patch(
                "thelabdb.middleware.connections.settings",
                {
                    "default": {"ATOMIC_REQUESTS": False},
                    "secondary": {"ATOMIC_REQUESTS": False},
                },
            ),
        ):
            mock_context = MagicMock()
            mock_atomic.return_value = mock_context
            mock_context.__enter__ = MagicMock(return_value=None)
            mock_context.__exit__ = MagicMock(return_value=False)

            self.middleware(request)

        # Should be called once for each database
        self.assertEqual(mock_atomic.call_count, 2)
        mock_atomic.assert_any_call(using="default")
        mock_atomic.assert_any_call(using="secondary")

    def test_subclass_can_limit_databases(self) -> None:
        """Subclasses should be able to limit which databases are wrapped."""

        class SingleDbMiddleware(AtomicMutatingRequestsMiddleware):
            databases = frozenset({"default"})

        middleware = SingleDbMiddleware(self.mock_get_response)

        request = HttpRequest()
        request.method = "POST"

        with (
            patch("thelabdb.middleware.transaction.atomic") as mock_atomic,
            patch(
                "thelabdb.middleware.connections.settings",
                {
                    "default": {"ATOMIC_REQUESTS": False},
                    "secondary": {"ATOMIC_REQUESTS": False},
                },
            ),
        ):
            mock_context = MagicMock()
            mock_atomic.return_value = mock_context
            mock_context.__enter__ = MagicMock(return_value=None)
            mock_context.__exit__ = MagicMock(return_value=False)

            middleware(request)

        # Should only be called for the "default" database
        mock_atomic.assert_called_once_with(using="default")


class SetRollbackTest(SimpleTestCase):
    """Unit tests for the set_rollback function."""

    def test_set_rollback_marks_rollback_for_mutating_methods(self) -> None:
        """set_rollback should mark rollback for mutating methods when in atomic block."""
        mutating_methods = ["POST", "PUT", "PATCH", "DELETE"]

        for method in mutating_methods:
            with self.subTest(method=method):
                request = HttpRequest()
                request.method = method

                # Mock connection that is in an atomic block without ATOMIC_REQUESTS
                mock_db = MagicMock()
                mock_db.alias = "default"
                mock_db.in_atomic_block = True
                mock_db.settings_dict = {"ATOMIC_REQUESTS": False}

                with (
                    patch(
                        "thelabdb.middleware.connections.all", return_value=[mock_db]
                    ),
                    patch(
                        "thelabdb.middleware.connections.settings",
                        {"default": mock_db.settings_dict},
                    ),
                ):
                    AtomicMutatingRequestsMiddleware.set_rollback(request)

                mock_db.set_rollback.assert_called_once_with(True)

    def test_set_rollback_skips_safe_methods(self) -> None:
        """set_rollback should not mark rollback for safe methods."""
        for method in AtomicMutatingRequestsMiddleware.safe_http_methods:
            with self.subTest(method=method):
                request = HttpRequest()
                request.method = method

                mock_db = MagicMock()
                mock_db.alias = "default"
                mock_db.in_atomic_block = True
                mock_db.settings_dict = {"ATOMIC_REQUESTS": False}

                with (
                    patch(
                        "thelabdb.middleware.connections.all", return_value=[mock_db]
                    ),
                    patch(
                        "thelabdb.middleware.connections.settings",
                        {"default": mock_db.settings_dict},
                    ),
                ):
                    AtomicMutatingRequestsMiddleware.set_rollback(request)

                mock_db.set_rollback.assert_not_called()

    def test_set_rollback_skips_connections_not_in_atomic_block(self) -> None:
        """set_rollback should skip connections not in an atomic block."""
        request = HttpRequest()
        request.method = "POST"

        mock_db = MagicMock()
        mock_db.alias = "default"
        mock_db.in_atomic_block = False
        mock_db.settings_dict = {"ATOMIC_REQUESTS": False}

        with (
            patch("thelabdb.middleware.connections.all", return_value=[mock_db]),
            patch(
                "thelabdb.middleware.connections.settings",
                {"default": mock_db.settings_dict},
            ),
        ):
            AtomicMutatingRequestsMiddleware.set_rollback(request)

        mock_db.set_rollback.assert_not_called()

    def test_set_rollback_with_atomic_requests_enabled(self) -> None:
        """set_rollback should always mark rollback when ATOMIC_REQUESTS is True."""
        # Even for a GET request, if ATOMIC_REQUESTS is True, mark rollback
        request = HttpRequest()
        request.method = "GET"

        mock_db = MagicMock()
        mock_db.alias = "default"
        mock_db.in_atomic_block = True
        mock_db.settings_dict = {"ATOMIC_REQUESTS": True}

        with (
            patch("thelabdb.middleware.connections.all", return_value=[mock_db]),
            patch(
                "thelabdb.middleware.connections.settings",
                {"default": mock_db.settings_dict},
            ),
        ):
            AtomicMutatingRequestsMiddleware.set_rollback(request)

        mock_db.set_rollback.assert_called_once_with(True)

    def test_set_rollback_with_none_request(self) -> None:
        """set_rollback with None request should only mark rollback for ATOMIC_REQUESTS."""
        mock_db_atomic = MagicMock()
        mock_db_atomic.alias = "default"
        mock_db_atomic.in_atomic_block = True
        mock_db_atomic.settings_dict = {"ATOMIC_REQUESTS": True}

        mock_db_middleware = MagicMock()
        mock_db_middleware.alias = "secondary"
        mock_db_middleware.in_atomic_block = True
        mock_db_middleware.settings_dict = {"ATOMIC_REQUESTS": False}

        with (
            patch(
                "thelabdb.middleware.connections.all",
                return_value=[mock_db_atomic, mock_db_middleware],
            ),
            patch(
                "thelabdb.middleware.connections.settings",
                {
                    "default": mock_db_atomic.settings_dict,
                    "secondary": mock_db_middleware.settings_dict,
                },
            ),
        ):
            AtomicMutatingRequestsMiddleware.set_rollback(None)

        # ATOMIC_REQUESTS=True should be marked for rollback
        mock_db_atomic.set_rollback.assert_called_once_with(True)
        # ATOMIC_REQUESTS=False with None request should NOT be marked
        mock_db_middleware.set_rollback.assert_not_called()

    def test_set_rollback_handles_multiple_connections(self) -> None:
        """set_rollback should handle multiple database connections."""
        request = HttpRequest()
        request.method = "POST"

        mock_db1 = MagicMock()
        mock_db1.alias = "default"
        mock_db1.in_atomic_block = True
        mock_db1.settings_dict = {"ATOMIC_REQUESTS": False}

        mock_db2 = MagicMock()
        mock_db2.alias = "secondary"
        mock_db2.in_atomic_block = True
        mock_db2.settings_dict = {"ATOMIC_REQUESTS": False}

        mock_db3 = MagicMock()
        mock_db3.alias = "tertiary"
        mock_db3.in_atomic_block = False  # Not in atomic block
        mock_db3.settings_dict = {"ATOMIC_REQUESTS": False}

        with (
            patch(
                "thelabdb.middleware.connections.all",
                return_value=[mock_db1, mock_db2, mock_db3],
            ),
            patch(
                "thelabdb.middleware.connections.settings",
                {
                    "default": mock_db1.settings_dict,
                    "secondary": mock_db2.settings_dict,
                    "tertiary": mock_db3.settings_dict,
                },
            ),
        ):
            AtomicMutatingRequestsMiddleware.set_rollback(request)

        mock_db1.set_rollback.assert_called_once_with(True)
        mock_db2.set_rollback.assert_called_once_with(True)
        mock_db3.set_rollback.assert_not_called()

    def test_set_rollback_respects_databases_attribute(self) -> None:
        """set_rollback should only affect databases in the databases attribute."""

        class SingleDbMiddleware(AtomicMutatingRequestsMiddleware):
            databases = frozenset({"default"})

        request = HttpRequest()
        request.method = "POST"

        mock_db1 = MagicMock()
        mock_db1.alias = "default"
        mock_db1.in_atomic_block = True
        mock_db1.settings_dict = {"ATOMIC_REQUESTS": False}

        mock_db2 = MagicMock()
        mock_db2.alias = "secondary"
        mock_db2.in_atomic_block = True
        mock_db2.settings_dict = {"ATOMIC_REQUESTS": False}

        with (
            patch(
                "thelabdb.middleware.connections.all",
                return_value=[mock_db1, mock_db2],
            ),
            patch(
                "thelabdb.middleware.connections.settings",
                {
                    "default": mock_db1.settings_dict,
                    "secondary": mock_db2.settings_dict,
                },
            ),
        ):
            SingleDbMiddleware.set_rollback(request)

        # Only "default" should be marked for rollback
        mock_db1.set_rollback.assert_called_once_with(True)
        # "secondary" should NOT be marked since it's not in the databases attribute
        mock_db2.set_rollback.assert_not_called()


class AtomicMutatingRequestsMiddlewareTransactionTest(TransactionTestCase):
    """Integration tests for AtomicMutatingRequestsMiddleware with real transactions."""

    def test_rollback_on_exception(self) -> None:
        """Database changes should be rolled back when an exception occurs."""

        def view_that_raises(request: HttpRequest) -> HttpResponse:
            UppercaseChar.objects.create(value="rollback_test")
            raise ValueError("Simulated error")

        middleware = AtomicMutatingRequestsMiddleware(view_that_raises)
        request = HttpRequest()
        request.method = "POST"

        with self.assertRaises(ValueError):
            middleware(request)

        # Verify the object was not persisted due to rollback
        self.assertFalse(UppercaseChar.objects.filter(value="ROLLBACK_TEST").exists())

    def test_commit_on_success(self) -> None:
        """Database changes should be committed when view succeeds."""

        def successful_view(request: HttpRequest) -> HttpResponse:
            UppercaseChar.objects.create(value="commit_test")
            return HttpResponse("Created")

        middleware = AtomicMutatingRequestsMiddleware(successful_view)
        request = HttpRequest()
        request.method = "POST"

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        # Verify the object was persisted
        self.assertTrue(UppercaseChar.objects.filter(value="COMMIT_TEST").exists())

    def test_safe_method_does_not_wrap_in_transaction(self) -> None:
        """Safe methods should not wrap operations in transactions."""
        # This test verifies that safe methods actually bypass the transaction
        # by checking that we're not inside a transaction.atomic() block
        atomic_entered = []

        def view_checking_atomic(request: HttpRequest) -> HttpResponse:
            # Check if we're in an atomic block by trying to detect the
            # connection's in_atomic_block state
            atomic_entered.append(connection.in_atomic_block)
            return HttpResponse("OK")

        middleware = AtomicMutatingRequestsMiddleware(view_checking_atomic)

        # Test safe method
        request = HttpRequest()
        request.method = "GET"
        middleware(request)

        # For GET, we should not be in an atomic block
        # (unless there's an outer transaction, which TransactionTestCase shouldn't have)
        self.assertFalse(atomic_entered[0])

        # Test mutating method
        atomic_entered.clear()
        request = HttpRequest()
        request.method = "POST"
        middleware(request)

        # For POST, we should be in an atomic block
        self.assertTrue(atomic_entered[0])

    def test_set_rollback_causes_transaction_rollback(self) -> None:
        """set_rollback should cause the transaction to roll back on exit."""

        def view_with_rollback(request: HttpRequest) -> HttpResponse:
            UppercaseChar.objects.create(value="set_rollback_test")
            # Simulate what a DRF exception handler would do
            AtomicMutatingRequestsMiddleware.set_rollback(request)
            return HttpResponse("OK")

        middleware = AtomicMutatingRequestsMiddleware(view_with_rollback)
        request = HttpRequest()
        request.method = "POST"

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        # Even though the view returned successfully, the object should not
        # be persisted because set_rollback was called
        self.assertFalse(
            UppercaseChar.objects.filter(value="SET_ROLLBACK_TEST").exists()
        )

    def test_set_rollback_does_not_affect_safe_methods(self) -> None:
        """set_rollback should not affect safe methods (they have no transaction)."""

        def view_creating_object(request: HttpRequest) -> HttpResponse:
            UppercaseChar.objects.create(value="safe_method_test")
            # Calling set_rollback on a safe method should be a no-op
            AtomicMutatingRequestsMiddleware.set_rollback(request)
            return HttpResponse("OK")

        middleware = AtomicMutatingRequestsMiddleware(view_creating_object)
        request = HttpRequest()
        request.method = "GET"

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        # For safe methods, the object should be persisted since there's
        # no transaction to roll back
        self.assertTrue(UppercaseChar.objects.filter(value="SAFE_METHOD_TEST").exists())
