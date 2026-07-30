from django.urls import path
from . import views

app_name = "walletapp"

urlpatterns = [
    path("connect/", views.connect_wallet_view, name="connect"),
    path("disconnect/", views.disconnect_wallet_view, name="disconnect"),
    path("balance/", views.onchain_balance_view, name="onchain_balance"),
    path("swap/", views.swap_view, name="swap"),
    path("transactions/", views.transactions_view, name="transactions"),
]
