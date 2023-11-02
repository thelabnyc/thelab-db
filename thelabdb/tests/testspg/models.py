from django.db import models

from thelabdb.pgviews import view


class TestModel(models.Model):
    """Test model with some basic data for running migrate tests against."""

    name = models.CharField(max_length=100)


class Superusers(view.View):
    projection = ["auth.User.*"]
    sql = """SELECT * FROM auth_user WHERE is_superuser = TRUE;"""


class SimpleUser(view.View):
    projection = ["auth.User.username", "auth.User.password"]
    # The row_number() window function is needed so that Django sees some kind
    # of 'id' field. We could also grab the one from `auth.User`, but this
    # seemed like more fun :)
    sql = """
    SELECT
        username,
        password,
        row_number() OVER () AS id
    FROM auth_user;"""


class RelatedView(view.ReadOnlyView):
    sql = """SELECT id AS model_id, id FROM {}""".format(TestModel._meta.db_table)
    model = models.ForeignKey(TestModel, on_delete=models.CASCADE)


class MaterializedRelatedView(view.ReadOnlyMaterializedView):
    sql = """SELECT id AS model_id, id FROM {}""".format(TestModel._meta.db_table)
    model = models.ForeignKey(TestModel, on_delete=models.DO_NOTHING)


class DependantView(view.ReadOnlyView):
    dependencies = ("testspg.RelatedView",)
    sql = """SELECT model_id from {};""".format(RelatedView._meta.db_table)


class DependantMaterializedView(view.ReadOnlyMaterializedView):
    dependencies = ("testspg.MaterializedRelatedView",)
    sql = """SELECT model_id from {};""".format(MaterializedRelatedView._meta.db_table)


class MaterializedRelatedViewWithIndex(view.ReadOnlyMaterializedView):
    concurrent_index = "id"
    sql = """SELECT id AS model_id, id FROM {}""".format(TestModel._meta.db_table)
    model = models.ForeignKey(TestModel, on_delete=models.DO_NOTHING)


class CustomSchemaView(view.ReadOnlyView):
    sql = """SELECT id AS model_id, id FROM {}""".format(TestModel._meta.db_table)
    model = models.ForeignKey(TestModel, on_delete=models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = "test_schema.my_custom_view"
