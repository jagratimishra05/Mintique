import uuid

from django.conf import settings
from django.db import models


class Wallet(models.Model):
    """Internal ledger wallet. Holds a simulated balance for ETH plus the
    platform's own MNQ token and a handful of other popular cryptocurrencies
    — this is what powers the multi-currency swap feature and lets buy/sell
    work without needing a real blockchain connection.

    NFT purchases themselves are still always settled in ETH (see
    nftapp.views.buy_nft_view); the other balances exist so a user can hold
    and swap between multiple coins, then convert into ETH when they're
    ready to buy.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ledger_wallet")
    eth_balance = models.DecimalField(max_digits=18, decimal_places=6, default=5)  # demo starting balance
    mnq_balance = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    btc_balance = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    usdt_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    usdc_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    sol_balance = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    # Maps a token symbol to the Wallet field that stores its balance. Kept
    # as a single source of truth so the swap view/forms/templates never
    # need a hardcoded if/elif per currency — add a new token by adding one
    # field above and one entry here.
    BALANCE_FIELDS = {
        "ETH": "eth_balance",
        "MNQ": "mnq_balance",
        "BTC": "btc_balance",
        "USDT": "usdt_balance",
        "USDC": "usdc_balance",
        "SOL": "sol_balance",
    }

    def __str__(self):
        return f"{self.user.email} — {self.eth_balance} ETH / {self.mnq_balance} MNQ"

    def get_balance(self, token):
        field = self.BALANCE_FIELDS.get(token.upper())
        return getattr(self, field) if field else None

    def set_balance(self, token, value):
        field = self.BALANCE_FIELDS.get(token.upper())
        if field:
            setattr(self, field, value)
        return field


class Transaction(models.Model):
    class TxType(models.TextChoices):
        MINT = "mint", "Mint"
        BUY = "buy", "Buy"
        SELL = "sell", "Sell"
        SWAP = "swap", "Swap"
        WALLET_CONNECT = "connect", "Wallet Connected"
        GIFT = "gift", "Gift"
        BURN = "burn", "Burn"
        ROYALTY = "royalty", "Creator Royalty"
        OFFER = "offer", "Offer"
        LIST = "list", "Listed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions")
    # Which NFT this transaction is about, if any (mint/buy/sell/gift/burn/
    # offer/list all are). Nullable because swap/wallet-connect aren't tied
    # to any single NFT. This is what powers each item's public Activity
    # tab: Transaction.objects.filter(nft=nft) is the whole timeline, no
    # separate activity-log table needed.
    nft = models.ForeignKey(
        "nftapp.NFT", on_delete=models.SET_NULL, blank=True, null=True, related_name="activity"
    )
    tx_type = models.CharField(max_length=10, choices=TxType.choices)
    token = models.CharField(max_length=10, default="ETH")
    amount = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    note = models.CharField(max_length=255, blank=True)
    tx_hash = models.CharField(max_length=66, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.tx_hash:
            self.tx_hash = "0x" + uuid.uuid4().hex + uuid.uuid4().hex[:24]
        super().save(*args, **kwargs)
