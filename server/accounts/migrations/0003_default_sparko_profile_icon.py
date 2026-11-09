from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_profile_icon"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="profile_icon",
            field=models.CharField(
                choices=[
                    ("sparkle", "Star"),
                    ("sparko", "Sparko"),
                    ("flower", "Flower"),
                    ("heart", "Heart"),
                ],
                default="sparko",
                max_length=32,
            ),
        ),
    ]
