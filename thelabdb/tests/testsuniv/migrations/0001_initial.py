# Generated by Django 4.2.6 on 2023-11-02 12:54

from django.db import migrations, models

import thelabdb.fields.fernet


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="EncryptedChar",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("value", thelabdb.fields.fernet.EncryptedCharField(max_length=25)),
            ],
        ),
        migrations.CreateModel(
            name="EncryptedDate",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("value", thelabdb.fields.fernet.EncryptedDateField()),
            ],
        ),
        migrations.CreateModel(
            name="EncryptedDateTime",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("value", thelabdb.fields.fernet.EncryptedDateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="EncryptedEmail",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("value", thelabdb.fields.fernet.EncryptedEmailField(max_length=254)),
            ],
        ),
        migrations.CreateModel(
            name="EncryptedInt",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("value", thelabdb.fields.fernet.EncryptedIntegerField()),
            ],
        ),
        migrations.CreateModel(
            name="EncryptedNullable",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("value", thelabdb.fields.fernet.EncryptedIntegerField(null=True)),
            ],
        ),
        migrations.CreateModel(
            name="EncryptedText",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("value", thelabdb.fields.fernet.EncryptedTextField()),
            ],
        ),
    ]
