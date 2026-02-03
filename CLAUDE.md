# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**thelabdb** is a Django package providing custom database fields and utilities. It includes encrypted fields (Fernet-based), character field variants, Pydantic-backed JSON fields, PostgreSQL view ORM integration, and transaction middleware.

Documentation: [https://thelabnyc.gitlab.io/thelab-db](https://thelabnyc.gitlab.io/thelab-db)

## Common Commands

### Testing

```bash
# Run full test suite via tox (Python 3.13 & 3.14 × Django 4.2, 5.1, 5.2)
uv run tox

# Run tests with SQLite (universal tests only)
DJANGO_SETTINGS_MODULE=thelabdb.tests.settings.sqlite uv run coverage run manage.py test --noinput -v 2 thelabdb.tests.testsuniv

# Run tests with PostgreSQL (includes PG-specific tests)
DJANGO_SETTINGS_MODULE=thelabdb.tests.settings.pg uv run coverage run manage.py test --noinput -v 2 thelabdb.tests.testsuniv thelabdb.tests.testspg

# Run a single test file
DJANGO_SETTINGS_MODULE=thelabdb.tests.settings.sqlite uv run python manage.py test thelabdb.tests.testsuniv.test_middleware

# Run a single test class or method
DJANGO_SETTINGS_MODULE=thelabdb.tests.settings.sqlite uv run python manage.py test thelabdb.tests.testsuniv.test_middleware.AtomicMutatingRequestsMiddlewareTests.test_get_does_not_use_transaction
```

### Type Checking & Linting

```bash
# Type check with mypy (strict mode enabled)
uv run mypy thelabdb/

# Run pre-commit hooks on all files
uv run pre-commit run --all-files
```

### Documentation

```bash
# Serve docs locally with live reload
make docs_serve

# Build docs
make docs_build
```

## Architecture

### Module Structure

- **`thelabdb.fields`** - Custom Django model fields
  - `fernet.py`: Fernet-encrypted field variants (EncryptedTextField, EncryptedCharField, EncryptedIntegerField, etc.)
  - `char.py`: UppercaseCharField, NullCharField (stores empty strings as NULL)
  - `pydantic.py`: PydanticField for JSON fields backed by Pydantic models
  - `hkdf.py`: HKDF key derivation for encrypted fields

- **`thelabdb.middleware`** - AtomicMutatingRequestsMiddleware
  - Wraps POST/PUT/PATCH/DELETE in `transaction.atomic()`, bypasses for GET/HEAD/OPTIONS/TRACE
  - Provides `set_rollback()` for DRF exception handlers

- **`thelabdb.pgviews`** - PostgreSQL view ORM integration
  - `View`, `ReadOnlyView`, `MaterializedView`, `ReadOnlyMaterializedView` base classes
  - Management commands: `sync_pgviews`, `clear_pgviews`

### Test Organization

- `thelabdb/tests/testsuniv/` - Tests that run on both SQLite and PostgreSQL
- `thelabdb/tests/testspg/` - PostgreSQL-specific tests (pgviews)
- `thelabdb/tests/settings/` - Django settings for different test environments

## Code Quality Requirements

- Strict mypy type checking is enforced (see `pyproject.toml` for config)
- All code must be type-hinted
- Pre-commit hooks validate commits (ruff, isort, pyupgrade, django-upgrade, commitizen)
- Python 3.13+ syntax required
