from django.contrib import admin
from .models import NFT, Collection, Like, NFTAttribute, Offer, RecentlyViewed, Wishlist


class NFTAttributeInline(admin.TabularInline):
    model = NFTAttribute
    extra = 1


@admin.register(NFT)
class NFTAdmin(admin.ModelAdmin):
    list_display = [
        "name", "onchain_token_id", "owner", "collection", "category", "price",
        "token_standard", "mint_status", "network", "is_listed", "is_lazy_minted",
        "is_burned", "likes", "created_at",
    ]
    list_filter = ["category", "token_standard", "mint_status", "network", "is_listed", "is_lazy_minted",
                    "is_burned", "collection"]
    search_fields = ["name", "creator_name", "owner__email", "polygon_tx_hash", "contract_address"]
    readonly_fields = [
        "content_hash", "created_at", "minted_at",
        "ipfs_image_cid", "ipfs_metadata_cid", "image_uri", "metadata_uri",
        "onchain_token_id", "polygon_tx_hash", "contract_address", "mint_error",
    ]
    inlines = [NFTAttributeInline]


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "category", "is_verified", "nft_count", "created_at"]
    list_filter = ["category", "is_verified"]
    search_fields = ["name", "slug", "owner__email"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ["nft", "bidder", "amount", "currency", "status", "created_at", "expires_at"]
    list_filter = ["status", "currency"]
    search_fields = ["nft__name", "bidder__email"]


admin.site.register(Like)
admin.site.register(Wishlist)
admin.site.register(RecentlyViewed)
