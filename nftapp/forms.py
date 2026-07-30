from django import forms

from accounts.validators import validate_deliverable_email

from .models import NFT, Category, Collection, Currency, Offer, compute_asset_hash


class ListForSaleForm(forms.ModelForm):
    """Minimal form used from the 'Sell NFTs' dashboard page to put an
    already-minted, owned NFT up for sale (or update its listing price)."""

    class Meta:
        model = NFT
        fields = ["price", "currency"]
        widgets = {
            "price": forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.0001", "min": "0.0001"}),
        }

    def clean_price(self):
        price = self.cleaned_data.get("price") or 0
        if price <= 0:
            raise forms.ValidationError("Set a price greater than zero to list this NFT for sale.")
        return price


class ContactForm(forms.Form):
    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "Ada Lovelace"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"placeholder": "you@email.com"}),
    )
    subject = forms.ChoiceField(
        choices=[
            ("general", "General question"),
            ("support", "Account / technical support"),
            ("partnership", "Partnership or press"),
            ("bug", "Report a bug"),
        ],
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 6, "placeholder": "How can we help?"}),
        min_length=10,
    )

    def clean_email(self):
        from accounts.validators import validate_deliverable_email

        email = self.cleaned_data["email"].strip().lower()
        validate_deliverable_email(email)
        return email

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        validate_deliverable_email(email)
        return email


def validate_nft_image(image):
    """Shared image validation used by both single and batch mint forms —
    kept as one function so the rules can't drift between the two flows."""
    max_size_mb = 50
    if image.size > max_size_mb * 1024 * 1024:
        raise forms.ValidationError(f"File too large ({image.name}). Max size is {max_size_mb}MB.")
    valid_types = ["image/png", "image/jpeg", "image/gif", "image/svg+xml", "image/webp"]
    if image.content_type not in valid_types:
        raise forms.ValidationError(f"Unsupported file type for {image.name}. Use PNG, JPG, GIF, SVG or WebP.")
    return image


def check_duplicate_asset(asset_hash, user, exclude_hashes=()):
    """Raise a ValidationError if `user` has already minted a non-burned
    NFT from the exact same file (by SHA-256 of its bytes — see
    models.compute_asset_hash).

    Scoped to the uploading user rather than globally: two different
    creators coincidentally uploading byte-identical stock art isn't
    necessarily a problem this platform needs to police, but the same
    creator minting their own asset twice almost always is (accidental
    double-submit, or an attempt to mint multiple "unique" NFTs from one
    underlying file). `exclude_hashes` lets a batch check for
    within-batch duplicates too, before anything is even saved.
    """
    if asset_hash in exclude_hashes:
        raise forms.ValidationError(
            "This file appears more than once in this upload — each NFT must be minted from a distinct asset."
        )
    if user is not None and getattr(user, "is_authenticated", False):
        if NFT.objects.filter(owner=user, content_hash=asset_hash, is_burned=False).exists():
            raise forms.ValidationError(
                "You've already minted an NFT from this exact file. Duplicate minting of the same asset "
                "isn't allowed — upload a different file, or manage your existing NFT from My Collection."
            )


class _OwnerScopedCollectionMixin:
    """Shared by every form that lets a user pick one of their own
    collections — scopes the queryset to `user` and adds a friendly
    'No collection' first choice."""
    def _scope_collection_field(self, user):
        field = self.fields.get("collection")
        if field is None:
            return
        if user is not None and user.is_authenticated:
            field.queryset = Collection.objects.filter(owner=user)
        else:
            field.queryset = Collection.objects.none()
        field.required = False
        field.empty_label = "No collection"


class MintNFTForm(_OwnerScopedCollectionMixin, forms.ModelForm):
    class Meta:
        model = NFT
        fields = [
            "image", "name", "creator_name", "description", "category", "price", "currency",
            "collection", "royalty_percentage", "is_lazy_minted",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Cosmic Drift #001"}),
            "creator_name": forms.TextInput(attrs={"placeholder": "e.g. AstralArtist"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Tell the story behind your artwork..."}),
            "price": forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.0001", "min": "0"}),
            "royalty_percentage": forms.NumberInput(attrs={"placeholder": "0", "step": "0.5", "min": "0", "max": "100"}),
            "is_lazy_minted": forms.CheckboxInput(),
        }
        labels = {
            "is_lazy_minted": "Lazy mint (metadata created now, minted on-chain at first sale — saves gas)",
            "royalty_percentage": "Creator royalty on resale (%)",
            "currency": "Price currency",
        }

    traits = forms.CharField(
        required=False,
        label="Properties (optional)",
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "One per line, e.g.\nBackground: Cosmic Purple\nEyes: Laser\nRarity: Legendary",
        }),
        help_text="One trait per line as \"Type: Value\" — shown as property chips on the item page.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self._scope_collection_field(user)
        self.order_fields([f for f in self.fields if f != "traits"] + ["traits"])

    def clean_image(self):
        image = validate_nft_image(self.cleaned_data["image"])
        # Computed once here (from the raw upload) and reused by
        # nftapp.views.mint_view so the file's bytes aren't hashed twice —
        # this is the same hash NFT.save() would otherwise compute itself.
        self.asset_hash = compute_asset_hash(image)
        check_duplicate_asset(self.asset_hash, self.user)
        return image

    def clean_price(self):
        price = self.cleaned_data.get("price") or 0
        if price < 0:
            raise forms.ValidationError("Price cannot be negative.")
        return price

    def clean_traits(self):
        raw = self.cleaned_data.get("traits", "")
        pairs = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if ":" not in line:
                raise forms.ValidationError(f'Each line needs a "Type: Value" format — check "{line}".')
            trait_type, value = line.split(":", 1)
            trait_type, value = trait_type.strip(), value.strip()
            if not trait_type or not value:
                raise forms.ValidationError(f'Each line needs a "Type: Value" format — check "{line}".')
            pairs.append((trait_type[:50], value[:100]))
        return pairs


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Django's FileField only accepts a single file; this small, standard
    subclass (the pattern recommended in Django's own docs) lets one field
    accept several files while still running FileField's per-file
    validation on each one."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(d, initial) for d in data]
        return [single_file_clean(data, initial)]


class BatchMintForm(_OwnerScopedCollectionMixin, forms.Form):
    """Shared metadata for a batch of NFTs, minted from multiple images in
    one submission. Reuses NFT's own category/collection/royalty choices
    rather than redefining them."""
    images = MultipleFileField(help_text="Select up to 20 images. PNG, JPG, GIF, SVG or WebP, 50MB each.")
    name_prefix = forms.CharField(
        max_length=130,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Cosmic Drift"}),
        help_text="Each NFT is named '<prefix> #1', '<prefix> #2', ... in upload order.",
    )
    creator_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"placeholder": "e.g. AstralArtist"}))
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Applied to every NFT in this batch..."}),
    )
    category = forms.ChoiceField(choices=Category.choices)
    price = forms.DecimalField(max_digits=12, decimal_places=4, min_value=0,
                                widget=forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.0001", "min": "0"}))
    currency = forms.ChoiceField(choices=Currency.choices, initial=Currency.ETH, label="Price currency")
    collection = forms.ModelChoiceField(queryset=Collection.objects.none(), required=False)
    royalty_percentage = forms.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, initial=0,
        widget=forms.NumberInput(attrs={"placeholder": "0", "step": "0.5", "min": "0", "max": "100"}),
    )
    is_lazy_minted = forms.BooleanField(required=False, label="Lazy mint the whole batch")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self._scope_collection_field(user)

    def clean_images(self):
        images = self.cleaned_data["images"]
        if not images:
            raise forms.ValidationError("Select at least one image.")
        if len(images) > 20:
            raise forms.ValidationError("Batch mint is limited to 20 images at a time.")
        # Computed once here and reused by nftapp.views.batch_mint_view (in
        # the same order as `images`) so each file's bytes aren't hashed
        # twice, and so a duplicate *within this same batch* is caught
        # before any of it is saved — not just duplicates against
        # previously-minted NFTs.
        self.asset_hashes = []
        for image in images:
            validate_nft_image(image)
            asset_hash = compute_asset_hash(image)
            check_duplicate_asset(asset_hash, self.user, exclude_hashes=self.asset_hashes)
            self.asset_hashes.append(asset_hash)
        return images


class GiftNFTForm(forms.Form):
    recipient_email = forms.EmailField(
        label="Recipient's email",
        widget=forms.EmailInput(attrs={"placeholder": "friend@email.com"}),
    )

    def __init__(self, *args, sender=None, **kwargs):
        self.sender = sender
        super().__init__(*args, **kwargs)

    def clean_recipient_email(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        email = self.cleaned_data["recipient_email"].strip().lower()
        validate_deliverable_email(email)
        if self.sender and email == self.sender.email.lower():
            raise forms.ValidationError("You can't gift an NFT to yourself.")
        try:
            recipient = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise forms.ValidationError("No Mintique account found with that email.")
        self.cleaned_data["recipient"] = recipient
        return email


class OfferForm(forms.ModelForm):
    DURATION_CHOICES = [
        ("1", "1 day"), ("3", "3 days"), ("7", "7 days"), ("30", "30 days"),
    ]
    duration_days = forms.ChoiceField(choices=DURATION_CHOICES, initial="7", label="Offer expires in")

    class Meta:
        model = Offer
        fields = ["amount", "currency"]
        widgets = {
            "amount": forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.0001", "min": "0.0001"}),
        }
        labels = {"amount": "Your offer"}

    def __init__(self, *args, nft=None, bidder=None, **kwargs):
        self.nft = nft
        self.bidder = bidder
        super().__init__(*args, **kwargs)

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Offer must be greater than zero.")
        return amount

    def clean(self):
        cleaned = super().clean()
        if self.nft and self.bidder and self.nft.owner_id == self.bidder.id:
            raise forms.ValidationError("You can't make an offer on an NFT you already own.")
        return cleaned


class CollectionForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = ["name", "description", "category", "cover_image", "banner_image"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Cosmic Series"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "What ties this collection together?"}),
        }


class MarketplaceFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={"placeholder": "Search NFTs..."}))
    category = forms.ChoiceField(
        required=False,
        choices=[("", "All Categories")] + list(Category.choices),
    )
    collection = forms.ModelChoiceField(
        required=False, queryset=Collection.objects.all(), empty_label="All Collections",
    )
    price_min = forms.DecimalField(required=False, min_value=0,
                                    widget=forms.NumberInput(attrs={"placeholder": "Min ETH", "step": "0.0001"}))
    price_max = forms.DecimalField(required=False, min_value=0,
                                    widget=forms.NumberInput(attrs={"placeholder": "Max ETH", "step": "0.0001"}))
    verified_only = forms.BooleanField(required=False, label="Verified creators only")
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("new", "Newest"),
            ("price_asc", "Price: Low to High"),
            ("price_desc", "Price: High to Low"),
            ("popular", "Most Liked"),
            ("trending", "Trending (views)"),
        ],
    )

    def clean(self):
        cleaned = super().clean()
        lo, hi = cleaned.get("price_min"), cleaned.get("price_max")
        if lo is not None and hi is not None and lo > hi:
            raise forms.ValidationError("Minimum price can't be greater than maximum price.")
        return cleaned
