# Welcome

This repository is a collection of DB fields and utilities for Django.

## Installation

Install via pip:

```sh
pip install thelabdb
```

Add to your project's installed applications in `settings.py`.

```py
INSTALLED_APPS = [
  # …

  # Install the main `thelabdb` app.
  "thelabdb",

  # If you're using the PostgreSQL views functionality (requires PostgreSQL be
  # used as your DB), install that app as well.
  "thelabdb.pgviews",

  # …
]
```

Now you're ready to start using thelabdb.

## Next Steps

{nav}

<style type="text/css">
.autodoc { display: none; }
</style>

::: thelabdb.tests.settings.docgen_setup.setup
