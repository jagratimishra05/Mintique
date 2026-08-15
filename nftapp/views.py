import json
import logging
from datetime import date
from decimal import Decimal
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, models, transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from mintique.email_utils import send_transactional_email
from walletapp.models import Transaction, Wallet
from . import blockchain, ipfs_utils
from .forms import (
    BatchMintForm, CollectionForm, ContactForm, GiftNFTForm,
    ListForSaleForm, MarketplaceFilterForm, MintNFTForm, OfferForm,
)
from .models import NFT, Category, Collection, Like, MintStatus, NFTAttribute, Offer, RecentlyViewed, Wishlist

User = get_user_model()
logger = logging.getLogger(__name__)


def wallet_required(view_func):
    """Wallet connection is only enforced right before an on-chain action
    (minting / buying / gifting / burning) — browsing and the dashboard
    never require it."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        # Only block the actual state-changing submission (POST). GET
        # requests still render the page; static/js/wallet.js intercepts
        # the form submit client-side and opens the connect modal first —
        # this server-side check is the safety net in case JS is bypassed.
        if request.method == "POST" and not request.user.has_wallet:
            messages.warning(request, "Connect your wallet before continuing.")
            return redirect(f"{request.path}?wallet_required=1")
        return view_func(request, *args, **kwargs)
    return _wrapped


def home_view(request):
    trending = NFT.objects.filter(is_listed=True, is_burned=False).order_by("-likes")[:3]
    stats = {
        "minted": NFT.objects.count(),
        "collectors": Wallet.objects.filter(user__nfts__isnull=False).distinct().count() or 15000,
        "creators": NFT.objects.values("creator_name").distinct().count() or 500,
    }
    category_counts = dict(
        NFT.objects.filter(is_listed=True, is_burned=False).values_list("category").annotate(n=Count("id"))
    )
    category_icons = {
        "art": "🎨", "photography": "📷", "music": "🎵",
        "collectible": "🏺", "video": "🎬", "other": "✦",
    }
    categories = [
        {"key": key, "label": label, "count": category_counts.get(key, 0), "icon": category_icons.get(key, "✦")}
        for key, label in Category.choices
    ]
    recent_tokens = [
        f"#{t}" for t in NFT.objects.filter(onchain_token_id__isnull=False)
        .order_by("-minted_at").values_list("onchain_token_id", flat=True)[:8]
    ]
    return render(request, "home.html", {
        "trending": trending, "stats": stats, "categories": categories, "recent_tokens": recent_tokens,
    })


@login_required
def dashboard_view(request):
    user = request.user
    my_nfts = NFT.objects.filter(owner=user)
    wallet, _ = Wallet.objects.get_or_create(user=user)

    sell_txs = Transaction.objects.filter(user=user, tx_type=Transaction.TxType.SELL)
    total_earnings = sum((t.amount for t in sell_txs), Decimal("0"))
    royalty_txs = Transaction.objects.filter(user=user, tx_type=Transaction.TxType.ROYALTY)
    total_royalties = sum((t.amount for t in royalty_txs), Decimal("0"))

    # --- Last 6 months of sales/revenue, oldest → newest -------------------
    today = timezone.now().date().replace(day=1)
    month_starts = []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        month_starts.append(date(y, m, 1))

    sales_labels, sales_data, revenue_data = [], [], []
    for i, start in enumerate(month_starts):
        end = month_starts[i + 1] if i + 1 < len(month_starts) else date(
            start.year + (start.month == 12), start.month % 12 + 1, 1
        )
        bucket = sell_txs.filter(created_at__date__gte=start, created_at__date__lt=end)
        sales_labels.append(start.strftime("%b"))
        sales_data.append(bucket.count())
        revenue_data.append(float(sum((t.amount for t in bucket), Decimal("0"))))

    # --- Views / likes per NFT (top 5 most recent) --------------------------
    top_nfts = list(my_nfts.order_by("-created_at")[:5])
    nft_labels = [n.name[:14] for n in top_nfts] or ["No NFTs yet"]
    views_data = [n.views for n in top_nfts] or [0]
    likes_data = [n.likes for n in top_nfts] or [0]

    context = {
        # --- stat cards ---
        "total_nfts": NFT.objects.count(),
        "owned_nfts": my_nfts.count(),
        "collections_count": user.collections.count(),
        "total_earnings": total_earnings,
        "total_royalties": total_royalties,
        "wallet_eth": wallet.eth_balance,
        "wallet_mnq": wallet.mnq_balance,
        "recent_activity_count": Transaction.objects.filter(user=user).count(),
        "listed_items": my_nfts.filter(is_listed=True, is_burned=False).count(),
        "wishlist_count": Wishlist.objects.filter(user=user).count(),
        "collectors": Wallet.objects.exclude(user=user).count(),
        # --- charts ---
        "sales_labels": sales_labels,
        "sales_data": sales_data,
        "revenue_data": revenue_data,
        "nft_labels": nft_labels,
        "views_data": views_data,
        "likes_data": likes_data,
        # --- lists ---
        "recent_nfts": my_nfts[:6],
        "recent_transactions": Transaction.objects.filter(user=user)[:5],
    }
    return render(request, "nftapp/dashboard.html", context)


@login_required
@wallet_required
def mint_view(request):
    if request.method == "POST":
        form = MintNFTForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                nft = form.save(commit=False)
                nft.owner = request.user
                nft.creator = request.user
                # Reuse the hash MintNFTForm.clean_image already computed
                # (and duplicate-checked) from the raw upload, so the
                # file's bytes aren't hashed a second time in NFT.save().
                if getattr(form, "asset_hash", None):
                    nft.content_hash = form.asset_hash
                nft.save()
                for trait_type, value in form.cleaned_data.get("traits", []):
                    NFTAttribute.objects.create(nft=nft, trait_type=trait_type, value=value)
                if nft.is_lazy_minted:
                    # Metadata + content hash exist now, but the "on-chain"
                    # mint event (and its real ERC-721 token ID) only
                    # happens at first sale — see the lazy-mint
                    # finalization block in buy_nft_view. There is no
                    # token ID to show yet: per ERC-721, one doesn't exist
                    # until the contract actually assigns it.
                    messages.success(
                        request,
                        f"'{nft.name}' lazy-minted — its ERC-721 token ID will be assigned on-chain "
                        "at first sale.",
                    )
                else:
                    Transaction.objects.create(
                        user=request.user, tx_type=Transaction.TxType.MINT, nft=nft,
                        token="NFT", amount=1, note=f"Minted {nft.name} (Mintique #{nft.pk})",
                    )
                    if nft.is_listed and nft.price > 0:
                        Transaction.objects.create(
                            user=request.user, tx_type=Transaction.TxType.LIST, nft=nft,
                            token=nft.currency, amount=nft.price,
                            note=f"Listed {nft.name} for {nft.price} {nft.currency}",
                        )
                    if blockchain.web3_enabled():
                        messages.success(
                            request,
                            f"'{nft.name}' created — mint it on-chain from the item page to receive "
                            "its ERC-721 token ID.",
                        )
                    else:
                        messages.success(request, f"'{nft.name}' minted!")

                # Pin artwork + metadata to IPFS, and mark the NFT ready
                # for its on-chain mint transaction — only when IPFS is
                # actually configured (settings.IPFS_ENABLED) and it isn't
                # lazy-minted (a lazy mint has no on-chain event until
                # first sale). The mint page's own flow above is
                # completely unaffected either way — a failure here never
                # rolls back the NFT row itself, it just leaves the NFT in
                # its existing off-chain state with mint_error explaining
                # why, so the creator can retry from the detail page
                # rather than losing the mint entirely.
                if not nft.is_lazy_minted and ipfs_utils.ipfs_enabled():
                    detail_url = request.build_absolute_uri(nft.get_absolute_url())
                    try:
                        image_cid, metadata_cid = ipfs_utils.pin_nft_to_ipfs(nft, external_url=detail_url)
                    except ipfs_utils.IPFSError as exc:
                        logger.warning("mint_view: IPFS pin failed for NFT #%s: %s", nft.pk, exc)
                        nft.mint_error = str(exc)[:255]
                        nft.save(update_fields=["mint_error"])
                        messages.warning(
                            request,
                            f"'{nft.name}' was saved, but pinning to IPFS failed: {exc} "
                            "You can retry from the item page.",
                        )
                    else:
                        if image_cid and metadata_cid:
                            nft.ipfs_image_cid = image_cid
                            nft.ipfs_metadata_cid = metadata_cid
                            nft.image_uri = ipfs_utils.to_ipfs_uri(image_cid)
                            nft.metadata_uri = ipfs_utils.to_ipfs_uri(metadata_cid)
                            nft.network = blockchain.network_slug()
                            update_fields = [
                                "ipfs_image_cid", "ipfs_metadata_cid", "image_uri", "metadata_uri", "network",
                            ]
                            if blockchain.web3_enabled():
                                nft.mint_status = MintStatus.PENDING
                                update_fields.append("mint_status")
                            nft.save(update_fields=update_fields)
            return redirect("nftapp:nft_detail", pk=nft.pk)
    else:
        form = MintNFTForm(user=request.user)

    # Suggested price per category: the average of currently listed,
    # unburned NFTs in that category, so the mint form can offer a
    # starting point without forcing it — the creator always decides the
    # final price themselves.
    category_avgs = {
        row["category"]: row["avg_price"]
        for row in NFT.objects.filter(is_listed=True, is_burned=False, price__gt=0)
        .values("category").annotate(avg_price=models.Avg("price"))
    }
    fallback_avg = NFT.objects.filter(is_listed=True, is_burned=False, price__gt=0).aggregate(
        avg_price=models.Avg("price")
    )["avg_price"] or Decimal("0.05")
    suggested_prices = {
        key: round(float(category_avgs.get(key, fallback_avg)), 4) for key, _ in Category.choices
    }

    return render(request, "nftapp/mint.html", {
        "form": form, "suggested_prices_json": json.dumps(suggested_prices),
    })


@login_required
@wallet_required
def batch_mint_view(request):
    if request.method == "POST":
        form = BatchMintForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            created = []
            with transaction.atomic():
                asset_hashes = getattr(form, "asset_hashes", [])
                for i, image in enumerate(form.cleaned_data["images"], start=1):
                    nft = NFT(
                        owner=request.user,
                        creator=request.user,
                        creator_name=form.cleaned_data["creator_name"],
                        name=f"{form.cleaned_data['name_prefix']} #{i}",
                        description=form.cleaned_data["description"],
                        image=image,
                        category=form.cleaned_data["category"],
                        price=form.cleaned_data["price"],
                        currency=form.cleaned_data.get("currency") or NFT._meta.get_field("currency").default,
                        collection=form.cleaned_data.get("collection"),
                        royalty_percentage=form.cleaned_data.get("royalty_percentage") or 0,
                        is_lazy_minted=form.cleaned_data.get("is_lazy_minted", False),
                    )
                    # Reuse BatchMintForm.clean_images' precomputed,
                    # already duplicate-checked hash for this same image
                    # (asset_hashes is in the same order as `images`).
                    if i - 1 < len(asset_hashes):
                        nft.content_hash = asset_hashes[i - 1]
                    nft.save()
                    created.append(nft)
                    if not nft.is_lazy_minted:
                        Transaction.objects.create(
                            user=request.user, tx_type=Transaction.TxType.MINT, nft=nft,
                            token="NFT", amount=1, note=f"Batch minted {nft.name} (Mintique #{nft.pk})",
                        )
            messages.success(request, f"Batch mint complete — {len(created)} NFTs created.")
            return redirect("nftapp:my_collection")
    else:
        form = BatchMintForm(user=request.user)
    return render(request, "nftapp/batch_mint.html", {"form": form})


def marketplace_view(request):
    filter_form = MarketplaceFilterForm(request.GET or None)
    nfts = (
        NFT.objects.filter(is_listed=True, is_burned=False)
        .select_related("owner", "collection")
        .annotate(like_count=Count("like_set"))
        .order_by("-created_at")
    )

    if filter_form.is_valid():
        q = filter_form.cleaned_data.get("q")
        category = filter_form.cleaned_data.get("category")
        collection = filter_form.cleaned_data.get("collection")
        price_min = filter_form.cleaned_data.get("price_min")
        price_max = filter_form.cleaned_data.get("price_max")
        verified_only = filter_form.cleaned_data.get("verified_only")
        sort = filter_form.cleaned_data.get("sort")

        if q:
            nfts = nfts.filter(Q(name__icontains=q) | Q(creator_name__icontains=q) | Q(description__icontains=q))
        if category:
            nfts = nfts.filter(category=category)
        if collection:
            nfts = nfts.filter(collection=collection)
        if price_min is not None:
            nfts = nfts.filter(price__gte=price_min)
        if price_max is not None:
            nfts = nfts.filter(price__lte=price_max)
        if verified_only:
            nfts = nfts.filter(Q(owner__is_verified_creator=True) | Q(collection__is_verified=True))

        if sort == "price_asc":
            nfts = nfts.order_by("price")
        elif sort == "price_desc":
            nfts = nfts.order_by("-price")
        elif sort == "popular":
            nfts = nfts.order_by("-like_count")
        elif sort == "trending":
            nfts = nfts.order_by("-views")
        else:
            nfts = nfts.order_by("-created_at")

    paginator = Paginator(nfts, 9)
    page_obj = paginator.get_page(request.GET.get("page"))

    wishlisted_ids = set()
    if request.user.is_authenticated:
        wishlisted_ids = set(
            Wishlist.objects.filter(user=request.user, nft__in=page_obj).values_list("nft_id", flat=True)
        )

    return render(request, "nftapp/marketplace.html", {
        "filter_form": filter_form, "page_obj": page_obj, "wishlisted_ids": wishlisted_ids,
    })


def _qr_data_uri(data):
    """Render `data` as a QR code PNG and return it as a base64 data URI,
    so the detail page can embed it directly with no extra file storage.
    Returns None (rather than crashing the page) if the optional `qrcode`
    package hasn't been installed yet — run `pip install -r requirements.txt`."""
    import base64
    from io import BytesIO

    try:
        import qrcode
    except ImportError:
        return None

    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#08070c", back_color="#ffffff")
    buf = BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def nft_detail_view(request, pk):
    nft = get_object_or_404(NFT.objects.select_related("owner", "creator", "collection"), pk=pk)
    if not request.user.is_authenticated or request.user.id != nft.owner_id:
        NFT.objects.filter(pk=pk).update(views=F("views") + 1)
        nft.views += 1

    already_liked = False
    already_wishlisted = False
    if request.user.is_authenticated:
        already_liked = Like.objects.filter(user=request.user, nft=nft).exists()
        already_wishlisted = Wishlist.objects.filter(user=request.user, nft=nft).exists()
        # Bump/record the "recently viewed" entry for this user (auto_now
        # on viewed_at means an existing row's timestamp is refreshed too).
        RecentlyViewed.objects.update_or_create(user=request.user, nft=nft)

    verify_url = request.build_absolute_uri(nft.get_absolute_url())
    qr_data_uri = _qr_data_uri(verify_url)
    gift_form = GiftNFTForm(sender=request.user) if request.user.is_authenticated else None

    can_mint_onchain = (
        blockchain.web3_enabled()
        and nft.mint_status == MintStatus.PENDING
        and nft.ipfs_metadata_cid
        and request.user.is_authenticated
        and request.user.id == nft.owner_id
    )

    is_owner = request.user.is_authenticated and request.user.id == nft.owner_id
    offers = nft.offers.filter(status=Offer.Status.PENDING).select_related("bidder").order_by("-amount", "-created_at")
    best_offer = offers.first()
    my_offer = offers.filter(bidder=request.user).first() if request.user.is_authenticated else None
    offer_form = OfferForm(nft=nft, bidder=request.user) if request.user.is_authenticated and not is_owner else None
    activity = nft.activity.select_related("user").order_by("-created_at")[:25]

    return render(request, "nftapp/nft_detail.html", {
        "nft": nft, "already_liked": already_liked, "already_wishlisted": already_wishlisted,
        "qr_data_uri": qr_data_uri, "verify_url": verify_url, "gift_form": gift_form,
        "can_mint_onchain": can_mint_onchain,
        "traits": nft.attributes.all(),
        "is_owner": is_owner, "offers": offers, "best_offer": best_offer, "my_offer": my_offer,
        "offer_form": offer_form, "activity": activity,
        "onchain_mint_config_json": json.dumps({
            "network": blockchain.network_params(),
            "contractAddress": settings.NFT_CONTRACT_ADDRESS,
            "contractAbiUrl": reverse("nftapp:contract_abi"),
            "metadataUri": f"ipfs://{nft.ipfs_metadata_cid}",
            "mintiqueTokenId": str(nft.pk),
            "royaltyBps": int((nft.royalty_percentage or 0) * 100),
            "confirmUrl": reverse("nftapp:confirm_onchain_mint", args=[nft.pk]),
        }) if can_mint_onchain else "{}",
    })


def _certificate_context(request, nft):
    """Shared data for the certificate — used by both the on-screen
    certificate page and the downloadable PDF, so the two can never drift
    apart."""
    verify_url = request.build_absolute_uri(nft.get_absolute_url())
    owner = nft.owner
    if owner and getattr(owner, "wallet_address", None):
        certified_owner = f"{owner.wallet_address[:6]}…{owner.wallet_address[-4:]}"
    elif owner:
        certified_owner = f"@{owner.username}"
    else:
        certified_owner = "Unowned"
    return {
        "nft": nft,
        "asset_name": nft.name,
        "token_id": nft.token_id_display,
        "certificate_id": (nft.content_hash[:16] or f"MNTQ{nft.pk:08d}").upper(),
        "creator_name": nft.creator_name,
        "certified_owner": certified_owner,
        "date_minted": nft.created_at,
        "content_hash": nft.content_hash,
        "verify_url": verify_url,
    }


def _certificate_permission(request, nft):
    """Only the current owner, the original creator, or staff may view or
    download a certificate — it's proof of ownership, not public marketing
    material, even though the underlying NFT page itself is public."""
    if not request.user.is_authenticated:
        return False
    return request.user.is_staff or request.user.id in (nft.owner_id, nft.creator_id)


@login_required
def certificate_view(request, pk):
    nft = get_object_or_404(NFT.objects.select_related("owner", "creator", "collection"), pk=pk)
    if not _certificate_permission(request, nft):
        messages.error(request, "Only the owner or creator of this NFT can view its certificate.")
        return redirect("nftapp:nft_detail", pk=pk)

    ctx = _certificate_context(request, nft)
    ctx["qr_data_uri"] = _qr_data_uri(ctx["verify_url"])
    return render(request, "nftapp/certificate.html", ctx)


@login_required
def certificate_pdf_view(request, pk):
    from io import BytesIO

    from django.http import HttpResponse

    nft = get_object_or_404(NFT.objects.select_related("owner", "creator", "collection"), pk=pk)
    if not _certificate_permission(request, nft):
        messages.error(request, "Only the owner or creator of this NFT can download its certificate.")
        return redirect("nftapp:nft_detail", pk=pk)

    ctx = _certificate_context(request, nft)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError:
        messages.error(request, "PDF generation isn't available — install reportlab (see requirements.txt).")
        return redirect("nftapp:certificate", pk=pk)

    from reportlab.lib.utils import ImageReader

    buf = BytesIO()
    page_size = landscape(A4)  # 297 x 210mm — roomy enough for a clean, uncluttered layout
    width, height = page_size
    c = canvas.Canvas(buf, pagesize=page_size)

    cream = colors.HexColor("#faf6ec")
    cream_deep = colors.HexColor("#f2ead4")
    gold = colors.HexColor("#b8912f")
    gold_soft = colors.HexColor("#d8cca4")
    ink = colors.HexColor("#211a10")
    dim = colors.HexColor("#7a7264")

    def truncated(text, font, size, max_width):
        """Fit text to max_width, adding an ellipsis rather than letting it
        run off the page or overlap the next field."""
        text = str(text)
        if c.stringWidth(text, font, size) <= max_width:
            return text
        while text and c.stringWidth(text + "…", font, size) > max_width:
            text = text[:-1]
        return text + "…" if text else "…"

    # --- Background + border --------------------------------------------
    c.setFillColor(cream)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    margin = 16 * mm
    c.setStrokeColor(gold)
    c.setLineWidth(1.6)
    c.rect(margin, margin, width - 2 * margin, height - 2 * margin)
    c.setLineWidth(0.6)
    c.rect(margin + 4, margin + 4, width - 2 * margin - 8, height - 2 * margin - 8)

    # Small corner flourishes so the border doesn't look like a plain box.
    corner = 7 * mm
    for cx, cy, dx, dy in (
        (margin + 4, height - margin - 4, 1, -1),
        (width - margin - 4, height - margin - 4, -1, -1),
        (margin + 4, margin + 4, 1, 1),
        (width - margin - 4, margin + 4, -1, 1),
    ):
        c.setStrokeColor(gold)
        c.setLineWidth(1.1)
        c.line(cx, cy, cx + dx * corner, cy)
        c.line(cx, cy, cx, cy + dy * corner)

    inner_left = margin + 14 * mm
    inner_right = width - margin - 14 * mm

    # --- Header ------------------------------------------------------------
    y = height - margin - 16 * mm
    c.setFillColor(gold)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(width / 2, y, "✦   M I N T I Q U E   ✦")

    y -= 9 * mm
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(width / 2, y, "Certificate of Authenticity")

    y -= 7 * mm
    c.setFillColor(dim)
    c.setFont("Helvetica", 9)
    subtitle = "This certifies that the digital asset described below is recorded and verifiably owned on the Mintique platform."
    c.drawCentredString(width / 2, y, subtitle)

    y -= 10 * mm
    c.setStrokeColor(gold_soft)
    c.setLineWidth(0.8)
    c.line(inner_left, y, inner_right, y)

    # --- Body: image (left) + field grid (right) ---------------------------
    body_top = y - 12 * mm
    img_w = img_h = 52 * mm
    img_x = inner_left
    img_y = body_top - img_h

    try:
        # Matte/frame behind the artwork, like a museum label — drawn first
        # so that images whose aspect ratio isn't square still sit on a
        # clean backing instead of bare page background.
        c.setFillColor(cream_deep)
        c.setStrokeColor(gold)
        c.setLineWidth(1)
        c.rect(img_x - 2, img_y - 2, img_w + 4, img_h + 4, fill=1, stroke=1)
        # preserveAspectRatio=True fits the whole image inside the box
        # (letterboxed on the matte, never cropped) — this must stay True,
        # since disabling it or using a "cover" style crop is what sliced
        # off the edges of non-square artwork before.
        c.drawImage(ImageReader(nft.image.path), img_x, img_y, img_w, img_h,
                    preserveAspectRatio=True, anchor="c", mask="auto")
    except Exception:
        c.setFillColor(cream_deep)
        c.rect(img_x, img_y, img_w, img_h, fill=1, stroke=0)

    grid_x = img_x + img_w + 16 * mm
    grid_w = inner_right - grid_x
    col_gap = 10 * mm
    col_w = (grid_w - col_gap) / 2
    fx1 = grid_x
    fx2 = grid_x + col_w + col_gap
    row_h = 17 * mm
    fy = body_top - 6 * mm

    def field(x, yy, label, value, col_width):
        c.setFillColor(dim)
        c.setFont("Helvetica", 7.5)
        c.drawString(x, yy, label)
        c.setFillColor(ink)
        c.setFont("Helvetica-Bold", 11.5)
        c.drawString(x, yy - 13, truncated(value, "Helvetica-Bold", 11.5, col_width))

    token_id_str = f"#{ctx['token_id']}" if ctx["token_id"] is not None else "Pending on-chain mint"
    field(fx1, fy, "ASSET NAME", ctx["asset_name"], col_w)
    field(fx1, fy - row_h, "TOKEN ID", token_id_str, col_w)
    field(fx1, fy - 2 * row_h, "CREATOR", ctx["creator_name"], col_w)
    field(fx2, fy, "CERTIFICATE ID", ctx["certificate_id"], col_w)
    field(fx2, fy - row_h, "CERTIFIED OWNER", ctx["certified_owner"], col_w)
    field(fx2, fy - 2 * row_h, "DATE MINTED", ctx["date_minted"].strftime("%B %d, %Y"), col_w)

    # --- Footer: hash (left), QR (center), wordmark (right) ----------------
    footer_top = min(img_y, fy - 3 * row_h) - 10 * mm
    c.setStrokeColor(gold_soft)
    c.setLineWidth(0.8)
    c.line(inner_left, footer_top, inner_right, footer_top)

    qr_size = 26 * mm
    qr_x = width / 2 - qr_size / 2
    qr_y = margin + 8 * mm
    try:
        import qrcode
        qr_img = qrcode.make(ctx["verify_url"])
        c.drawImage(ImageReader(qr_img), qr_x, qr_y, qr_size, qr_size)
    except Exception:
        pass
    c.setFillColor(dim)
    c.setFont("Helvetica", 7)
    c.drawCentredString(width / 2, qr_y - 9, "Scan to verify")

    hash_top = footer_top - 12 * mm
    c.setFillColor(dim)
    c.setFont("Helvetica", 7)
    c.drawString(inner_left, hash_top, "CONTENT HASH")
    hash_col_w = qr_x - 8 * mm - inner_left
    c.setFillColor(ink)
    c.setFont("Helvetica", 7.5)
    hash_val = ctx["content_hash"] or "—"
    # Wrap the hash across up to two lines instead of truncating it, since
    # it's meant to be verifiable/readable.
    line1, line2 = hash_val, ""
    if c.stringWidth(hash_val, "Helvetica", 7.5) > hash_col_w:
        half = len(hash_val) // 2
        line1, line2 = hash_val[:half], hash_val[half:]
    c.drawString(inner_left, hash_top - 10, line1)
    if line2:
        c.drawString(inner_left, hash_top - 19, line2)

    c.setFillColor(gold)
    c.setFont("Helvetica-Oblique", 13)
    c.drawRightString(inner_right, hash_top, "Mintique")
    c.setFillColor(dim)
    c.setFont("Helvetica", 7)
    c.drawRightString(inner_right, hash_top - 11, "PLATFORM OF RECORD")

    c.showPage()
    c.save()
    buf.seek(0)

    response = HttpResponse(buf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="mintique-certificate-{nft.pk}.pdf"'
    return response


@login_required
def toggle_like_view(request, pk):
    nft = get_object_or_404(NFT, pk=pk)
    like, created = Like.objects.get_or_create(user=request.user, nft=nft)
    if not created:
        like.delete()
        nft.likes = max(0, nft.likes - 1)
    else:
        nft.likes += 1
    nft.save(update_fields=["likes"])
    return redirect("nftapp:nft_detail", pk=pk)


@login_required
def toggle_wishlist_view(request, pk):
    nft = get_object_or_404(NFT, pk=pk)
    item, created = Wishlist.objects.get_or_create(user=request.user, nft=nft)
    if not created:
        item.delete()
        messages.info(request, f"Removed '{nft.name}' from your wishlist.")
    else:
        messages.success(request, f"Added '{nft.name}' to your wishlist.")
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("nftapp:nft_detail", pk=pk)


@login_required
def wishlist_view(request):
    items = Wishlist.objects.filter(user=request.user).select_related("nft", "nft__owner")
    nfts = [i.nft for i in items]
    wishlisted_ids = {nft.pk for nft in nfts}
    return render(request, "nftapp/wishlist.html", {"nfts": nfts, "wishlisted_ids": wishlisted_ids})


@login_required
def favorites_view(request):
    likes = Like.objects.filter(user=request.user).select_related("nft", "nft__owner")
    nfts = [l.nft for l in likes]
    wishlisted_ids = set(
        Wishlist.objects.filter(user=request.user, nft__in=nfts).values_list("nft_id", flat=True)
    )
    return render(request, "nftapp/favorites.html", {"nfts": nfts, "wishlisted_ids": wishlisted_ids})


@login_required
def recently_viewed_view(request):
    items = RecentlyViewed.objects.filter(user=request.user).select_related("nft", "nft__owner")[:30]
    nfts = [i.nft for i in items]
    wishlisted_ids = set(
        Wishlist.objects.filter(user=request.user, nft__in=nfts).values_list("nft_id", flat=True)
    )
    return render(request, "nftapp/recently_viewed.html", {"nfts": nfts, "wishlisted_ids": wishlisted_ids})


def _pay_royalty_and_split_proceeds(nft, sale_price):
    """On a resale (creator != current owner/seller), deduct the creator's
    royalty from the seller's proceeds and pay it to the creator. On a
    primary sale (creator == seller, e.g. first sale of a freshly minted or
    just-finalized lazy-minted NFT) no royalty is owed. Returns
    (seller_proceeds, royalty_amount)."""
    if nft.creator_id and nft.creator_id != nft.owner_id and nft.royalty_percentage:
        royalty_amount = (sale_price * nft.royalty_percentage / Decimal("100")).quantize(Decimal("0.0001"))
        royalty_amount = min(royalty_amount, sale_price)
        return sale_price - royalty_amount, royalty_amount
    return sale_price, Decimal("0")


@login_required
@wallet_required
def buy_nft_view(request, pk):
    nft = get_object_or_404(NFT, pk=pk, is_listed=True, is_burned=False)
    if nft.owner_id == request.user.id:
        messages.error(request, "You already own this NFT.")
        return redirect("nftapp:nft_detail", pk=pk)

    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    currency = nft.currency
    # Demo/simulated USD price for whatever currency this NFT is priced in,
    # derived from the same ETH-based rate table the swap widget uses (see
    # settings.CRYPTO_RATES_PER_ETH), so "$" estimates stay consistent
    # platform-wide regardless of which token a listing is denominated in.
    rate_per_eth = Decimal(str(settings.CRYPTO_RATES_PER_ETH.get(currency, 1)))
    usd_per_unit = Decimal(str(settings.ETH_USD_RATE)) / rate_per_eth if rate_per_eth else Decimal("0")

    if request.method == "GET":
        # Checkout summary — mirrors a marketplace checkout modal: item,
        # price, payment method, and a confirm step before anything is
        # actually charged. The wallet-connect gate + the real purchase
        # both happen on the POST below (data-wallet-gate on the form).
        balance = wallet.get_balance(currency) or Decimal("0")
        sufficient_funds = balance >= nft.price
        return render(request, "nftapp/checkout.html", {
            "nft": nft, "wallet": wallet, "sufficient_funds": sufficient_funds,
            "wallet_balance": balance, "currency": currency,
            "usd_estimate": nft.price * usd_per_unit,
        })

    balance = wallet.get_balance(currency) or Decimal("0")
    if balance < nft.price:
        messages.error(
            request,
            f"Insufficient {currency} balance. Try swapping for more {currency} first.",
        )
        return redirect("walletapp:swap")

    with transaction.atomic():
        seller = nft.owner
        seller_wallet, _ = Wallet.objects.get_or_create(user=seller)

        seller_proceeds, royalty_amount = _pay_royalty_and_split_proceeds(nft, nft.price)

        wallet.set_balance(currency, wallet.get_balance(currency) - nft.price)
        seller_wallet.set_balance(currency, (seller_wallet.get_balance(currency) or Decimal("0")) + seller_proceeds)
        wallet.save(update_fields=[Wallet.BALANCE_FIELDS[currency]])
        seller_wallet.save(update_fields=[Wallet.BALANCE_FIELDS[currency]])

        Transaction.objects.create(user=request.user, tx_type=Transaction.TxType.BUY, nft=nft,
                                    token=currency, amount=nft.price, note=f"Bought {nft.name}")
        sell_note = f"Sold {nft.name}"
        if royalty_amount:
            sell_note += f" (after {nft.royalty_percentage}% creator royalty)"
        Transaction.objects.create(user=seller, tx_type=Transaction.TxType.SELL, nft=nft,
                                    token=currency, amount=seller_proceeds, note=sell_note)

        if royalty_amount and nft.creator_id:
            creator_wallet, _ = Wallet.objects.get_or_create(user=nft.creator)
            creator_wallet.set_balance(currency, (creator_wallet.get_balance(currency) or Decimal("0")) + royalty_amount)
            creator_wallet.save(update_fields=[Wallet.BALANCE_FIELDS[currency]])
            Transaction.objects.create(
                user=nft.creator, tx_type=Transaction.TxType.ROYALTY, token=currency, nft=nft,
                amount=royalty_amount, note=f"Royalty on resale of {nft.name}",
            )

        # Lazy-mint finalization: the first sale of a lazy-minted NFT is the
        # point it actually "mints" — log that now if it hasn't already.
        if nft.is_lazy_minted and not nft.lazy_minted_at:
            nft.lazy_minted_at = timezone.now()
            Transaction.objects.create(
                user=seller, tx_type=Transaction.TxType.MINT, token="NFT", nft=nft,
                amount=1, note=f"Lazy-minted {nft.name} (Mintique #{nft.pk}) finalized on first sale",
            )

        nft.owner = request.user
        nft.is_listed = False
        nft.save(update_fields=["owner", "is_listed", "lazy_minted_at"])

    messages.success(request, f"You now own '{nft.name}'!")
    return redirect("nftapp:nft_detail", pk=pk)


@login_required
@wallet_required
@require_POST
def make_offer_view(request, pk):
    nft = get_object_or_404(NFT, pk=pk, is_burned=False)
    form = OfferForm(request.POST, nft=nft, bidder=request.user)
    if form.is_valid():
        with transaction.atomic():
            # A fresh offer supersedes any prior pending offer from the
            # same bidder on this NFT, rather than stacking duplicates.
            Offer.objects.filter(nft=nft, bidder=request.user, status=Offer.Status.PENDING).update(
                status=Offer.Status.CANCELLED, responded_at=timezone.now()
            )
            days = int(form.cleaned_data.get("duration_days") or 7)
            offer = Offer.objects.create(
                nft=nft, bidder=request.user,
                amount=form.cleaned_data["amount"], currency=form.cleaned_data["currency"],
                expires_at=timezone.now() + timezone.timedelta(days=days),
            )
            Transaction.objects.create(
                user=request.user, tx_type=Transaction.TxType.OFFER, nft=nft,
                token=offer.currency, amount=offer.amount,
                note=f"Offered {offer.amount} {offer.currency} on {nft.name}",
            )
        messages.success(request, f"Your offer of {offer.amount} {offer.currency} was sent to the owner.")
    else:
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, err)
    return redirect("nftapp:nft_detail", pk=pk)


@login_required
@require_POST
def cancel_offer_view(request, offer_id):
    offer = get_object_or_404(Offer, pk=offer_id, bidder=request.user, status=Offer.Status.PENDING)
    offer.status = Offer.Status.CANCELLED
    offer.responded_at = timezone.now()
    offer.save(update_fields=["status", "responded_at"])
    messages.success(request, "Offer cancelled.")
    return redirect("nftapp:nft_detail", pk=offer.nft_id)


@login_required
@wallet_required
@require_POST
def accept_offer_view(request, offer_id):
    offer = get_object_or_404(
        Offer.objects.select_related("nft", "bidder"), pk=offer_id, status=Offer.Status.PENDING
    )
    nft = offer.nft
    if nft.owner_id != request.user.id:
        messages.error(request, "Only the current owner can accept an offer.")
        return redirect("nftapp:nft_detail", pk=nft.pk)
    if offer.is_expired:
        offer.status = Offer.Status.EXPIRED
        offer.save(update_fields=["status"])
        messages.error(request, "That offer has expired.")
        return redirect("nftapp:nft_detail", pk=nft.pk)

    bidder_wallet, _ = Wallet.objects.get_or_create(user=offer.bidder)
    balance = bidder_wallet.get_balance(offer.currency) or Decimal("0")
    if balance < offer.amount:
        messages.error(request, f"{offer.bidder.email} no longer has sufficient {offer.currency} balance to cover this offer.")
        return redirect("nftapp:nft_detail", pk=nft.pk)

    with transaction.atomic():
        seller = nft.owner
        seller_wallet, _ = Wallet.objects.get_or_create(user=seller)
        seller_proceeds, royalty_amount = _pay_royalty_and_split_proceeds(nft, offer.amount)

        bidder_wallet.set_balance(offer.currency, balance - offer.amount)
        seller_wallet.set_balance(
            offer.currency, (seller_wallet.get_balance(offer.currency) or Decimal("0")) + seller_proceeds
        )
        bidder_wallet.save(update_fields=[Wallet.BALANCE_FIELDS[offer.currency]])
        seller_wallet.save(update_fields=[Wallet.BALANCE_FIELDS[offer.currency]])

        Transaction.objects.create(user=offer.bidder, tx_type=Transaction.TxType.BUY, nft=nft,
                                    token=offer.currency, amount=offer.amount,
                                    note=f"Bought {nft.name} (accepted offer)")
        sell_note = f"Sold {nft.name} (accepted offer)"
        if royalty_amount:
            sell_note += f" (after {nft.royalty_percentage}% creator royalty)"
        Transaction.objects.create(user=seller, tx_type=Transaction.TxType.SELL, nft=nft,
                                    token=offer.currency, amount=seller_proceeds, note=sell_note)
        if royalty_amount and nft.creator_id:
            creator_wallet, _ = Wallet.objects.get_or_create(user=nft.creator)
            creator_wallet.set_balance(
                offer.currency, (creator_wallet.get_balance(offer.currency) or Decimal("0")) + royalty_amount
            )
            creator_wallet.save(update_fields=[Wallet.BALANCE_FIELDS[offer.currency]])
            Transaction.objects.create(
                user=nft.creator, tx_type=Transaction.TxType.ROYALTY, token=offer.currency, nft=nft,
                amount=royalty_amount, note=f"Royalty on resale of {nft.name}",
            )

        if nft.is_lazy_minted and not nft.lazy_minted_at:
            nft.lazy_minted_at = timezone.now()
            Transaction.objects.create(
                user=seller, tx_type=Transaction.TxType.MINT, token="NFT", nft=nft,
                amount=1, note=f"Lazy-minted {nft.name} (Mintique #{nft.pk}) finalized on first sale",
            )

        offer.status = Offer.Status.ACCEPTED
        offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "responded_at"])
        # Any other pending offers on this NFT no longer apply — it has a
        # new owner now.
        Offer.objects.filter(nft=nft, status=Offer.Status.PENDING).exclude(pk=offer.pk).update(
            status=Offer.Status.EXPIRED, responded_at=timezone.now()
        )

        nft.owner = offer.bidder
        nft.is_listed = False
        nft.save(update_fields=["owner", "is_listed", "lazy_minted_at"])

    messages.success(request, f"Offer accepted — '{nft.name}' sold to {offer.bidder.email}.")
    return redirect("nftapp:nft_detail", pk=nft.pk)


@login_required
@require_POST
def reject_offer_view(request, offer_id):
    offer = get_object_or_404(Offer.objects.select_related("nft"), pk=offer_id, status=Offer.Status.PENDING)
    if offer.nft.owner_id != request.user.id:
        messages.error(request, "Only the current owner can decline an offer.")
        return redirect("nftapp:nft_detail", pk=offer.nft_id)
    offer.status = Offer.Status.REJECTED
    offer.responded_at = timezone.now()
    offer.save(update_fields=["status", "responded_at"])
    messages.success(request, "Offer declined.")
    return redirect("nftapp:nft_detail", pk=offer.nft_id)


@login_required
@wallet_required
def gift_nft_view(request, pk):
    nft = get_object_or_404(NFT, pk=pk, is_burned=False)
    if nft.owner_id != request.user.id:
        messages.error(request, "You can only gift NFTs you own.")
        return redirect("nftapp:nft_detail", pk=pk)

    form = GiftNFTForm(request.POST or None, sender=request.user)
    if request.method == "POST" and form.is_valid():
        recipient = form.cleaned_data["recipient"]
        with transaction.atomic():
            nft.owner = recipient
            nft.is_listed = False
            nft.save(update_fields=["owner", "is_listed"])
            Transaction.objects.create(user=request.user, tx_type=Transaction.TxType.GIFT, nft=nft,
                                        token="NFT", amount=0, note=f"Gifted {nft.name} to {recipient.email}")
            Transaction.objects.create(user=recipient, tx_type=Transaction.TxType.GIFT, nft=nft,
                                        token="NFT", amount=0, note=f"Received {nft.name} from {request.user.email}")
        messages.success(request, f"'{nft.name}' gifted to {recipient.email}.")
        return redirect("nftapp:my_collection")

    return render(request, "nftapp/gift_nft.html", {"nft": nft, "form": form})


@login_required
@wallet_required
def burn_nft_view(request, pk):
    nft = get_object_or_404(NFT, pk=pk)
    if nft.owner_id != request.user.id:
        messages.error(request, "You can only burn NFTs you own.")
        return redirect("nftapp:nft_detail", pk=pk)
    if nft.is_burned:
        messages.info(request, "This NFT has already been burned.")
        return redirect("nftapp:nft_detail", pk=pk)

    if request.method == "POST":
        with transaction.atomic():
            nft.is_burned = True
            nft.burned_at = timezone.now()
            nft.is_listed = False
            nft.save(update_fields=["is_burned", "burned_at", "is_listed"])
            Transaction.objects.create(user=request.user, tx_type=Transaction.TxType.BURN, nft=nft,
                                        token="NFT", amount=0, note=f"Burned {nft.name} (Mintique #{nft.pk})")
        messages.success(request, f"'{nft.name}' has been permanently burned.")
        return redirect("nftapp:my_collection")

    return redirect("nftapp:nft_detail", pk=pk)


@login_required
def my_collection_view(request):
    nfts = NFT.objects.filter(owner=request.user).select_related("collection")
    my_collections = Collection.objects.filter(owner=request.user)
    return render(request, "nftapp/my_collection.html", {"nfts": nfts, "my_collections": my_collections})


@login_required
def sell_view(request):
    """'Sell NFTs' dashboard page: owned NFTs split into ones already
    listed on the marketplace and ones that can be listed for sale."""
    owned = NFT.objects.filter(owner=request.user, is_burned=False).select_related("collection")
    listed = owned.filter(is_listed=True)
    unlisted = owned.filter(is_listed=False)
    unlisted_items = [(nft, ListForSaleForm(instance=nft)) for nft in unlisted]
    return render(request, "nftapp/sell.html", {
        "listed_nfts": listed, "unlisted_items": unlisted_items, "unlisted_count": len(unlisted_items),
    })


@login_required
@require_POST
def list_for_sale_view(request, pk):
    nft = get_object_or_404(NFT, pk=pk, owner=request.user, is_burned=False)
    form = ListForSaleForm(request.POST, instance=nft)
    if form.is_valid():
        nft = form.save(commit=False)
        nft.is_listed = True
        nft.save(update_fields=["price", "currency", "is_listed"])
        messages.success(request, f"{nft.name} is now listed for {nft.price} {nft.currency}.")
    else:
        messages.error(request, "Couldn't list that NFT — please set a valid price.")
    return redirect("nftapp:sell")


@login_required
@require_POST
def unlist_nft_view(request, pk):
    nft = get_object_or_404(NFT, pk=pk, owner=request.user, is_burned=False)
    nft.is_listed = False
    nft.save(update_fields=["is_listed"])
    messages.info(request, f"{nft.name} was removed from sale.")
    return redirect("nftapp:sell")


@login_required
def create_collection_view(request):
    if request.method == "POST":
        form = CollectionForm(request.POST, request.FILES)
        if form.is_valid():
            collection = form.save(commit=False)
            collection.owner = request.user
            collection.save()
            messages.success(request, f"Collection '{collection.name}' created.")
            return redirect("nftapp:collection_detail", slug=collection.slug)
    else:
        form = CollectionForm()
    return render(request, "nftapp/collection_form.html", {"form": form})


def collection_list_view(request):
    collections = (
        Collection.objects.annotate(item_count=Count("nfts"))
        .select_related("owner")
        .order_by("-is_verified", "-created_at")
    )
    q = request.GET.get("q")
    if q:
        collections = collections.filter(Q(name__icontains=q) | Q(owner__username__icontains=q))
    paginator = Paginator(collections, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "nftapp/collection_list.html", {"page_obj": page_obj, "q": q or ""})


def collection_detail_view(request, slug):
    collection = get_object_or_404(Collection.objects.select_related("owner"), slug=slug)
    nfts = collection.nfts.filter(is_burned=False).select_related("owner")
    if not (request.user.is_authenticated and request.user.id == collection.owner_id):
        nfts = nfts.filter(is_listed=True)
    wishlisted_ids = set()
    if request.user.is_authenticated:
        wishlisted_ids = set(
            Wishlist.objects.filter(user=request.user, nft__in=nfts).values_list("nft_id", flat=True)
        )
    return render(request, "nftapp/collection_detail.html", {
        "collection": collection, "nfts": nfts, "wishlisted_ids": wishlisted_ids,
    })


def creator_profile_view(request, username):
    creator = get_object_or_404(User, username=username)
    nfts = NFT.objects.filter(owner=creator, is_burned=False)
    if not (request.user.is_authenticated and request.user.id == creator.id):
        nfts = nfts.filter(is_listed=True)
    collections = Collection.objects.filter(owner=creator)
    stats = {
        "minted": NFT.objects.filter(creator=creator).count(),
        "sold": Transaction.objects.filter(user=creator, tx_type=Transaction.TxType.SELL).count(),
    }
    wishlisted_ids = set()
    if request.user.is_authenticated:
        wishlisted_ids = set(
            Wishlist.objects.filter(user=request.user, nft__in=nfts).values_list("nft_id", flat=True)
        )
    return render(request, "nftapp/creator_profile.html", {
        "creator": creator, "nfts": nfts, "collections": collections, "stats": stats,
        "wishlisted_ids": wishlisted_ids,
    })


def about_view(request):
    """Company/project story — mission, vision, and platform milestones."""
    stats = {
        "minted": NFT.objects.count() or 25000,
        "creators": NFT.objects.values("creator_name").distinct().count() or 500,
    }
    return render(request, "about.html", {"stats": stats})


def contact_view(request):
    """Contact form: validates input, emails the team (or logs to console in
    dev when no SMTP credentials are configured), and shows a success state
    that reflects what actually happened — a caught send failure no longer
    reports "sent" to the person filling out the form."""
    sent = False
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            status = send_transactional_email(
                subject=f"[Mintique Contact] {data['subject']} — {data['name']}",
                message=f"From: {data['name']} <{data['email']}>\n\n{data['message']}",
                recipient_list=[getattr(settings, "EMAIL_HOST_USER", None) or "support@mintique.io"],
                context="contact form",
            )
            if status == "sent":
                sent = True
                messages.success(request, "Message sent — we'll get back to you within 24 hours.")
                form = ContactForm()
            elif status == "console":
                messages.warning(
                    request,
                    "Your message was recorded, but this server doesn't have email delivery "
                    "configured yet, so it wasn't actually emailed to our team. Please reach "
                    "out another way in the meantime, or try again once email is set up.",
                )
            else:
                messages.error(
                    request,
                    "We couldn't send your message right now — the email server isn't reachable. "
                    "Please try again shortly, or email us directly.",
                )
    else:
        form = ContactForm()
    return render(request, "contact.html", {"form": form, "sent": sent})


def contract_abi_view(request):
    """Serves the MintiqueNFT contract ABI so the browser (ethers.js) can
    build a contract instance for MetaMask to sign against, without
    needing the ABI duplicated into the static/ pipeline.

    Defaults to the ERC-721 contract; pass ?standard=erc1155 once that
    companion contract (contracts/MintiqueNFT1155.sol) is deployed and
    configured."""
    standard = request.GET.get("standard", "erc721")
    try:
        abi = blockchain._load_abi(standard) or []
    except blockchain.BlockchainError:
        return JsonResponse({"error": f"Unknown token standard '{standard}'."}, status=400)
    return JsonResponse(abi, safe=False)


@login_required
@require_POST
def confirm_onchain_mint_view(request, pk):
    """Called by static/js/web3mint.js right after the owner's MetaMask
    wallet signs and broadcasts the `mintNFT` transaction on Polygon.
    Verifies the transaction server-side (when web3/RPC access is
    available) before trusting it, then records the on-chain details on
    the NFT and logs a wallet Transaction — mirroring how the existing
    off-chain mint records a Transaction in mint_view above.
    """
    nft = get_object_or_404(NFT, pk=pk, owner=request.user)
    tx_hash = (request.POST.get("tx_hash") or "").strip()
    wallet_address = (request.POST.get("wallet_address") or "").strip()
    standard = nft.token_standard or "erc721"

    if not tx_hash:
        return JsonResponse({"ok": False, "error": "Missing transaction hash."}, status=400)
    if not wallet_address:
        return JsonResponse({"ok": False, "error": "Missing wallet address."}, status=400)
    if nft.mint_status == MintStatus.CONFIRMED:
        return JsonResponse({"ok": False, "error": "This NFT is already confirmed on-chain."}, status=400)

    verification = {"confirmed": True, "onchain_token_id": None, "to": wallet_address, "error": None}
    if blockchain.web3_enabled():
        try:
            verification = blockchain.verify_mint_transaction(
                tx_hash, expected_to_address=wallet_address, standard=standard,
            )
        except blockchain.BlockchainError as exc:
            logger.exception("confirm_onchain_mint_view: verification error for NFT #%s", nft.pk)
            nft.mint_error = str(exc)[:255]
            nft.save(update_fields=["mint_error"])
            return JsonResponse({"ok": False, "error": f"On-chain verification failed: {exc}"}, status=502)

        if not verification["confirmed"]:
            error_msg = verification.get("error") or "Transaction could not be verified on-chain yet."
            nft.mint_error = error_msg[:255]
            nft.save(update_fields=["mint_error"])
            return JsonResponse({"ok": False, "error": error_msg}, status=409)

    # Belt-and-suspenders check against the DB constraints added in
    # NFT.Meta.constraints (unique_polygon_tx_hash /
    # unique_onchain_token_per_contract_chain): catch a reused tx_hash, or
    # an onchain_token_id already recorded against a *different* row on
    # this same contract/chain, up front with a clear message — rather
    # than surfacing a raw IntegrityError to the user if this same real
    # transaction somehow gets reported twice (e.g. a retried/duplicate
    # confirm request from the client).
    already_confirmed = NFT.objects.filter(polygon_tx_hash=tx_hash).exclude(pk=nft.pk).exists()
    if already_confirmed:
        error_msg = "This transaction has already been recorded against another NFT."
        nft.mint_error = error_msg[:255]
        nft.save(update_fields=["mint_error"])
        return JsonResponse({"ok": False, "error": error_msg}, status=409)

    onchain_token_id = verification.get("onchain_token_id")
    if onchain_token_id is not None:
        contract_address = blockchain.contract_address_for(standard)
        duplicate_token = NFT.objects.filter(
            contract_address=contract_address,
            chain_id=settings.POLYGON_CHAIN_ID,
            onchain_token_id=onchain_token_id,
        ).exclude(pk=nft.pk).exists()
        if duplicate_token:
            error_msg = "That on-chain token ID is already recorded against another NFT on this contract."
            nft.mint_error = error_msg[:255]
            nft.save(update_fields=["mint_error"])
            return JsonResponse({"ok": False, "error": error_msg}, status=409)

    try:
        with transaction.atomic():
            update_fields = blockchain.build_confirmed_mint_fields(
                nft, tx_hash, wallet_address, verification, standard=standard,
            )
            for field, value in update_fields.items():
                setattr(nft, field, value)
            nft.save(update_fields=list(update_fields.keys()))
            Transaction.objects.create(
                user=request.user, tx_type=Transaction.TxType.MINT, token="NFT", amount=0, nft=nft,
                note=f"'{nft.name}' (#{nft.onchain_token_id}) confirmed on {nft.get_network_display() or 'Polygon'}",
                tx_hash=tx_hash,
            )
    except IntegrityError:
        # The pre-checks above should catch this first in the normal
        # case, but a concurrent request confirming the same tx_hash /
        # onchain_token_id at the same instant could still race past
        # them — the DB's own unique constraints are the final backstop,
        # and transaction.atomic() ensures this failed attempt leaves no
        # partial row behind.
        logger.warning(
            "confirm_onchain_mint_view: duplicate onchain record rejected by DB constraint for NFT #%s",
            nft.pk,
        )
        return JsonResponse(
            {"ok": False, "error": "This transaction or token ID is already recorded against another NFT."},
            status=409,
        )
    except Exception:
        logger.exception("confirm_onchain_mint_view: failed to persist confirmed mint for NFT #%s", nft.pk)
        return JsonResponse(
            {"ok": False, "error": "Transaction was verified on-chain, but saving the result failed. "
                                    "Please contact support with your transaction hash."},
            status=500,
        )

    messages.success(request, f"'{nft.name}' confirmed on-chain on Polygon.")
    return JsonResponse({
        "ok": True,
        "explorer_url": blockchain.explorer_tx_url(tx_hash),
        "token_id": nft.onchain_token_id,
        "contract_address": nft.contract_address,
        "metadata_uri": nft.metadata_uri,
    })
