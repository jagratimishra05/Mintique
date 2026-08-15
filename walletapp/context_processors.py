from .models import Wallet


def wallet_context(request):
    if request.user.is_authenticated:
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        return {"nav_wallet": wallet}
    return {"nav_wallet": None}
