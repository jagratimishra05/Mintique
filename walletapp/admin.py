from django.contrib import admin
from .models import Transaction, Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ["user", "eth_balance", "mnq_balance", "btc_balance", "usdt_balance", "usdc_balance", "sol_balance", "updated_at"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["user", "tx_type", "token", "amount", "tx_hash", "created_at"]
    list_filter = ["tx_type", "token"]
    search_fields = ["user__email", "tx_hash"]
