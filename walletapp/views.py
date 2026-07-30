import json
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from nftapp import blockchain

from .forms import ConnectWalletForm, SwapForm
from .models import Transaction, Wallet


@login_required
@require_POST
def connect_wallet_view(request):
    """
    Called by wallet.js either after a real window.ethereum (MetaMask-style)
    connection, or the manual/demo fallback. Only ever invoked at the moment
    a wallet-gated action (mint/buy) is attempted.
    """
    form = ConnectWalletForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "error": "Invalid wallet address."}, status=400)

    address = form.cleaned_data["wallet_address"]
    user = request.user
    user.wallet_address = address
    user.wallet_connected_at = timezone.now()
    user.save(update_fields=["wallet_address", "wallet_connected_at"])

    Wallet.objects.get_or_create(user=user)
    Transaction.objects.create(
        user=user, tx_type=Transaction.TxType.WALLET_CONNECT,
        token="—", amount=0, note=f"Wallet connected: {address[:6]}...{address[-4:]}"
    )
    return JsonResponse({"ok": True, "address": address})


@login_required
def disconnect_wallet_view(request):
    request.user.wallet_address = None
    request.user.wallet_connected_at = None
    request.user.save(update_fields=["wallet_address", "wallet_connected_at"])
    messages.info(request, "Wallet disconnected.")
    return redirect(request.META.get("HTTP_REFERER", "nftapp:dashboard"))


@login_required
def onchain_balance_view(request):
    """Live on-chain POL/MATIC balance for the signed-in user's connected
    wallet, via nftapp.blockchain's read-only RPC lookup. Kept deliberately
    separate from Wallet's simulated ledger balances above — this reflects
    what the address actually holds on Polygon, not Mintique's internal
    demo balances. Always returns 200 with ok:False rather than erroring,
    so the frontend can just hide the balance when it's unavailable.
    """
    address = request.user.wallet_address
    if not address:
        return JsonResponse({"ok": False, "error": "No wallet connected."})

    balance = blockchain.get_native_balance(address)
    if balance is None:
        return JsonResponse({"ok": False, "error": "Could not reach the Polygon network."})

    currency = settings.POLYGON_ACTIVE_NETWORK["currency"]
    return JsonResponse({
        "ok": True,
        "balance": balance,
        "symbol": currency["symbol"],
        "network": settings.POLYGON_ACTIVE_NETWORK["name"],
    })


def _decimal_rates():
    """settings.CRYPTO_RATES_PER_ETH as Decimals, keyed by token symbol —
    each value is 'how many units of this token equal 1 ETH'."""
    return {token: Decimal(str(rate)) for token, rate in settings.CRYPTO_RATES_PER_ETH.items()}


@login_required
def swap_view(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    rates = _decimal_rates()
    fee_pct = Decimal(str(settings.SWAP_FEE_PERCENT)) / Decimal("100")

    if request.method == "POST":
        form = SwapForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data["amount"]
            from_token = form.cleaned_data["from_token"]
            to_token = form.cleaned_data["to_token"]

            with transaction.atomic():
                wallet.refresh_from_db()
                balance = wallet.get_balance(from_token)
                if balance is None:
                    messages.error(request, "Unsupported currency.")
                    return redirect("walletapp:swap")
                if amount > balance:
                    messages.error(request, f"Insufficient {from_token} balance.")
                    return redirect("walletapp:swap")

                # Convert via ETH as the common base: amount_in_eth = amount / rate[from]
                amount_in_eth = amount / rates[from_token]
                received = (amount_in_eth * rates[to_token]) * (1 - fee_pct)

                wallet.set_balance(from_token, balance - amount)
                wallet.set_balance(to_token, wallet.get_balance(to_token) + received)
                note = f"Swapped {amount} {from_token} → {received:.6f} {to_token}"

                wallet.save(update_fields=[Wallet.BALANCE_FIELDS[from_token], Wallet.BALANCE_FIELDS[to_token]])
                Transaction.objects.create(
                    user=request.user, tx_type=Transaction.TxType.SWAP,
                    token=to_token, amount=amount, note=note,
                )
            messages.success(request, note)
            return redirect("walletapp:swap")
    else:
        form = SwapForm(initial={"from_token": "ETH", "to_token": "MNQ"})

    recent_txs = Transaction.objects.filter(user=request.user)[:10]
    balances = {token: wallet.get_balance(token) for token in Wallet.BALANCE_FIELDS}
    token_rows = [
        {"symbol": symbol, "label": meta["label"], "icon": meta["icon"], "balance": balances[symbol]}
        for symbol, meta in settings.CRYPTO_TOKENS.items()
    ]
    return render(request, "walletapp/swap.html", {
        "wallet": wallet, "form": form,
        "token_rows": token_rows,
        "rates_json": json.dumps({t: float(r) for t, r in rates.items()}),
        "balances_json": json.dumps({t: float(v) for t, v in balances.items()}),
        "fee_percent": settings.SWAP_FEE_PERCENT, "recent_txs": recent_txs,
    })


@login_required
def transactions_view(request):
    txs = Transaction.objects.filter(user=request.user)
    return render(request, "walletapp/transactions.html", {"txs": txs})
