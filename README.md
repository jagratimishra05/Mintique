# Mintique — NFT Minting, Marketplace & Swap Platform

A full-stack Django project: server-rendered HTML/CSS/JS frontend (Django templates —
no separate React build needed), with real authentication, a wallet-gated minting
flow, a marketplace, and a built-in ETH ⇄ MNQ token swap.

## Stack

- **Backend:** Python 3, Django 5/6
- **Database:** SQLite (swap `DATABASES` in `mintique/settings.py` for Postgres/MySQL in production)
- **Frontend:** Django Templates + vanilla CSS/JS (dark "Mintique" theme, no build step)
- **Images:** Pillow (for uploaded artwork + demo seed images)

## Project layout

```
mintique/
├── manage.py
├── requirements.txt
├── mintique/              # project settings/urls/wsgi/asgi
├── accounts/              # custom User model, register/login/profile, brute-force throttle
│   ├── models.py          # User (email/google/wallet auth_provider), LoginAttempt
│   ├── forms.py           # RegisterForm, EmailLoginForm, WalletAuthForm, ProfileForm
│   ├── views.py           # email + Google OAuth + wallet login, password reset, email verify
│   ├── urls.py
│   ├── context_processors.py   # exposes google/walletconnect config to templates
│   ├── middleware.py      # simple login rate-limiter
│   └── admin.py
├── nftapp/                # NFTs: mint, marketplace, detail, likes, buy
│   ├── models.py          # NFT (auto-generates MNQ-XXXX token IDs + content hash), Like
│   ├── forms.py           # MintNFTForm, MarketplaceFilterForm
│   ├── views.py           # dashboard, mint (wallet-gated), marketplace, detail, buy, collection
│   ├── management/commands/seed_demo.py   # `python manage.py seed_demo`
│   └── admin.py
├── walletapp/             # internal ledger wallet, token swap, transaction history
│   ├── models.py          # Wallet (ETH + MNQ balances), Transaction
│   ├── forms.py           # SwapForm, ConnectWalletForm
│   ├── views.py           # connect/disconnect wallet, swap, transaction history
│   ├── context_processors.py   # exposes wallet balance in the navbar everywhere
│   └── admin.py
├── templates/
│   ├── base.html          # navbar, toasts, footer — extended by every page
│   ├── home.html
│   ├── accounts/{login,register,profile}.html
│   ├── accounts/{forgot_password,password_reset_sent,password_reset_confirm,password_reset_complete}.html
│   ├── accounts/{verify_email_pending,_wallet_auth_modal}.html
│   ├── nftapp/{dashboard,mint,marketplace,nft_detail,my_collection}.html
│   └── walletapp/{swap,transactions,_wallet_modal}.html
└── static/
    ├── css/style.css      # entire design system (tokens, buttons, cards, forms, modal…)
    └── js/{main,wallet,auth,swap}.js
```

## Setup

```bash
python -m venv venv
source venv/bin/activate            # venv\Scripts\activate on Windows
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser    # for /admin/
python manage.py seed_demo          # optional: populates 6 demo NFTs + a demo creator
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`.

Demo login created by `seed_demo`: **demo@mintique.io / DemoPass123!**

## Feature overview

### Authentication & accounts
- Custom `User` model, email as the login identifier (not username)
- **Four sign-in methods, all working end-to-end:**
  - **Email/password** — registration with password confirmation + Django's
    built-in password validators (min length, common-password check,
    similarity check, all-numeric check)
  - **Google OAuth** — standard authorization-code flow (`accounts/views.py`:
    `google_login_view` / `google_callback_view`). Configure
    `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` env vars (redirect URI:
    `<domain>/accounts/google/callback/`); the button shows a clear
    "not configured yet" message instead of failing silently if unset.
  - **MetaMask** — real `window.ethereum` browser-wallet connection; first
    connect auto-creates an account tied to that address
  - **WalletConnect** — same login flow; falls back to the built-in demo
    wallet if `WALLETCONNECT_PROJECT_ID` isn't set, so the flow is always
    testable without external credentials
- **Forgot / reset password** — Django's built-in token-based reset flow with
  dark-themed templates (`accounts/forgot_password.html` → email → 
  `password_reset_confirm.html` → done)
- **Verify email** — every new email/password account gets a verification
  link; `/accounts/verify-email/` shows status + a resend button, and a
  dismissible banner nudges unverified users site-wide
- Login/logout, "welcome back" toast messages
- Simple brute-force throttle (`accounts/middleware.py`): 5 failed attempts on one
  email within 10 minutes blocks further tries — swap for `django-axes` in production
- Editable profile (name, bio, avatar)
- Session/CSRF hardening in `settings.py` (HttpOnly, SameSite, HSTS in production, etc.)

**New environment variables** (all optional — features degrade gracefully when unset):
```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
WALLETCONNECT_PROJECT_ID=
```

### Dashboard
- Available immediately after login — **no wallet required** to view it
- Live stats: NFTs minted, total earnings, listed items, collectors
- Recent NFTs + recent transaction activity

### Minting — wallet-gated
- Wallet connection is **only requested at the moment you try to mint or buy**,
  never at registration/login/browsing
- `static/js/wallet.js` intercepts the mint/buy form submit and opens a connect
  modal with three options: real browser wallet (MetaMask `window.ethereum`),
  a one-click demo wallet (for reviewers without an extension installed), or
  manual address entry
- Server-side, `nftapp.views.wallet_required` is a safety net that re-checks the
  wallet on POST even if JS were bypassed
- On mint: drag-and-drop upload with live preview, client + server-side file
  type/size validation, auto-generated unique `MNQ-XXXX-XXXX-XXXX-XXXX` token ID
  and a SHA-256 content hash simulating the "cryptographic hashing" step

### Marketplace
- Search, category filter, sort (newest / price / most liked), pagination
- NFT detail page: like/unlike, buy now (wallet-gated), ownership transfer on
  purchase, "sold" vs "listed" state

### Wallet & token swap
- Every user gets an internal ledger `Wallet` (simulated ETH balance + platform
  MNQ token balance) — new users get a starter MNQ bonus to try swapping right away
- Swap widget: type an amount, live-estimated conversion (JS), fixed demo rate
  + platform fee (both configurable in `settings.py`), swap direction toggle
- All mints/buys/sells/swaps/wallet-connects are logged to `Transaction` with a
  fake but unique `tx_hash`, visible in the dashboard and a full history page

### Security notes / what's simulated vs. real
- Wallet connections and ETH/MNQ balances are an **internal ledger**, not a real
  blockchain — this keeps the whole flow runnable without a live Web3 provider,
  gas fees, or a deployed smart contract. Swapping in `web3.py` + a real contract
  is a drop-in replacement for `walletapp/models.py` + `views.py` once you're
  ready to go on-chain.
- Email is sent via Django's console backend in dev — point `EMAIL_BACKEND` at
  SMTP/SES/SendGrid for real delivery (e.g. verification emails).
- The login throttle is DB-backed for portability; use Redis + `django-axes`
  or `django-ratelimit` for production-grade protection.

## Suggested next steps for production
- Real email verification gate before allowing minting
- 2FA (field already on the User model: `two_factor_enabled`)
- Real Web3 integration (web3.py) + smart contract for on-chain minting
- Object storage (S3) for `MEDIA_ROOT` instead of local disk
- Postgres + Redis (cache/rate-limit) instead of SQLite
- Celery for async email/notification sending
