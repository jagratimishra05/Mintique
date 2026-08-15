// Mintique — on-chain mint transaction signing (MetaMask + Polygon).
//
// Wallet *connection* (eth_requestAccounts) already lives in wallet.js.
// This file is the second, separate step: once an NFT's artwork +
// metadata are pinned to IPFS and a MintiqueNFT contract is configured
// server-side, the owner's connected MetaMask wallet signs and pays gas
// for the actual `mintNFT` transaction on Polygon — Mintique's backend
// never holds a private key. Uses ethers.js (loaded from CDN only on
// pages that need it — see nft_detail.html) to build the contract call.

async function ensurePolygonNetwork(network) {
  if (typeof window.ethereum === "undefined") {
    throw new Error("No wallet detected. Install MetaMask to mint on-chain.");
  }
  try {
    await window.ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: network.chainId }],
    });
  } catch (switchError) {
    // 4902 = chain not added to MetaMask yet — add it, then switching
    // is implicit.
    if (switchError.code === 4902) {
      await window.ethereum.request({
        method: "wallet_addEthereumChain",
        params: [network],
      });
    } else {
      throw switchError;
    }
  }
}

/**
 * Signs and sends the on-chain `mintNFT` transaction via the connected
 * MetaMask wallet, then reports the result back to Django so the NFT
 * record can be marked confirmed.
 *
 * @param {Object} cfg - onchain_mint_config_json from nft_detail_view.
 * @param {Function} onStatus - optional callback(message) for UI updates.
 */
async function mintOnChain(cfg, onStatus) {
  const status = onStatus || (() => {});
  if (typeof window.ethereum === "undefined") {
    showToast("Install MetaMask to mint this NFT on-chain.", "danger");
    return;
  }
  if (typeof ethers === "undefined") {
    showToast("Could not load the Web3 library — please refresh and try again.", "danger");
    return;
  }

  try {
    status("Requesting wallet connection…");
    const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
    const walletAddress = accounts[0];

    status("Switching to Polygon…");
    await ensurePolygonNetwork(cfg.network);

    status("Loading contract…");
    const abiResp = await fetch(cfg.contractAbiUrl);
    const abi = await abiResp.json();

    const provider = new ethers.BrowserProvider(window.ethereum);
    const signer = await provider.getSigner();
    const contract = new ethers.Contract(cfg.contractAddress, abi, signer);

    status("Confirm the transaction in MetaMask…");
    const tx = await contract.mintNFT(
      walletAddress,
      cfg.metadataUri,
      cfg.mintiqueTokenId,
      cfg.royaltyBps || 0
    );

    status("Waiting for confirmation on Polygon…");
    showToast("Transaction submitted — waiting for confirmation…", "info");
    const receipt = await tx.wait();

    status("Recording confirmation…");
    const res = await fetch(cfg.confirmUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: `tx_hash=${encodeURIComponent(receipt.hash)}&wallet_address=${encodeURIComponent(walletAddress)}`,
    });
    const data = await res.json();
    if (data.ok) {
      showToast("Minted on Polygon! 🎉", "success");
      setTimeout(() => window.location.reload(), 900);
    } else {
      showToast(data.error || "Mint transaction sent, but confirmation failed.", "warning");
    }
  } catch (err) {
    if (err && (err.code === 4001 || err.code === "ACTION_REJECTED")) {
      showToast("Mint transaction was cancelled.", "warning");
    } else {
      console.error(err);
      showToast("On-chain mint failed. Please try again.", "danger");
    }
  }
}
