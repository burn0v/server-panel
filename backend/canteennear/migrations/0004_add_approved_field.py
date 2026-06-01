"""Add approved field to Review model.

Generated manually to keep repository in sync.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("canteennear", "0003_remove_canteen_city"),
    ]

    operations = [
        migrations.AddField(
            model_name="review",
            name="approved",
            field=models.BooleanField(default=False),
        ),
    ]
