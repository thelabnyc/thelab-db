from django.db import models

import thelabdb.fields


class EncryptedText(models.Model):
    value = thelabdb.fields.EncryptedTextField()


class EncryptedChar(models.Model):
    value = thelabdb.fields.EncryptedCharField(max_length=25)


class EncryptedEmail(models.Model):
    value = thelabdb.fields.EncryptedEmailField()


class EncryptedInt(models.Model):
    value = thelabdb.fields.EncryptedIntegerField()


class EncryptedDate(models.Model):
    value = thelabdb.fields.EncryptedDateField()


class EncryptedDateTime(models.Model):
    value = thelabdb.fields.EncryptedDateTimeField()


class EncryptedNullable(models.Model):
    value = thelabdb.fields.EncryptedIntegerField(null=True)
