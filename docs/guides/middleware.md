# Middleware

## AtomicMutatingRequestsMiddleware

Middleware that automatically wraps mutating HTTP requests in database transactions.

### Why Use This?

Django provides the `ATOMIC_REQUESTS` database setting which wraps every request in a transaction. While this ensures data integrity, it has overhead: even read-only requests (GET, HEAD, etc.) start and commit a transaction.

`AtomicMutatingRequestsMiddleware` provides a smarter approach:

- **Mutating methods** (POST, PUT, PATCH, DELETE) are wrapped in `transaction.atomic()`
- **Safe methods** (GET, HEAD, OPTIONS, TRACE) bypass transaction overhead entirely

This gives you the safety of automatic transactions for writes while avoiding unnecessary overhead for reads.

### Installation

Add the middleware to your Django settings:

```python
MIDDLEWARE = [
    # ... other middleware
    'thelabdb.middleware.AtomicMutatingRequestsMiddleware',
    # ... other middleware
]
```

### How It Works

The middleware checks the HTTP method of each incoming request:

1. If the method is in `safe_http_methods` (GET, HEAD, OPTIONS, TRACE), the request passes through without transaction wrapping
2. For all other methods (POST, PUT, PATCH, DELETE, etc.), the request is wrapped in `transaction.atomic()`

If an exception occurs during a mutating request, all database changes are automatically rolled back.

### Customizing Safe Methods

You can customize which HTTP methods are considered safe by subclassing the middleware:

```python
from thelabdb.middleware import AtomicMutatingRequestsMiddleware


class CustomAtomicMiddleware(AtomicMutatingRequestsMiddleware):
    # Only treat GET as safe; all other methods use transactions
    safe_http_methods = frozenset({"GET"})
```

Then use your custom middleware in settings:

```python
MIDDLEWARE = [
    # ... other middleware
    'myapp.middleware.CustomAtomicMiddleware',
    # ... other middleware
]
```

### Django REST Framework Integration

**Important:** If you use this middleware with Django REST Framework, you must configure a custom exception handler to ensure proper transaction rollback.

#### Why This Is Needed

When DRF handles an exception (e.g., validation errors, permission denied), it catches the exception and returns an error response. This happens *inside* the middleware's `transaction.atomic()` block, which means:

1. The exception is caught by DRF before propagating to the middleware
2. The middleware sees a successful response (the error response)
3. The transaction commits, persisting any partial database changes

To prevent this, you need to explicitly mark the transaction for rollback when DRF handles an exception.

#### The `set_rollback` Class Method

The `AtomicMutatingRequestsMiddleware.set_rollback` class method is designed to work correctly in this scenario. It extends DRF's `rest_framework.views.set_rollback` to also work with `AtomicMutatingRequestsMiddleware`.

**Behavior:**

- Iterates over **all** database connections (supports multi-database setups)
- Only marks connections that are actually in an atomic block
- If `ATOMIC_REQUESTS=True`: Always marks for rollback (original DRF behavior)
- If `ATOMIC_REQUESTS=False`: Only marks for rollback on mutating methods (POST, PUT, PATCH, DELETE)

This means `AtomicMutatingRequestsMiddleware.set_rollback` works correctly whether you're using:

- Only `AtomicMutatingRequestsMiddleware`
- Only `ATOMIC_REQUESTS=True`
- Both together
- Multi-database configurations

#### Setting Up the Exception Handler

Create a custom exception handler that calls `AtomicMutatingRequestsMiddleware.set_rollback`:

```python
# myapp/exceptions.py
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response
from thelabdb.middleware import AtomicMutatingRequestsMiddleware


def exception_handler(exc: Exception, context: dict[str, Any] | None) -> Response | None:
    """DRF exception handler that ensures transaction rollback.

    This handler must be used when combining AtomicMutatingRequestsMiddleware
    with Django REST Framework. It marks the current transaction for rollback
    before returning the error response, ensuring that any database changes
    made before the exception are not committed.
    """
    request = context.get("request") if context else None

    if isinstance(exc, APIException):
        headers = {}
        if getattr(exc, "auth_header", None):
            headers["WWW-Authenticate"] = exc.auth_header
        if getattr(exc, "wait", None):
            headers["Retry-After"] = "%d" % exc.wait

        if isinstance(exc.detail, (list, dict)):
            data = exc.detail
        else:
            data = {"detail": exc.detail}

        AtomicMutatingRequestsMiddleware.set_rollback(request)
        return Response(data, status=exc.status_code, headers=headers)

    elif isinstance(exc, Http404):
        data = {"detail": str(_("Not found."))}
        AtomicMutatingRequestsMiddleware.set_rollback(request)
        return Response(data, status=status.HTTP_404_NOT_FOUND)

    elif isinstance(exc, PermissionDenied):
        data = {"detail": str(_("Permission denied."))}
        AtomicMutatingRequestsMiddleware.set_rollback(request)
        return Response(data, status=status.HTTP_403_FORBIDDEN)

    return None
```

Then configure DRF to use your custom exception handler in `settings.py`:

```python
REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'myapp.exceptions.exception_handler',
}
```

#### Simpler Alternative

If you don't need to customize the exception response format, you can wrap DRF's default handler:

```python
# myapp/exceptions.py
from rest_framework.views import exception_handler as drf_exception_handler
from thelabdb.middleware import AtomicMutatingRequestsMiddleware


def exception_handler(exc, context):
    """DRF exception handler that ensures transaction rollback."""
    request = context.get("request") if context else None
    AtomicMutatingRequestsMiddleware.set_rollback(request)
    return drf_exception_handler(exc, context)
```
