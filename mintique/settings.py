"""
Django settings for the Mintique NFT platform.
"""
import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from a .env file at the project root (if present). This was
# already listed in requirements.txt but never actually loaded, so anything
# you set in a .env file (email credentials, secret key, etc.) was silently
# ignored before. Copy .env.example to .env and fill in real values.
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# SECURITY
# ---------------------------------------------------------------------------
# In production, load SECRET_KEY / DEBUG from environment variables and NEVER
# commit real secrets to source control.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-insecure-key-change-me-before-deploying"
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

# Django requires the full scheme+host here (not just ALLOWED_HOSTS) for
# CSRF-protected POSTs to work once you're behind Render's HTTPS proxy.
CSRF_TRUSTED_ORIGINS = [
    f"https://{h}" for h in ALLOWED_HOSTS if h not in ("127.0.0.1", "localhost")
]

# ---------------------------------------------------------------------------
# APPLICATIONS
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # Local apps
    "accounts",
    "nftapp",
    "walletapp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves static files reliably in ALL environments
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.LoginRateLimitMiddleware",  # simple brute-force throttle
]

ROOT_URLCONF = "mintique.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "walletapp.context_processors.wallet_context",
                "accounts.context_processors.auth_config",
            ],
        },
    },
]

WSGI_APPLICATION = "mintique.wsgi.application"

# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------
# Uses DATABASE_URL (auto-set by Render's Postgres add-on) when present,
# falling back to local SQLite for dev. SQLite is NOT persistent on
# Render's filesystem across deploys, so production must set DATABASE_URL.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    # Enforces: 8+ chars, at least one uppercase letter, one digit, and one
    # special character. Replaces the old MinimumLengthValidator +
    # NumericPasswordValidator combo, which only rejected all-digit
    # passwords and never actually required a digit, uppercase, or symbol —
    # so things like "password" or "abcdefgh" were accepted before.
    {"NAME": "accounts.validators.ComplexPasswordValidator", "OPTIONS": {"min_length": 8}},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "nftapp:dashboard"
LOGOUT_REDIRECT_URL = "home"

# ---------------------------------------------------------------------------
# SOCIAL / WALLET AUTH
# ---------------------------------------------------------------------------
# Google OAuth 2.0 — create credentials at https://console.cloud.google.com/apis/credentials
# (OAuth client type: "Web application", authorized redirect URI:
#  <your-domain>/accounts/google/callback/). Leave blank to disable the
# button gracefully (users see a "not configured yet" message instead of
# a broken flow).
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# WalletConnect Cloud project id — create one at https://cloud.walletconnect.com
# Leave blank to fall back to the built-in demo wallet flow (same simulated
# connection already used for MetaMask-less browsers elsewhere in the app).
WALLETCONNECT_PROJECT_ID = os.environ.get("WALLETCONNECT_PROJECT_ID", "")

# Session / cookie hardening
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # must be readable by JS if you submit via fetch with header
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 7 days
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

# Only force HTTPS cookies/redirects in production
if not DEBUG:
    # Without this, if you deploy behind a reverse proxy/load balancer that
    # terminates HTTPS for you (nginx, Render, Railway, Heroku, etc.), Django
    # never sees the request as HTTPS and SECURE_SSL_REDIRECT below causes an
    # infinite redirect loop — which looks exactly like a broken/unstyled
    # white page in the browser. Your proxy must forward this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ---------------------------------------------------------------------------
# I18N
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# STATIC / MEDIA
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise serves STATICFILES_DIRS directly, so CSS/JS load correctly even
# if `collectstatic` hasn't been run yet (dev) and even when DEBUG=False
# (this project's old urls.py only wired up static serving when DEBUG=True,
# which is why the site looked unstyled/white whenever DEBUG was off).
# Deliberately using the non-manifest storage (not
# CompressedManifestStaticFilesStorage) so the site keeps working even if
# `collectstatic` is never run — the manifest variant raises a 500 error on
# any page using {% static %} until its manifest file has been generated.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
WHITENOISE_USE_FINDERS = True  # let WhiteNoise find files in STATICFILES_DIRS without collectstatic

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# EMAIL
# ---------------------------------------------------------------------------
# Previously hardcoded to the console backend, which just prints emails to
# the terminal instead of sending them — that's why "verification"/"reset"
# emails were never actually arriving in anyone's inbox. Now it's driven by
# environment variables (via .env, see .env.example) and only falls back to
# console mode if no real SMTP credentials are configured, so local dev
# still works out of the box without crashing.
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")

if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
    EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "False") == "True"
else:
    # No real credentials set — emails print to the console instead of
    # failing, so `runserver` still works, but you'll never get a real inbox
    # delivery until EMAIL_HOST_USER / EMAIL_HOST_PASSWORD are set in .env.
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Mintique <no-reply@mintique.io>")

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
# Every place that sends email (registration, verification resend, password
# reset, contact form) wraps send_mail() in try/except and calls
# logger.exception() on failure. Without a LOGGING config those exceptions
# were swallowed entirely — the person saw a friendly error message (or,
# before the contact-form fix, no error at all) but nothing was ever
# recorded anywhere, making the "email doesn't actually arrive" bug
# impossible to diagnose. This sends warnings/errors to the console (visible
# via `runserver` / your process manager's logs) and also appends them to
# logs/mintique.log so failures are still there after the console scrolls
# away.
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "mintique.log",
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# MINTIQUE / PLATFORM SETTINGS
# ---------------------------------------------------------------------------
# Fixed demo swap rate: 1 ETH = X MNQ. In a real system this would come from
# a price oracle / liquidity pool contract.
MNQ_PER_ETH_RATE = 1500
SWAP_FEE_PERCENT = 0.3  # 0.3% platform fee on every swap
NEW_USER_MNQ_BONUS = 50  # sign-up bonus so users can try swapping immediately

# Demo/simulated USD price of 1 ETH — used only for the friendly "$" estimate
# shown at checkout and in the swap widget. Not a real price feed.
ETH_USD_RATE = 3200

# Fixed demo exchange rates: "how many units of this token equal 1 ETH".
# Every supported token in the swap + wallet ledger is priced against ETH so
# any token can be converted to any other token via ETH as the common base
# (received = amount / RATE[from] * RATE[to], minus the platform fee). In a
# real system these would come from a price oracle / liquidity pool
# contract instead of being hardcoded here.
CRYPTO_RATES_PER_ETH = {
    "ETH": 1,
    "MNQ": MNQ_PER_ETH_RATE,
    "BTC": 0.031,        # ~1 ETH ≈ 0.031 BTC
    "USDT": ETH_USD_RATE,
    "USDC": ETH_USD_RATE,
    "SOL": 22,            # ~1 ETH ≈ 22 SOL
}

# Display metadata for every token the wallet ledger + swap widget support.
CRYPTO_TOKENS = {
    "ETH": {"label": "Ethereum", "icon": "⟠"},
    "MNQ": {"label": "Mintique Token", "icon": "◆"},
    "BTC": {"label": "Bitcoin", "icon": "₿"},
    "USDT": {"label": "Tether USD", "icon": "₮"},
    "USDC": {"label": "USD Coin", "icon": "＄"},
    "SOL": {"label": "Solana", "icon": "◎"},
}

MESSAGE_TAGS = {
    10: "info", 20: "info", 25: "success", 30: "warning", 40: "danger",
}

# ---------------------------------------------------------------------------
# Polygon blockchain configuration
# ---------------------------------------------------------------------------
# Which Polygon network the platform mints/reads against. "amoy" is
# Polygon's public testnet (chain id 80002) — the safe default for
# development/staging. Switch POLYGON_NETWORK=mainnet (chain id 137) for
# production once a contract is deployed and verified there.
POLYGON_NETWORK = os.environ.get("POLYGON_NETWORK", "amoy")

POLYGON_NETWORKS = {
    "amoy": {
        "chain_id": 80002,
        "chain_id_hex": "0x13882",
        "name": "Polygon Amoy Testnet",
        "rpc_url": os.environ.get("POLYGON_AMOY_RPC_URL", "https://rpc-amoy.polygon.technology"),
        "explorer": "https://amoy.polygonscan.com",
        "currency": {"name": "POL", "symbol": "POL", "decimals": 18},
    },
    "mainnet": {
        "chain_id": 137,
        "chain_id_hex": "0x89",
        "name": "Polygon Mainnet",
        "rpc_url": os.environ.get("POLYGON_MAINNET_RPC_URL", "https://polygon-rpc.com"),
        "explorer": "https://polygonscan.com",
        "currency": {"name": "POL", "symbol": "POL", "decimals": 18},
    },
}
POLYGON_ACTIVE_NETWORK = POLYGON_NETWORKS[POLYGON_NETWORK]
POLYGON_RPC_URL = POLYGON_ACTIVE_NETWORK["rpc_url"]
POLYGON_CHAIN_ID = POLYGON_ACTIVE_NETWORK["chain_id"]

# Address of the deployed MintiqueNFT ERC-721 contract (see contracts/) on
# the active network above. Left blank until a contract is deployed — the
# platform falls back to its existing simulated/off-chain mint ledger
# whenever this is unset, so nothing breaks in dev without a contract.
NFT_CONTRACT_ADDRESS = os.environ.get("NFT_CONTRACT_ADDRESS", "")
NFT_CONTRACT_ABI_PATH = BASE_DIR / "contracts" / "MintiqueNFT.abi.json"
WEB3_ENABLED = bool(NFT_CONTRACT_ADDRESS)

# Optional ERC-1155 companion contract (contracts/MintiqueNFT1155.sol) —
# unset by default. See nftapp.blockchain.CONTRACT_REGISTRY: once this is
# set, ERC-1155 minting/verification lights up with no further code
# changes needed.
NFT_CONTRACT_ADDRESS_ERC1155 = os.environ.get("NFT_CONTRACT_ADDRESS_ERC1155", "")
NFT_CONTRACT_ABI_PATH_ERC1155 = BASE_DIR / "contracts" / "MintiqueNFT1155.abi.json"

# ---------------------------------------------------------------------------
# IPFS (via Pinata) configuration
# ---------------------------------------------------------------------------
# NFT media + metadata are pinned to IPFS so the tokenURI a minted contract
# points to is content-addressed and doesn't depend on Mintique's own
# servers staying up. Uses Pinata's pinning API (a JWT is all that's
# required — no wallet/gas needed to pin). IPFS uploads are skipped
# whenever no key is configured, so local dev works without one.
PINATA_JWT = os.environ.get("PINATA_JWT", "")
PINATA_API_URL = "https://api.pinata.cloud"
PINATA_GATEWAY_URL = os.environ.get("PINATA_GATEWAY_URL", "https://gateway.pinata.cloud/ipfs/")
IPFS_ENABLED = bool(PINATA_JWT)
