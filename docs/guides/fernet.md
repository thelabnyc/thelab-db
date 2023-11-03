# Fernet (Encrypted) Fields

These fields perform [Fernet](https://cryptography.io/en/latest/fernet/) symmetric encryption
using the [cryptography](https://cryptography.io/en/latest/) library.

## Prerequisites

Only PostgreSQL and SQLite are tested, but any Django database backend with support for `BinaryField` should work.

## Usage

Import and use the included field classes in your models:

```py
from django.db import models
from thelabdb.fields.fernet import EncryptedTextField


class MyModel(models.Model):
    name = EncryptedTextField()
```

You can assign values to and read values from the `name` field as usual, but the values will automatically be encrypted before being sent to the database and decrypted when read from the database.

Encryption and decryption are performed in your app; the secret key is never sent to the database server. The database sees only the encrypted value of this field.

### Field types

Several other field classes are included:

- `EncryptedCharField`
- `EncryptedEmailField`
- `EncryptedIntegerField`
- `EncryptedDateField`
- `EncryptedDateTimeField`

All field classes accept the same arguments as their non-encrypted versions.

To create an encrypted version of some other custom field class, inherit from both `EncryptedField` and the other field class:

```py
from thelabdb.fields.fernet import EncryptedField
from somewhere import MyField

class MyEncryptedField(EncryptedField, MyField):
    pass
```

### Nullable fields

Nullable encrypted fields are allowed; a `None` value in Python is
translated to a real `NULL` in the database column. Note that this
trivially reveals the presence or absence of data in the column to an
attacker. If this is a problem for your case, avoid using a nullable
encrypted field; instead store some other sentinel \"empty\" value
(which will be encrypted just like any other value) in a non-nullable
encrypted field.

## Keys

By default your `SECRET_KEY` setting is used as the encryption key.

You can instead provide a list of keys in the `FERNET_KEYS` setting; the
first key will be used to encrypt all new data, and decryption of
existing values will be attempted with all given keys in order. This is
useful for key rotation: place a new key at the head of the list for use
with all new or changed data, but existing values encrypted with old
keys will still be accessible:

```py
FERNET_KEYS = [
    'new key for encrypting',
    'older key for decrypting old data',
]
```

!!! warning

    Once you start saving data using a given encryption key (whether your `SECRET_KEY` or another key), don't lose track of that key or you will lose access to all data encrypted using it! And keep the key secret; anyone who gets ahold of it will have access to all your encrypted data.

### Disabling HKDF

Fernet encryption requires a 32-bit url-safe base-64 encoded secret key. By default, `django-fernet-fields` uses [HKDF][HKDF] to derive such a key from whatever arbitrary secret key you provide.

[HKDF]: https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#cryptography.hazmat.primitives.kdf.hkdf.HKDF

If you wish to disable HKDF and provide your own Fernet-compatible 32-bit key(s) (e.g. generated with
[Fernet.generate_key()][generate_key]) directly instead, just set `FERNET_USE_HKDF = False` in your settings file. If this is set, all keys specified in the `FERNET_KEYS` setting must be 32-bit and url-safe base64-encoded bytestrings. If a key is not in the correct format, you\'ll likely get \"incorrect padding\" errors.

[generate_key]: https://cryptography.io/en/latest/fernet/#cryptography.fernet.Fernet.generate_key

!!! warning

If you don't define a `FERNET_KEYS` setting, your `SECRET_KEY` setting is the fallback key. If you disable HKDF, this means that your `SECRET_KEY` itself needs to be a Fernet-compatible key.

## Indexes, Constraints, and Lookups

Because Fernet encryption is not deterministic (the same source text encrypted using the same key will result in a different encrypted token each time), indexing or enforcing uniqueness or performing lookups against encrypted data is useless. Every encrypted value will always be different, and every exact-match lookup will fail; other lookup's results would be meaningless.

For this reason, `EncryptedField` will raise `django.core.exceptions.ImproperlyConfigured` if passed any of `db_index=True`, `unique=True`, or `primary_key=True`, and any type of lookup on an `EncryptedField` except for `isnull` will raise `django.core.exceptions.FieldError`.

## Ordering

Ordering a queryset by an `EncryptedField` will not raise an error, but
it will order according to the encrypted data, not the decrypted value,
which is not very useful and probably not desired.

Raising an error would be better, but there's no mechanism in Django
for a field class to declare that it doesn't support ordering. It could
be done easily enough with a custom queryset and model manager that
overrides `order_by()` to check the supplied field names. You might
consider doing this for your models, if you're concerned that you might
accidentally order by an `EncryptedField` and get junk ordering without
noticing.

## Migrations

If migrating an existing non-encrypted field to its encrypted
counterpart, you won't be able to use a simple `AlterField` operation.
Since your database has no access to the encryption key, it can't
update the column values correctly. Instead, you'll need to do a
three-step migration dance:

1.  Add the new encrypted field with a different name and initialize its
    values as `null`, otherwise decryption will be attempted
    before anything has been encrypted.
2.  Write a data migration (using RunPython and the ORM, not raw SQL) to
    copy the values from the old field to the new (which automatically
    encrypts them in the process).
3.  Remove the old field and (if needed) rename the new encrypted field
    to the old field's name.

## Reference

::: thelabdb.fields.fernet.EncryptedField
    :docstring:
