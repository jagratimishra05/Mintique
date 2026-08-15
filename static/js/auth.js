// Mintique — auth page wallet connection (login/register).
// Distinct from wallet.js's post-login "connect before minting" gate: this
// flow logs the user IN (creating an account on first connect) rather than
// linking a wallet to an already-authenticated session.

function openAuthWalletModal() {
  const modal = document.getElementById("authWalletModal");
  if (!modal) return;
  modal.classList.add("open");
  requestAnimationFrame(() => requestAnimationFrame(() => modal.classList.add("show")));
}
function closeAuthWalletModal() {
  const modal = document.getElementById("authWalletModal");
  if (!modal) return;
  modal.classList.remove("show");
  document.getElementById("authManualWalletInput")?.style.setProperty("display", "none");
  setTimeout(() => modal.classList.remove("open"), 300);
}

function submitAuthWallet(address) {
  const input = document.getElementById("walletAuthAddress");
  const form = document.getElementById("walletAuthForm");
  if (!input || !form) return;
  input.value = address;
  form.submit();
}

// Official install/connect pages for wallets that aren't detected in the
// browser — clicking a wallet that isn't installed opens its real site in
// a new tab (same pattern most dApps use), instead of silently doing
// nothing or always falling back to the demo wallet.
const AUTH_WALLET_REDIRECT_URLS = {
  metamask: "https://metamask.io/download/",
  coinbase: "https://www.coinbase.com/wallet/downloads",
  trust: "https://trustwallet.com/download",
};

function openAuthWalletSite(url) {
  window.open(url, "_blank", "noopener,noreferrer");
}

async function authConnectMetaMask() {
  if (typeof window.ethereum === "undefined" || !window.ethereum.isMetaMask) {
    showToast("Opening MetaMask so you can connect…", "info");
    openAuthWalletSite(AUTH_WALLET_REDIRECT_URLS.metamask);
    return;
  }
  try {
    const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
    if (accounts && accounts[0]) submitAuthWallet(accounts[0]);
  } catch (err) {
    showToast("Wallet connection was cancelled.", "warning");
  }
}

async function authConnectCoinbaseWallet() {
  if (typeof window.ethereum !== "undefined" && window.ethereum.isCoinbaseWallet) {
    try {
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      if (accounts && accounts[0]) return submitAuthWallet(accounts[0]);
    } catch (err) {
      showToast("Wallet connection was cancelled.", "warning");
      return;
    }
  }
  showToast("Opening Coinbase Wallet so you can connect…", "info");
  openAuthWalletSite(AUTH_WALLET_REDIRECT_URLS.coinbase);
}

async function authConnectTrustWallet() {
  if (typeof window.ethereum !== "undefined" && window.ethereum.isTrust) {
    try {
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      if (accounts && accounts[0]) return submitAuthWallet(accounts[0]);
    } catch (err) {
      showToast("Wallet connection was cancelled.", "warning");
      return;
    }
  }
  showToast("Opening Trust Wallet so you can connect…", "info");
  openAuthWalletSite(AUTH_WALLET_REDIRECT_URLS.trust);
}

function authConnectDemoWallet() {
  const chars = "0123456789abcdef";
  let addr = "0x";
  for (let i = 0; i < 40; i++) addr += chars[Math.floor(Math.random() * chars.length)];
  submitAuthWallet(addr);
}

function authConnectWalletConnect() {
  const projectId = document.body.dataset.walletconnectProjectId;
  if (!projectId) {
    // No WALLETCONNECT_PROJECT_ID configured — open walletconnect.com so the
    // person can still see/use the real thing, instead of silently doing
    // nothing or always falling back to the demo wallet.
    showToast("WalletConnect isn't configured yet — opening walletconnect.com…", "info");
    openAuthWalletSite("https://walletconnect.com/");
    return;
  }
  showToast("Opening WalletConnect…", "info");
  // Real integration point: initialize EthereumProvider.init({ projectId, ... })
  // here, then call submitAuthWallet(accounts[0]) once connected. Until then,
  // still open the real site so the click always does something visible.
  openAuthWalletSite("https://walletconnect.com/");
}

function showAuthManualWalletInput() {
  const el = document.getElementById("authManualWalletInput");
  if (el) el.style.display = "block";
}

function submitAuthManualWallet() {
  const input = document.getElementById("authManualAddressField");
  if (!input) return;
  const val = input.value.trim();
  if (val.length < 10) {
    showToast("Enter a valid wallet address.", "danger");
    return;
  }
  submitAuthWallet(val);
}
