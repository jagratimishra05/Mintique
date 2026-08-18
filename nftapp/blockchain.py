"""Polygon blockchain integration.

Minting itself is signed client-side by the user's own MetaMask wallet
(see static/js/web3mint.js) — Mintique's backend never holds a private key
or pays gas. This module covers what the backend *does* need:

  1. `network_params()` — the chain config the frontend needs to get
     MetaMask onto the right Polygon network (via wallet_addEthereumChain
     / wallet_switchEthereumChain).
  2. `verify_mint_transaction()` — a read-only check, via web3.py, that a
     tx hash the client reports back really is a confirmed `MintiqueMinted`
     mint on our contract, before Mintique's database trusts it.
  3. A small per-standard contract *registry* (`CONTRACT_REGISTRY` /
     `get_contract_config`) so adding a second deployed contract — e.g.
     an ERC-1155 companion contract (contracts/MintiqueNFT1155.sol) — is
     a matter of adding one settings variable + one registry entry, not
     touching this module's call sites.

Falls back gracefully (returns None / not-verified) wherever web3 isn't
installed or the relevant contract address isn't configured, so the rest
of the app keeps working without a deployed contract.
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from web3 import Web3
except ImportError:  # pragma: no cover - optional dependency
    Web3 = None


class BlockchainError(Exception):
    """Raised for a blockchain operation that fails in a way the caller
    needs to report to the user — as opposed to web3 simply being
    unavailable/unconfigured, which is the expected "off-chain mode"
    path and returns None/False rather than raising."""


def web3_enabled():
    return bool(settings.WEB3_ENABLED and Web3 is not None)


def network_params():
    """Config the frontend needs to add/switch MetaMask to the active
    Polygon network (matches the wallet_addEthereumChain RPC schema)."""
    net = settings.POLYGON_ACTIVE_NETWORK
    return {
        "chainId": net["chain_id_hex"],
        "chainName": net["name"],
        "rpcUrls": [net["rpc_url"]],
        "blockExplorerUrls": [net["explorer"]],
        "nativeCurrency": net["currency"],
    }


def network_slug():
    """Short machine-readable network identifier (matches
    nftapp.models.Network's choices) for the network currently active in
    settings — this is what gets stamped onto an NFT row at mint time."""
    return "polygon-mainnet" if settings.POLYGON_NETWORK == "mainnet" else "polygon-amoy"


# --- Multi-standard contract registry ---------------------------------
# Every entry describes one deployed (or not-yet-deployed) contract this
# backend knows how to talk to. Only ERC-721 has an address configured
# today; adding ERC-1155 support later is: deploy
# contracts/MintiqueNFT1155.sol, set NFT_CONTRACT_ADDRESS_ERC1155 in
# .env, and it lights up here with no code changes to get_contract(),
# verify_mint_transaction(), or any of their callers in views.py.
CONTRACT_REGISTRY = {
    "erc721": {
        "address_setting": "NFT_CONTRACT_ADDRESS",
        "abi_path_setting": "NFT_CONTRACT_ABI_PATH",
        "mint_event": "MintiqueMinted",
    },
    "erc1155": {
        "address_setting": "NFT_CONTRACT_ADDRESS_ERC1155",
        "abi_path_setting": "NFT_CONTRACT_ABI_PATH_ERC1155",
        "mint_event": "MintiqueMinted1155",
    },
}


def get_contract_config(standard="erc721"):
    entry = CONTRACT_REGISTRY.get(standard)
    if entry is None:
        raise BlockchainError(f"Unknown token standard '{standard}'.")
    return entry


def contract_address_for(standard="erc721"):
    return getattr(settings, get_contract_config(standard)["address_setting"], "") or ""


def standard_enabled(standard="erc721"):
    return bool(web3_enabled() and contract_address_for(standard))


def _load_abi(standard="erc721"):
    abi_path = getattr(settings, get_contract_config(standard)["abi_path_setting"], None)
    if not abi_path:
        return None
    try:
        with open(abi_path) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("blockchain: no ABI file at %s for standard=%s", abi_path, standard)
        return None
    except (OSError, json.JSONDecodeError):
        logger.exception("blockchain: could not load contract ABI for standard=%s", standard)
        return None


def _inject_poa_middleware(w3):
    """Polygon (and most non-mainnet-Ethereum chains) are Proof-of-Authority
    chains: their blocks include an `extraData` field longer than plain
    Ethereum allows. Without this middleware, web3.py raises an internal
    parsing error (ExtraDataLengthError) the moment it touches a block or
    receipt on Polygon — which looks exactly like "transaction not found",
    even when the transaction actually succeeded on-chain. This must be
    injected on every Web3 instance that talks to Polygon.
    """
    try:
        from web3.middleware import ExtraDataToPOAMiddleware
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    except ImportError:
        try:
            # Older web3.py releases used this name instead.
            from web3.middleware import geth_poa_middleware
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except ImportError:
            logger.warning("blockchain: could not import POA middleware; Polygon reads may fail")
    return w3


def get_web3():
    if not web3_enabled():
        return None
    return _inject_poa_middleware(Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL)))


def get_web3_readonly():
    """A Web3 instance for read-only RPC calls that don't touch our own
    contract — e.g. `get_native_balance()`. Unlike `get_web3()`, this only
    needs the web3 package installed and an RPC URL (POLYGON_RPC_URL
    always has a public default — see settings.POLYGON_NETWORKS), not
    NFT_CONTRACT_ADDRESS configured, so wallet balance lookups work even
    before a contract is deployed.
    """
    if Web3 is None:
        return None
    return _inject_poa_middleware(Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL)))


def get_native_balance(address):
    """Live on-chain POL/MATIC balance for `address` on the active Polygon
    network, as a float — a plain read-only RPC call, no gas/signing
    involved. Returns None (never raises) if web3 isn't installed, the
    address is malformed, or the RPC call fails, so callers can treat
    "unavailable" and "zero balance" differently.
    """
    w3 = get_web3_readonly()
    if not w3:
        return None
    try:
        checksum_address = Web3.to_checksum_address(address)
    except (ValueError, TypeError):
        logger.info("blockchain: %r is not a valid address for a balance lookup", address)
        return None
    try:
        wei = w3.eth.get_balance(checksum_address)
    except Exception:
        logger.exception("blockchain: failed to fetch native balance for %s", address)
        return None
    return float(Web3.from_wei(wei, "ether"))


def get_contract(standard="erc721"):
    w3 = get_web3()
    abi = _load_abi(standard)
    address = contract_address_for(standard)
    if not w3 or not abi or not address:
        return None
    try:
        checksum_address = Web3.to_checksum_address(address)
    except ValueError:
        logger.error("blockchain: NFT_CONTRACT_ADDRESS for standard=%s is not a valid address: %r", standard, address)
        return None
    return w3.eth.contract(address=checksum_address, abi=abi)


def explorer_tx_url(tx_hash):
    if not tx_hash:
        return ""
    return f"{settings.POLYGON_ACTIVE_NETWORK['explorer']}/tx/{tx_hash}"


def explorer_token_url(token_id, standard="erc721"):
    if token_id is None:
        return ""
    return f"{settings.POLYGON_ACTIVE_NETWORK['explorer']}/token/{contract_address_for(standard)}?a={token_id}"


def verify_mint_transaction(tx_hash, expected_to_address=None, standard="erc721"):
    """Confirm `tx_hash` is a successful, mined transaction against the
    contract for `standard`, and extract the on-chain tokenId from its
    mint event log.

    Returns a dict {"confirmed": bool, "onchain_token_id": int|None,
    "to": str|None, "error": str|None} — "confirmed" is False (never
    raised) for anything that can't be verified, so callers can decide
    how strict to be; "error" carries a human-readable reason when
    verification fails, for surfacing to the user.
    """
    result = {"confirmed": False, "onchain_token_id": None, "to": None, "error": None}
    contract = get_contract(standard)
    w3 = get_web3()
    if not contract or not w3:
        result["error"] = "On-chain verification isn't configured for this network/standard."
        return result

    if not tx_hash or not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
        result["error"] = "That doesn't look like a valid transaction hash."
        return result

    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception:
        logger.info("blockchain: tx %s not yet mined or not found", tx_hash)
        result["error"] = "Transaction not found or not yet mined — it may still be pending."
        return result

    if receipt is None:
        result["error"] = "Transaction not found."
        return result
    if receipt.status != 1:
        result["error"] = "Transaction reverted on-chain."
        return result

    try:
        mint_event = getattr(contract.events, get_contract_config(standard)["mint_event"])
        events = mint_event().process_receipt(receipt)
    except Exception:
        logger.exception("blockchain: failed to parse logs for tx %s", tx_hash)
        result["error"] = "Could not parse the mint event from this transaction's logs."
        return result

    if not events:
        result["error"] = "Transaction was mined, but no mint event was found in its logs."
        return result

    args = events[0]["args"]
    result["confirmed"] = True
    result["onchain_token_id"] = int(args["tokenId"])
    result["to"] = args["to"]

    if expected_to_address and args["to"].lower() != expected_to_address.lower():
        result["confirmed"] = False
        result["error"] = "Minted token's recipient does not match the connected wallet."

    return result


def build_confirmed_mint_fields(nft, tx_hash, wallet_address, verification, standard="erc721"):
    """Assemble the dict of NFT field updates for a just-confirmed
    on-chain mint. Centralizing this (instead of setting each field
    inline in the view) is what keeps `views.confirm_onchain_mint_view`
    and any future standard-specific confirm flow (ERC-1155 batch mint,
    etc.) from silently drifting on which fields get saved.
    """
    from django.utils import timezone

    from .models import MintStatus

    fields = {
        "mint_status": MintStatus.CONFIRMED,
        "polygon_tx_hash": tx_hash,
        "contract_address": contract_address_for(standard),
        "network": network_slug(),
        "chain_id": settings.POLYGON_CHAIN_ID,
        "minter_wallet_address": wallet_address,
        "minted_at": timezone.now(),
        "mint_error": "",
        "token_standard": standard,
    }
    if nft.ipfs_image_cid:
        from . import ipfs_utils
        fields["image_uri"] = ipfs_utils.to_ipfs_uri(nft.ipfs_image_cid)
    if nft.ipfs_metadata_cid:
        from . import ipfs_utils
        fields["metadata_uri"] = ipfs_utils.to_ipfs_uri(nft.ipfs_metadata_cid)
    onchain_token_id = verification.get("onchain_token_id")
    if onchain_token_id is not None:
        fields["onchain_token_id"] = onchain_token_id
    return fields