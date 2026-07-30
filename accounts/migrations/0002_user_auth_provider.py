# Generated manually to add multi-method auth support (Email / Google / Wallet)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='auth_provider',
            field=models.CharField(
                choices=[('email', 'Email'), ('google', 'Google'), ('wallet', 'Wallet')],
                default='email',
                max_length=20,
            ),
        ),
    ]
