# Generated manually for Mintique multi-currency wallet support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('walletapp', '0003_alter_transaction_tx_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallet',
            name='btc_balance',
            field=models.DecimalField(decimal_places=8, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='wallet',
            name='usdt_balance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='wallet',
            name='usdc_balance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='wallet',
            name='sol_balance',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=18),
        ),
    ]
