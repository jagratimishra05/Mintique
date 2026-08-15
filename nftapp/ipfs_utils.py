"""IPFS storage for NFT media + metadata, via Pinata's pinning API.

Two things get pinned per mint:
  1. The artwork file itself -> image CID.
  2. An OpenSea-style metadata JSON document (name, description, image
     ipfs:// URI, attributes) that embeds Mintique's own internal
     database id and content hash -> metadata CID. This metadata CID is
     what the ERC-721 contract's tokenURI points at.

Pinning happens *before* the on-chain mint transaction (the contract call
needs a metadata URI as an input), so at pin time the real ERC-721
tokenId doesn't exist yet — see NFT.token_id_display's docstring. The
metadata therefore cross-references Mintique's own database row id
(`nft.pk`), not a token id, for indexing purposes.

Pinning is skipped (functions return None) whenever PINATA_JWT isn't
configured, so local development and the rest of Mintique's simulated
mint flow keep working unmodified without any IPFS credentials.

Extensibility: `build_token_metadata` is the single place NFT -> ERC-721
JSON metadata gets built. Additional standards branch off it rather than
duplicating it:
  - ERC-1155 metadata is the same document shape (OpenSea's ERC-1155
    metadata spec is a superset of ERC-721's), so a future
    `build_token_metadata(nft, image_cid, standard=TokenStandard.ERC1155)`
    just needs to add a `decimals`/edition-count field.
  - ERC-4907 (rentable) and ERC-5192 (soulbound) don't need their own
    metadata shape at all — they're pure on-chain behavior — so nothing
    here needs to change for them.
"""
import json
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_IMAGE_MB = 50
VALID_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/svg+xml", "image/webp"}
PIN_TIMEOUT_SECONDS = 30
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.5


class IPFSError(Exception):
    """Raised for any IPFS operation that fails in a way the caller needs
    to know about and report to the user (as opposed to IPFS simply being
    unconfigured, which is the normal/expected `ipfs_enabled() is False`
    path and never raises)."""


def ipfs_enabled():
    return bool(settings.IPFS_ENABLED)


def _pinata_headers():
    return {"Authorization": f"Bearer {settings.PINATA_JWT}"}


def gateway_url(cid):
    """Human-browsable https URL for a CID, via the configured gateway."""
    if not cid:
        return ""
    return f"{settings.PINATA_GATEWAY_URL.rstrip('/')}/{cid}"


def to_ipfs_uri(cid):
    """The canonical `ipfs://<CID>` URI a smart contract's tokenURI
    should store — as opposed to gateway_url(), which is for humans
    clicking a link in a browser."""
    if not cid:
        return ""
    return f"ipfs://{cid}"


def _validate_file_for_pinning(file_obj, filename):
    """Raise IPFSError with a clear, user-facing message for anything that
    would make Pinata reject the upload or that we don't want pinned in
    the first place. Mirrors nftapp.forms.validate_nft_image's rules so
    the two can't silently drift, while staying self-contained here
    since ipfs_utils shouldn't import from forms.py (wrong direction of
    a Django app's dependency graph)."""
    size = getattr(file_obj, "size", None)
    if size is not None and size > MAX_IMAGE_MB * 1024 * 1024:
        raise IPFSError(f"'{filename}' is too large to pin ({size / (1024 * 1024):.1f}MB, max {MAX_IMAGE_MB}MB).")
    content_type = getattr(file_obj, "content_type", None)
    if content_type and content_type not in VALID_IMAGE_CONTENT_TYPES:
        raise IPFSError(f"'{filename}' has an unsupported content type ({content_type}) for IPFS pinning.")


def _post_with_retries(url, **kwargs):
    """POST to Pinata with a couple of retries on transient network
    failures (timeouts, connection resets) — but never retries on a 4xx
    (bad request / auth failure), since retrying an unfixable error just
    wastes time and obscures the real failure."""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            resp = requests.post(url, timeout=PIN_TIMEOUT_SECONDS, **kwargs)
        except requests.Timeout as exc:
            last_exc = exc
            logger.warning("IPFS: timeout on attempt %s/%s posting to %s", attempt, MAX_RETRIES + 1, url)
        except requests.ConnectionError as exc:
            last_exc = exc
            logger.warning("IPFS: connection error on attempt %s/%s posting to %s", attempt, MAX_RETRIES + 1, url)
        else:
            if resp.status_code >= 500:
                last_exc = requests.HTTPError(f"Pinata returned {resp.status_code}", response=resp)
                logger.warning("IPFS: server error %s on attempt %s/%s", resp.status_code, attempt, MAX_RETRIES + 1)
            else:
                return resp
        if attempt <= MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise IPFSError(f"Could not reach IPFS pinning service after {MAX_RETRIES + 1} attempts.") from last_exc


def pin_file_to_ipfs(file_obj, filename):
    """Pin a Django UploadedFile/File to IPFS via Pinata. Returns the CID.

    Raises IPFSError (never returns None) on a genuine failure — an
    unconfigured PINATA_JWT is the only case that returns None, since
    that's the expected "IPFS turned off" state rather than an error.
    """
    if not ipfs_enabled():
        return None
    _validate_file_for_pinning(file_obj, filename)
    try:
        file_obj.seek(0)
        content = file_obj.read()
        if not content:
            raise IPFSError(f"'{filename}' is empty — nothing to pin.")
        resp = _post_with_retries(
            f"{settings.PINATA_API_URL}/pinning/pinFileToIPFS",
            headers=_pinata_headers(),
            files={"file": (filename, content)},
            data={"pinataMetadata": json.dumps({"name": filename})},
        )
        if resp.status_code == 401:
            raise IPFSError("IPFS pinning failed: invalid or expired Pinata credentials.")
        resp.raise_for_status()
        cid = resp.json().get("IpfsHash")
        if not cid:
            raise IPFSError(f"Pinata did not return a CID for '{filename}'.")
        return cid
    except IPFSError:
        raise
    except requests.RequestException as exc:
        logger.exception("IPFS: failed to pin file %s", filename)
        raise IPFSError(f"Failed to pin '{filename}' to IPFS: {exc}") from exc
    finally:
        try:
            file_obj.seek(0)
        except Exception:
            pass


def pin_json_to_ipfs(data, name):
    """Pin a JSON-serializable dict to IPFS via Pinata. Returns the CID.

    Raises IPFSError (never returns None) on a genuine failure — see
    pin_file_to_ipfs's docstring for the unconfigured-vs-error distinction.
    """
    if not ipfs_enabled():
        return None
    try:
        resp = _post_with_retries(
            f"{settings.PINATA_API_URL}/pinning/pinJSONToIPFS",
            headers=_pinata_headers(),
            json={"pinataMetadata": {"name": name}, "pinataContent": data},
        )
        if resp.status_code == 401:
            raise IPFSError("IPFS pinning failed: invalid or expired Pinata credentials.")
        resp.raise_for_status()
        cid = resp.json().get("IpfsHash")
        if not cid:
            raise IPFSError(f"Pinata did not return a CID for metadata '{name}'.")
        return cid
    except IPFSError:
        raise
    except requests.RequestException as exc:
        logger.exception("IPFS: failed to pin JSON %s", name)
        raise IPFSError(f"Failed to pin metadata '{name}' to IPFS: {exc}") from exc


def build_token_metadata(nft, image_cid):
    """OpenSea/ERC-721-standard metadata document for `nft`, pointing at
    the already-pinned artwork via its IPFS CID."""
    return {
        "name": nft.name,
        "description": nft.description or "",
        "image": to_ipfs_uri(image_cid),
        "external_url": None,  # filled in by the caller with an absolute detail-page URL
        "attributes": [
            {"trait_type": "Category", "value": nft.get_category_display()},
            {"trait_type": "Creator", "value": nft.creator_name},
            {"trait_type": "Royalty %", "value": float(nft.royalty_percentage)},
        ],
        # Cross-reference back to Mintique's own database record so the
        # on-chain/IPFS artifact and the platform record can always be
        # reconciled with each other. This is Mintique's internal row id
        # (nft.pk) — not the ERC-721 tokenId, which doesn't exist until
        # mintNFT() actually runs on-chain (see NFT.token_id_display).
        "mintique_id": nft.pk,
        "mintique_content_hash": nft.content_hash,
        "mintique_token_standard": nft.token_standard,
    }


def pin_nft_to_ipfs(nft, external_url=""):
    """Pin an NFT's image, then its metadata (referencing that image), to
    IPFS. Returns (image_cid, metadata_cid) — either may be None only if
    IPFS isn't configured or the NFT has no image (both are non-error
    "nothing to do" states).

    Raises IPFSError on a genuine pinning failure — callers should catch
    this and decide how to surface it (e.g. nftapp.views.mint_view shows
    it as a form-level warning rather than crashing the mint).
    """
    if not ipfs_enabled() or not nft.image:
        return None, None

    image_cid = pin_file_to_ipfs(nft.image, nft.image.name.rsplit("/", 1)[-1])
    if not image_cid:
        return None, None

    metadata = build_token_metadata(nft, image_cid)
    metadata["external_url"] = external_url
    metadata_cid = pin_json_to_ipfs(metadata, f"mintique-{nft.pk}.json")
    return image_cid, metadata_cid
