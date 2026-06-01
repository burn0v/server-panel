# Generated manually for APIKey model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("canteennear", "0005_remove_canteen_menu"),
    ]

    operations = [
        migrations.CreateModel(
            name="APIKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(default=True)),
                ("user", models.ForeignKey(on_delete=models.CASCADE, related_name="api_keys", to="auth.user")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
