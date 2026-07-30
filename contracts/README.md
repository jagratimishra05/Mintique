# MintiqueNFT — ERC-721 contract (Polygon)

`MintiqueNFT.sol` is a standard OpenZeppelin-based ERC-721 (`ERC721URIStorage`
+ `ERC2981` royalties) contract. Mintique's backend never needs to hold a
private key or pay gas for minting — the connected user's MetaMask wallet
signs and pays for the `mintNFT` transaction directly, and Django only
records the resulting transaction hash (see `nftapp/blockchain.py` and
`nftapp/views.confirm_onchain_mint_view`).

## 1. Deploy (Remix — no local toolchain needed)

1. Open [remix.ethereum.org](https://remix.ethereum.org) and create
   `MintiqueNFT.sol`, pasting in this file's contents.
2. In the **File Explorer**, use Remix's OpenZeppelin import resolver (the
   `@openzeppelin/contracts/...` imports resolve automatically via
   `npm`/`unpkg` — no manual install needed) or `npm install
   @openzeppelin/contracts` if deploying via Hardhat/Foundry instead.
3. Compile with Solidity `0.8.20+`.
4. In **Deploy & Run Transactions**:
   - Environment: `Injected Provider - MetaMask`.
   - Network: switch MetaMask to **Polygon Amoy** testnet first (chain id
     `80002`; add it via [chainlist.org](https://chainlist.org) if it's not
     already in your wallet) — test there before mainnet.
   - Constructor arg `initialOwner`: your platform treasury wallet address.
   - Click **Deploy** and confirm in MetaMask. Get testnet POL from the
     [Polygon Amoy faucet](https://faucet.polygon.technology/) first.
5. Copy the deployed contract address into `NFT_CONTRACT_ADDRESS` in `.env`.

## 2. Verify on Polygonscan (optional but recommended)

Verify the source on [amoy.polygonscan.com](https://amoy.polygonscan.com)
(or polygonscan.com for mainnet) so buyers can inspect the contract.
Constructor args must match step 4 above.

## 3. Point Mintique at it

Set in `.env`:

```
POLYGON_NETWORK=amoy        # or "mainnet" once verified there
NFT_CONTRACT_ADDRESS=0xYourDeployedAddress
```

With `NFT_CONTRACT_ADDRESS` unset, Mintique's mint flow stays fully
off-chain/simulated (its original behavior) — nothing breaks. Once it's
set, the mint page also prompts the connected MetaMask wallet to sign the
real `mintNFT` transaction on Polygon (see `static/js/web3mint.js`) after
the artwork + metadata are pinned to IPFS.

## Files

- `MintiqueNFT.sol` — ERC-721 contract source (the only one deployed today).
- `MintiqueNFT.abi.json` — its ABI, consumed by both the Python backend
  (`nftapp/blockchain.py`, via web3.py) and the browser
  (`static/js/web3mint.js`, via ethers.js/MetaMask).
- `MintiqueNFT1155.sol` / `MintiqueNFT1155.abi.json` — optional ERC-1155
  companion contract for multi-edition drops. Not deployed by default.
- `interfaces/IERC4907.sol`, `interfaces/IERC5192.sol` — standard
  interfaces declared as documented extension points for rentable and
  soulbound NFTs respectively. Neither is implemented on-chain yet; see
  the docstring in each file for how a future contract would adopt it.

## Extensibility: adding a second (or third) standard

`nftapp/blockchain.py` keeps a small registry (`CONTRACT_REGISTRY`) that
maps a `token_standard` string (`"erc721"`, `"erc1155"`, ...) to a
contract address setting, an ABI path setting, and a mint-event name.
`nftapp/models.py`'s `NFT.token_standard` field records which entry a
given NFT was minted under.

To bring `MintiqueNFT1155.sol` online once it's needed:

1. Deploy it the same way as `MintiqueNFT.sol` (see below) — Remix,
   `Injected Provider - MetaMask`, same constructor arg.
2. Set `NFT_CONTRACT_ADDRESS_ERC1155` in `.env`.
3. Nothing else changes — `get_contract()`, `verify_mint_transaction()`,
   `confirm_onchain_mint_view`, and the ABI endpoint
   (`/contract-abi/?standard=erc1155`) all already read from the
   registry rather than hardcoding the ERC-721 contract.

ERC-2981 (royalties) is already live on both contracts via
`_setTokenRoyalty`/`_setDefaultRoyalty` — no extra wiring needed. ERC-4907
and ERC-5192 are interface-only today (see above); wiring either one in
means a new contract implementing the interface plus a `token_standard`
registry entry, following the same pattern.
