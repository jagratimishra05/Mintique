from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nftapp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='nft',
            name='views',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
