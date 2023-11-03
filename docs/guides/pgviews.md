# PostgreSQL Views

Adds first-class support for [PostgreSQL](http://www.postgresql.org/) view features to the Django ORM.

## Why?

PostgreSQL is an excellent data store, with a host of useful and efficiently-implemented features. Unfortunately these features are not exposed through Django's ORM, primarily because the framework has to support several SQL backends and so can only provide a set of features common to all of them.

The features made available here replace some of the following practices:

-  Manual denormalization on `save()` (such that model saves may result in three or more separate queries).
-  Sequences represented by a one-to-many, with an `order` integer field.
-  Complex types represented by JSON in a text field.

## Examples

```py
from django.db import models
from thelabdb.pgviews import view as pg


class Customer(models.Model):
    name = models.CharField(max_length=100)
    post_code = models.CharField(max_length=20)
    is_preferred = models.BooleanField(default=False)

    class Meta:
        app_label = 'myapp'

class PreferredCustomer(pg.View):
    projection = ['myapp.Customer.*',]
    dependencies = ['myapp.OtherView',]
    sql = """SELECT * FROM myapp_customer WHERE is_preferred = TRUE;"""

    class Meta:
      app_label = 'myapp'
      db_table = 'myapp_preferredcustomer'
      managed = False
```

The SQL produced by this might look like:

```sql
CREATE VIEW myapp_preferredcustomer AS
SELECT * FROM myapp_customer WHERE is_preferred = TRUE;
```

To create all your views, run `python manage.py sync_pgviews`

You can also specify field names, which will map onto fields in your View:

```py
from django.db import models
from thelabdb.pgviews import view as pg


VIEW_SQL = """
    SELECT name, post_code FROM myapp_customer WHERE is_preferred = TRUE
"""


class PreferredCustomer(pg.View):
    name = models.CharField(max_length=100)
    post_code = models.CharField(max_length=20)

    sql = VIEW_SQL
```

## Usage

To map onto a View, simply extend `thelabdb.pgviews.view.View`, assign SQL to the
`sql` argument and define a `db_table`. You must _always_ set `managed = False`
on the `Meta` class.

Views can be created in a number of ways:

1. Define fields to map onto the VIEW output
2. Define a projection that describes the VIEW fields

### Define Fields

Define the fields as you would with any Django Model:

```py
from django.db import models
from thelabdb.pgviews import view as pg


VIEW_SQL = """
    SELECT name, post_code FROM myapp_customer WHERE is_preferred = TRUE
"""


class PreferredCustomer(pg.View):
    name = models.CharField(max_length=100)
    post_code = models.CharField(max_length=20)

    sql = VIEW_SQL

    class Meta:
      managed = False
      db_table = 'my_sql_view'
```

### Define Projection

Views can take a projection to figure out what fields it needs to
map onto for a view. To use this, set the `projection` attribute:

```py
from thelabdb.pgviews import view as pg


class PreferredCustomer(pg.View):
    projection = ['myapp.Customer.*',]
    sql = """SELECT * FROM myapp_customer WHERE is_preferred = TRUE;"""

    class Meta:
      db_table = 'my_sql_view'
      managed = False
```

This will take all fields on `myapp.Customer` and apply them to
`PreferredCustomer`

## Features

### Updating Views

Sometimes your models change and you need your Database Views to reflect the new
data. Updating the View logic is as simple as modifying the underlying SQL and
running:

```bash
python manage.py sync_pgviews --force
```

This will forcibly update any views that conflict with your new SQL.

### Dependencies

You can specify other views you depend on. This ensures the other views are
installed beforehand. Using dependencies also ensures that your views get
refreshed correctly when using `sync_pgviews --force`.

**Note:** Views are synced after the Django application has migrated and adding
models to the dependency list will cause syncing to fail.

Example:

```py
from thelabdb.pgviews import view as pg

class PreferredCustomer(pg.View):
    dependencies = ['myapp.OtherView',]
    sql = """SELECT * FROM myapp_customer WHERE is_preferred = TRUE;"""

    class Meta:
      app_label = 'myapp'
      db_table = 'myapp_preferredcustomer'
      managed = False
```

### Materialized Views

Postgres 9.3 and up supports [materialized views](http://www.postgresql.org/docs/current/static/sql-creatematerializedview.html)
which allow you to cache the results of views, potentially allowing them
to load faster.

However, you do need to manually refresh the view. To do this automatically,
you can attach [signals](https://docs.djangoproject.com/en/1.8/ref/signals/)
and call the refresh function.

Example:

```py
from django.db import models
from thelabdb.pgviews import view as pg


VIEW_SQL = """
    SELECT name, post_code FROM myapp_customer WHERE is_preferred = TRUE
"""

class Customer(models.Model):
    name = models.CharField(max_length=100)
    post_code = models.CharField(max_length=20)
    is_preferred = models.BooleanField(default=True)


class PreferredCustomer(pg.MaterializedView):
    name = models.CharField(max_length=100)
    post_code = models.CharField(max_length=20)

    sql = VIEW_SQL


@receiver(post_save, sender=Customer)
def customer_saved(sender, action=None, instance=None, **kwargs):
    PreferredCustomer.refresh()
```

Postgres 9.4 and up allow materialized views to be refreshed concurrently, without blocking reads, as long as a
unique index exists on the materialized view. To enable concurrent refresh, specify the name of a column that can be
used as a unique index on the materialized view. Unique index can be defined on more than one column of a materialized
view. Once enabled, passing `concurrently=True` to the model's refresh method will result in postgres performing the
refresh concurrently. (Note that the refresh method itself blocks until the refresh is complete; concurrent refresh is
most useful when materialized views are updated in another process or thread.)

Example:

```py
from django.db import models
from thelabdb.pgviews import view as pg


VIEW_SQL = """
    SELECT id, name, post_code FROM myapp_customer WHERE is_preferred = TRUE
"""

class PreferredCustomer(pg.MaterializedView):
    concurrent_index = 'id, post_code'
    sql = VIEW_SQL

    name = models.CharField(max_length=100)
    post_code = models.CharField(max_length=20)


@receiver(post_save, sender=Customer)
def customer_saved(sender, action=None, instance=None, **kwargs):
    PreferredCustomer.refresh(concurrently=True)
```

### Custom Schema

You can define any table name you wish for your views. They can even live inside your own custom
[PostgreSQL schema](http://www.postgresql.org/docs/current/static/ddl-schemas.html).

```py
from thelabdb.pgviews import view as pg


class PreferredCustomer(pg.View):
    sql = """SELECT * FROM myapp_customer WHERE is_preferred = TRUE;"""

    class Meta:
      db_table = 'my_custom_schema.preferredcustomer'
      managed = False
```

### Sync Listeners

#### `thelabdb.pgviews.signals.view_synced`

Fired every time a VIEW is synchronized with the database.

Provides args:

- `sender`: View Class
- `update`: Whether the view to be updated
- `force`: Whether `force` was passed
- `status`: The result of creating the view e.g. `EXISTS`, `FORCE_REQUIRED`
- `has_changed`: Whether the view had to change

#### `thelabdb.pgviews.signals.all_views_synced`

Sent after all Postgres VIEWs are synchronized.

Provides args:

- `sender`: Always `None`
