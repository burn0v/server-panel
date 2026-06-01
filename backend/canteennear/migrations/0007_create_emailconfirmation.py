# Generated manually for EmailConfirmation model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("canteennear", "0006_create_apikey"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailConfirmation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(default=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="email_confirmations", to="auth.user")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
