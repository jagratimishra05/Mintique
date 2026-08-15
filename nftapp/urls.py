from django.urls import path
from . import views

app_name = "nftapp"

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("mint/", views.mint_view, name="mint"),
    path("mint/batch/", views.batch_mint_view, name="batch_mint"),
    path("marketplace/", views.marketplace_view, name="marketplace"),
    path("collection/", views.my_collection_view, name="my_collection"),
    path("sell/", views.sell_view, name="sell"),
    path("sell/<int:pk>/list/", views.list_for_sale_view, name="list_for_sale"),
    path("sell/<int:pk>/unlist/", views.unlist_nft_view, name="unlist"),

    path("wishlist/", views.wishlist_view, name="wishlist"),
    path("favorites/", views.favorites_view, name="favorites"),
    path("recently-viewed/", views.recently_viewed_view, name="recently_viewed"),

    path("collections/", views.collection_list_view, name="collection_list"),
    path("collections/new/", views.create_collection_view, name="create_collection"),
    path("collections/<slug:slug>/", views.collection_detail_view, name="collection_detail"),

    path("creator/<str:username>/", views.creator_profile_view, name="creator_profile"),

    path("contract/abi/", views.contract_abi_view, name="contract_abi"),

    path("<int:pk>/", views.nft_detail_view, name="nft_detail"),
    path("<int:pk>/confirm-mint/", views.confirm_onchain_mint_view, name="confirm_onchain_mint"),
    path("<int:pk>/certificate/", views.certificate_view, name="certificate"),
    path("<int:pk>/certificate/download/", views.certificate_pdf_view, name="certificate_download"),
    path("<int:pk>/like/", views.toggle_like_view, name="toggle_like"),
    path("<int:pk>/wishlist/", views.toggle_wishlist_view, name="toggle_wishlist"),
    path("<int:pk>/buy/", views.buy_nft_view, name="buy_nft"),
    path("<int:pk>/offer/", views.make_offer_view, name="make_offer"),
    path("offer/<int:offer_id>/cancel/", views.cancel_offer_view, name="cancel_offer"),
    path("offer/<int:offer_id>/accept/", views.accept_offer_view, name="accept_offer"),
    path("offer/<int:offer_id>/reject/", views.reject_offer_view, name="reject_offer"),
    path("<int:pk>/gift/", views.gift_nft_view, name="gift_nft"),
    path("<int:pk>/burn/", views.burn_nft_view, name="burn_nft"),
]
