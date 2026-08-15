// Mintique — wallet connection flow.
// Wallet connection is ONLY requested at the moment a wallet-gated action
// (mint / buy) is attempted — never at login or while just browsing.

let pendingForm = null;

function openWalletModal() {
  const modal = document.getElementById("walletModal");
  if (!modal) return;
  modal.classList.add("open");
  requestAnimationFrame(() => requestAnimationFrame(() => modal.classList.add("show")));
}
function closeWalletModal() {
  const modal = document.getElementById("walletModal");
  if (!modal) return;
  modal.classList.remove("show");
  document.getElementById("manualWalletInput")?.style.setProperty("display", "none");
  setTimeout(() => modal.classList.remove("open"), 300);
}

async function submitWalletAddress(address) {
  const res = await fetch("/wallet/connect/", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: `wallet_address=${encodeURIComponent(address)}`,
  });
  const data = await res.json();
  if (data.ok) {
    closeWalletModal();
    showToast(`Wallet connected: ${data.address.slice(0, 6)}…${data.address.slice(-4)}`, "success");
    document.body.dataset.walletConnected = "true";
    const badge = document.getElementById("walletBadgeSlot");
    if (badge) badge.textContent = `${data.address.slice(0, 6)}…${data.address.slice(-4)}`;

    if (pendingForm) {
      pendingForm.submit();
      pendingForm = null;
    } else {
      // Refresh so server-rendered wallet-gated content updates.
      setTimeout(() => window.location.reload(), 700);
    }
  } else {
    showToast(data.error || "Could not connect wallet.", "danger");
  }
}

// Official install/connect pages for wallets that aren't detected in the
// browser — clicking a wallet that isn't installed opens its real site in
// a new tab (same pattern most dApps use), instead of silently doing
// nothing or always falling back to the demo wallet.
const WALLET_REDIRECT_URLS = {
  metamask: "https://metamask.io/download/",
  coinbase: "https://www.coinbase.com/wallet/downloads",
  trust: "https://trustwallet.com/download",
};

function openWalletSite(url) {
  window.open(url, "_blank", "noopener,noreferrer");
}

async function connectMetaMask() {
  if (typeof window.ethereum === "undefined" || !window.ethereum.isMetaMask) {
    showToast("Opening MetaMask so you can connect…", "info");
    openWalletSite(WALLET_REDIRECT_URLS.metamask);
    return;
  }
  try {
    const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
    if (accounts && accounts[0]) {
      await submitWalletAddress(accounts[0]);
    }
  } catch (err) {
    showToast("Wallet connection was cancelled.", "warning");
  }
}

async function connectCoinbaseWallet() {
  // Real integration point: swap in @coinbase/wallet-sdk here. If Coinbase
  // Wallet isn't detected in-browser, open its real site/app in a new tab
  // so the person can install or launch it and connect from there.
  if (typeof window.ethereum !== "undefined" && window.ethereum.isCoinbaseWallet) {
    try {
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      if (accounts && accounts[0]) return submitWalletAddress(accounts[0]);
    } catch (err) {
      showToast("Wallet connection was cancelled.", "warning");
      return;
    }
  }
  showToast("Opening Coinbase Wallet so you can connect…", "info");
  openWalletSite(WALLET_REDIRECT_URLS.coinbase);
}

async function connectTrustWallet() {
  // Real integration point: swap in Trust Wallet's provider/SDK here. If
  // Trust Wallet isn't detected in-browser, open its real site/app in a
  // new tab so the person can install or launch it and connect from there.
  if (typeof window.ethereum !== "undefined" && window.ethereum.isTrust) {
    try {
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      if (accounts && accounts[0]) return submitWalletAddress(accounts[0]);
    } catch (err) {
      showToast("Wallet connection was cancelled.", "warning");
      return;
    }
  }
  showToast("Opening Trust Wallet so you can connect…", "info");
  openWalletSite(WALLET_REDIRECT_URLS.trust);
}

function connectWalletConnect() {
  const projectId = document.body.dataset.walletconnectProjectId;
  if (!projectId) {
    // No WALLETCONNECT_PROJECT_ID configured — fall back to the demo
    // wallet so the flow can still be tried end-to-end. Swap in the real
    // @walletconnect/ethereum-provider SDK once a project id is set.
    showToast("WalletConnect isn't configured yet — opening walletconnect.com…", "info");
    openWalletSite("https://walletconnect.com/");
    return;
  }
  showToast("Opening WalletConnect…", "info");
  // Real integration point: initialize EthereumProvider.init({ projectId, ... })
  // here, then call submitWalletAddress(accounts[0]) once connected. Until
  // then, still open the real site so the click always does something visible.
  openWalletSite("https://walletconnect.com/");
}

function connectDemoWallet() {
  // Generates a realistic-looking demo address so the flow can be tried
  // without a real browser wallet extension installed.
  const chars = "0123456789abcdef";
  let addr = "0x";
  for (let i = 0; i < 40; i++) addr += chars[Math.floor(Math.random() * chars.length)];
  submitWalletAddress(addr);
}

function showManualWalletInput() {
  document.getElementById("manualWalletInput").style.display = "block";
}

function submitManualWallet() {
  const input = document.getElementById("manualAddressField");
  const val = input.value.trim();
  if (val.length < 10) {
    showToast("Enter a valid wallet address.", "danger");
    return;
  }
  submitWalletAddress(val);
}

document.addEventListener("DOMContentLoaded", () => {
  // Gate any form/button marked data-wallet-gate: open the modal instead of
  // submitting/navigating until a wallet is connected.
  document.querySelectorAll("[data-wallet-gate]").forEach((el) => {
    const alreadyConnected = document.body.dataset.walletConnected === "true";
    if (alreadyConnected) return;

    if (el.tagName === "FORM") {
      el.addEventListener("submit", (e) => {
        if (document.body.dataset.walletConnected !== "true") {
          e.preventDefault();
          pendingForm = el;
          openWalletModal();
        }
      });
    } else {
      el.addEventListener("click", (e) => {
        if (document.body.dataset.walletConnected !== "true") {
          e.preventDefault();
          openWalletModal();
        }
      });
    }
  });

  // Auto-open if the server redirected us here because wallet was required.
  if (new URLSearchParams(window.location.search).get("wallet_required")) {
    openWalletModal();
  }
});
