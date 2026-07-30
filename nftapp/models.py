import hashlib

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


def nft_upload_path(instance, filename):
    return f"nfts/{instance.owner_id}/{filename}"


def compute_asset_hash(file_obj):
    """SHA-256 of the actual uploaded file's bytes.

    This is the real "is this the same asset" fingerprint. Used both to
    stamp `NFT.content_hash` at mint time and, before that, by
    `nftapp.forms` to check for an existing, non-burned NFT already
    minted from the identical file.

    Reads in chunks so large uploads (up to the 50MB cap enforced in
    forms.py / ipfs_utils.py) don't need to be pulled fully into memory at
    once, and always seeks back to 0 afterward so the caller's later read
    of the file (form save, IPFS pin, etc.) isn't affected.
    """
    file_obj.seek(0)
    h = hashlib.sha256()
    chunks = file_obj.chunks() if hasattr(file_obj, "chunks") else iter([file_obj.read()])
    for chunk in chunks:
        h.update(chunk)
    file_obj.seek(0)
    return h.hexdigest()


class Category(models.TextChoices):
    ART = "art", "Digital Art"
    PHOTOGRAPHY = "photography", "Photography"
    MUSIC = "music", "Music"
    COLLECTIBLE = "collectible", "Collectible"
    VIDEO = "video", "Video"
    OTHER = "other", "Other"


class MintStatus(models.TextChoices):
    """Where an NFT sits in the on-chain (Polygon) minting lifecycle. Every
    existing/legacy row defaults to OFFCHAIN — Mintique's original
    simulated ledger — and only moves to PENDING/CONFIRMED once a real
    ERC-721 contract is configured (settings.NFT_CONTRACT_ADDRESS) and the
    creator's MetaMask wallet actually signs the mint transaction."""
    OFFCHAIN = "offchain", "Off-chain (simulated)"
    PENDING = "pending", "Pending on-chain confirmation"
    CONFIRMED = "confirmed", "Confirmed on Polygon"
    FAILED = "failed", "On-chain mint failed"


class TokenStandard(models.TextChoices):
    """Which token-contract family a given NFT was (or will be) minted
    under. ERC-721 is the only standard actually implemented/deployed
    today (contracts/MintiqueNFT.sol); the others are declared here so
    the rest of the backend — the contract registry in
    nftapp.blockchain, the metadata builder in nftapp.ipfs_utils, and
    this model's own `standard_metadata` field — already has a place to
    route standard-specific behavior the moment a matching contract
    (e.g. contracts/MintiqueNFT1155.sol) is deployed, with zero schema
    changes required at that point.
    """
    ERC721 = "erc721", "ERC-721 — single edition"
    ERC1155 = "erc1155", "ERC-1155 — multi-token / editions"
    ERC4907 = "erc4907", "ERC-4907 — rentable (extends ERC-721)"
    ERC5192 = "erc5192", "ERC-5192 — soulbound (extends ERC-721)"


class Network(models.TextChoices):
    """Human-readable chain identifier stored alongside chain_id, so the
    database record is self-describing without a settings lookup (and
    keeps working correctly even if a mint happened on a network the
    site's *current* POLYGON_NETWORK setting has since moved away from)."""
    POLYGON_AMOY = "polygon-amoy", "Polygon Amoy (testnet)"
    POLYGON_MAINNET = "polygon-mainnet", "Polygon Mainnet"


class Currency(models.TextChoices):
    """Which currency an NFT's price is denominated in. Mirrors the token
    symbols already supported by walletapp.models.Wallet.BALANCE_FIELDS so
    a listing can be priced/settled in whichever the creator picks."""
    ETH = "ETH", "ETH — Ethereum"
    MNQ = "MNQ", "MNQ — Mintique Token"


def collection_cover_path(instance, filename):
    return f"collections/{instance.owner_id}/cover_{filename}"


def collection_banner_path(instance, filename):
    return f"collections/{instance.owner_id}/banner_{filename}"


class Collection(models.Model):
    """Groups NFTs from the same creator into a named collection —
    mirrors the way individual NFTs already track ownership, so a
    collection is just an organizing/branding layer on top of the
    existing NFT model rather than a parallel ownership system.
    """
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="collections")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField(blank=True)
    cover_image = models.ImageField(upload_to=collection_cover_path, blank=True, null=True)
    banner_image = models.ImageField(upload_to=collection_banner_path, blank=True, null=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.ART)

    # Collection-level verification (distinct from creator verification —
    # a verified creator can still have an unverified collection pending
    # review, e.g. a new drop).
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:160] or "collection"
            slug = base
            n = 1
            while Collection.objects.filter(slug=slug).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("nftapp:collection_detail", args=[self.slug])

    @property
    def nft_count(self):
        return self.nfts.count()

    @property
    def floor_price(self):
        listed = self.nfts.filter(is_listed=True, is_burned=False).order_by("price")
        return listed.first().price if listed.exists() else None


class NFT(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="nfts")
    # The account that originally minted this NFT. Distinct from `owner`,
    # which changes on every resale/gift — `creator` never changes, and is
    # what royalty payouts on resale are credited to. Nullable/blank so
    # existing rows (and any future creator_name-only imports) degrade
    # gracefully rather than breaking.
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="created_nfts"
    )
    creator_name = models.CharField(max_length=100)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to=nft_upload_path)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.ART)
    price = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    currency = models.CharField(max_length=6, choices=Currency.choices, default=Currency.ETH)

    collection = models.ForeignKey(
        Collection, on_delete=models.SET_NULL, blank=True, null=True, related_name="nfts"
    )

    # Creator royalty — percentage of every resale price paid back to the
    # original creator. Enforced wherever a sale/gift transfer is processed.
    royalty_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    # Lazy minting: metadata + hash exist immediately (row is created), but
    # the NFT isn't "minted" on-chain until it's actually bought/claimed —
    # this flag plus lazy_minted_at track that pending state.
    is_lazy_minted = models.BooleanField(default=False)
    lazy_minted_at = models.DateTimeField(blank=True, null=True)

    is_burned = models.BooleanField(default=False)
    burned_at = models.DateTimeField(blank=True, null=True)

    content_hash = models.CharField(max_length=64, editable=False, blank=True)

    is_listed = models.BooleanField(default=True)
    likes = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    # --- IPFS storage (nftapp.ipfs_utils) -----------------------------
    # CIDs of the artwork and its metadata JSON once pinned to IPFS. Blank
    # until IPFS is configured (settings.IPFS_ENABLED) and a mint pins them.
    ipfs_image_cid = models.CharField(max_length=100, blank=True)
    ipfs_metadata_cid = models.CharField(max_length=100, blank=True)

    # --- Polygon / ERC-721 on-chain mint (nftapp.blockchain) ----------
    mint_status = models.CharField(max_length=12, choices=MintStatus.choices, default=MintStatus.OFFCHAIN)
    mint_error = models.CharField(
        max_length=255, blank=True,
        help_text="Last IPFS/on-chain error message, if mint_status is offchain/pending due to a failure.",
    )
    token_standard = models.CharField(
        max_length=10, choices=TokenStandard.choices, default=TokenStandard.ERC721,
        help_text="Which token contract family this NFT is minted under. See TokenStandard for the "
                   "extensibility rationale.",
    )
    contract_address = models.CharField(max_length=42, blank=True)
    network = models.CharField(
        max_length=20, choices=Network.choices, blank=True,
        help_text="Chain the mint was (or will be) confirmed on — set from settings.POLYGON_NETWORK at "
                   "mint time so it stays accurate even if the site's active network later changes.",
    )
    chain_id = models.PositiveIntegerField(blank=True, null=True)
    onchain_token_id = models.PositiveBigIntegerField(blank=True, null=True)
    polygon_tx_hash = models.CharField(max_length=66, blank=True)
    minter_wallet_address = models.CharField(max_length=42, blank=True)
    minted_at = models.DateTimeField(
        blank=True, null=True,
        help_text="When the mint transaction was confirmed on-chain (distinct from created_at, which is "
                   "when the off-chain database row was first created).",
    )

    # Full ipfs:// URIs (as opposed to the bare CIDs below), stored
    # verbatim at pin time so a caller never has to reconstruct them from
    # a CID + gateway guess.
    image_uri = models.CharField(max_length=255, blank=True, help_text="ipfs://<CID> of the pinned artwork.")
    metadata_uri = models.CharField(
        max_length=255, blank=True, help_text="ipfs://<CID> of the pinned ERC-721 metadata JSON — this is "
                                               "exactly what the contract's tokenURI(tokenId) resolves to."
    )

    # --- Forward-compatible standard-specific state --------------------
    # Kept as a single flag + JSON blob rather than a wide set of
    # nullable columns per standard, so ERC-4907 (rentable: user address +
    # expiry) and ERC-5192 (soulbound: usually just a boolean, but some
    # implementations track a lock reason) can both be supported without
    # another migration — the concrete shape is validated in code
    # (nftapp.blockchain) at the point a given standard is actually wired
    # up, not enforced at the database level.
    is_soulbound = models.BooleanField(
        default=False, help_text="ERC-5192 — if set, this token is non-transferable once minted."
    )
    standard_metadata = models.JSONField(
        default=dict, blank=True,
        help_text="Standard-specific extra state, e.g. {'rental_user': '0x..', 'rental_expires': ..} for "
                   "ERC-4907, or {'supply': N} for ERC-1155.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # An on-chain tokenId is only unique *within one contract on
            # one chain* (ERC-721's own guarantee, enforced by
            # `_nextTokenId++` in MintiqueNFT.sol) — not globally, since a
            # second standard/contract (see TokenStandard /
            # CONTRACT_REGISTRY) would legitimately reuse tokenId 0, 1, 2...
            # on its own address. This mirrors that scoping at the DB
            # level so two Mintique rows can never claim the same minted
            # token, while still leaving every OFFCHAIN/PENDING row (where
            # onchain_token_id is still NULL) unconstrained.
            models.UniqueConstraint(
                fields=["contract_address", "chain_id", "onchain_token_id"],
                condition=Q(onchain_token_id__isnull=False),
                name="unique_onchain_token_per_contract_chain",
            ),
            # A given on-chain transaction hash can only ever confirm one
            # mint — this stops the same tx_hash from being replayed onto
            # a second NFT row (e.g. two PENDING rows owned by the same
            # user both being confirmed with one real transaction).
            models.UniqueConstraint(
                fields=["polygon_tx_hash"],
                condition=~Q(polygon_tx_hash=""),
                name="unique_polygon_tx_hash",
            ),
        ]

    def __str__(self):
        return f"{self.name} (#{self.onchain_token_id})" if self.onchain_token_id is not None else self.name

    def save(self, *args, **kwargs):
        if not self.content_hash and self.image:
            self.content_hash = compute_asset_hash(self.image)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("nftapp:nft_detail", args=[self.pk])

    @property
    def token_id_display(self):
        """The NFT's real, ERC-721-standard token ID — sourced entirely
        from the smart contract (`MintiqueNFT.sol`'s auto-incrementing
        `_nextTokenId`, captured into `onchain_token_id` when the mint
        transaction is verified — see `blockchain.verify_mint_transaction`
        and `views.confirm_onchain_mint_view`).

        Deliberately not a locally-generated UUID or database row number:
        per the ERC-721 standard, a token's ID doesn't exist until
        `_safeMint` actually assigns it on-chain, so there is nothing
        truthful to show before that point. Returns None (render "Pending
        on-chain mint" or similar in templates) until then.
        """
        return self.onchain_token_id

    @property
    def is_verified(self):
        """True if the current owner is a verified creator OR this NFT
        belongs to a verified collection. Replaces the old hardcoded
        checkmark badge that every template showed unconditionally."""
        if self.owner_id and getattr(self.owner, "is_verified_creator", False):
            return True
        if self.collection_id and getattr(self.collection, "is_verified", False):
            return True
        return False

    @property
    def ipfs_image_url(self):
        from . import ipfs_utils
        return ipfs_utils.gateway_url(self.ipfs_image_cid)

    @property
    def ipfs_metadata_url(self):
        from . import ipfs_utils
        return ipfs_utils.gateway_url(self.ipfs_metadata_cid)

    @property
    def polygon_explorer_url(self):
        from . import blockchain
        return blockchain.explorer_tx_url(self.polygon_tx_hash)


class NFTAttribute(models.Model):
    """A single property/trait shown on the item page as a chip, e.g.
    ("Background", "Cosmic Purple"). Mirrors the `attributes` array in
    ERC-721 metadata JSON so these round-trip cleanly with ipfs_utils'
    metadata builder — this is purely the display/query side of that
    same data.
    """
    nft = models.ForeignKey(NFT, on_delete=models.CASCADE, related_name="attributes")
    trait_type = models.CharField(max_length=50)
    value = models.CharField(max_length=100)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.trait_type}: {self.value}"

    @property
    def rarity_percent(self):
        """% of listed/unburned NFTs sharing this exact trait_type+value —
        the same "N% have this trait" stat OpenSea shows on trait chips."""
        total = NFT.objects.filter(is_burned=False).count()
        if not total:
            return None
        matching = NFTAttribute.objects.filter(
            trait_type=self.trait_type, value=self.value, nft__is_burned=False
        ).count()
        return round((matching / total) * 100, 1)


class Offer(models.Model):
    """A buyer's standing offer to purchase an NFT below (or at) its list
    price — the OpenSea-style alternative to an outright Buy Now. Funds
    aren't escrowed when the offer is made (this platform's wallet is a
    simulated internal ledger, not on-chain WETH allowance); the bidder's
    balance is instead checked at the moment the owner accepts, same as
    a real marketplace re-validating a wallet's allowance right before
    settlement.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Declined"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    nft = models.ForeignKey(NFT, on_delete=models.CASCADE, related_name="offers")
    bidder = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="offers_made")
    amount = models.DecimalField(max_digits=12, decimal_places=4)
    currency = models.CharField(max_length=6, choices=Currency.choices, default=Currency.ETH)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-amount", "-created_at"]

    def __str__(self):
        return f"{self.amount} {self.currency} on {self.nft_id} by {self.bidder_id}"

    @property
    def is_expired(self):
        return self.status == self.Status.PENDING and self.expires_at <= timezone.now()


class Like(models.Model):

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nft = models.ForeignKey(NFT, on_delete=models.CASCADE, related_name="like_set")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "nft"]


class Wishlist(models.Model):
    """Distinct from Like (a public, lightweight 'favorite' heart that
    already exists): a Wishlist entry signals purchase intent and is
    surfaced separately in the user's dashboard ('items you want to buy')
    rather than as a generic favorites feed."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    nft = models.ForeignKey(NFT, on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "nft"]
        ordering = ["-created_at"]


class RecentlyViewed(models.Model):
    """One row per (user, nft); updated_at bumped on every view so a
    simple ordering gives the user's most-recently-viewed NFTs without
    unbounded row growth per view."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recently_viewed")
    nft = models.ForeignKey(NFT, on_delete=models.CASCADE, related_name="viewed_by")
    viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "nft"]
        ordering = ["-viewed_at"]
