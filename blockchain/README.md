# Mintique smart contracts

This is the Hardhat project for `MintiqueNFT.sol`, the ERC-721 contract
backing the Mintique marketplace. It was written to match the interface
Mintique's Django backend and frontend **already expect**:

- `nftapp/blockchain.py` reads the deployed address from
  `settings.NFT_CONTRACT_ADDRESS` and verifies mints by looking for a
  `MintiqueMinted(to, tokenId, ...)` event in the transaction receipt.
- `static/js/web3mint.js` calls
  `contract.mintNFT(walletAddress, metadataUri, mintiqueTokenId, royaltyBps)`
  directly from the user's connected MetaMask wallet — Mintique's backend
  never holds a private key or pays gas.
- `nftapp/views.py` serves the ABI to the browser from
  `contracts/MintiqueNFT.abi.json` at the repo root (one level up from
  this folder) via `settings.NFT_CONTRACT_ABI_PATH`.

So minting is a **public, free (gas-only) self-mint**: any connected
wallet can call `mintNFT` for itself. tokenIds are assigned by the
contract's own auto-incrementing counter, so they're unique by
construction — no coordination needed between callers.

## 1. Install

```bash
cd blockchain
npm install
cp .env.example .env   # fill in PRIVATE_KEY / RPC URLs before deploying anywhere but a local network
```

## 2. Compile

```bash
npm run compile
```

## 3. Unit tests

`test/MintiqueNFT.test.js` covers minting (including uniqueness of
tokenIds across many mints and input validation), transfers (owner,
approved-operator, and unauthorized-caller cases), and ownership /
access control (Ownable-gated admin functions, ERC-165/ERC-2981
interface detection).

```bash
npm test
```

## 4. Run tests locally

Either `npm test` (spins up an ephemeral in-process network per run) or,
for an interactive local chain you can point MetaMask at:

```bash
npm run node                 # terminal 1 — persistent local JSON-RPC node on :8545
npm run deploy:localhost      # terminal 2 — deploys to that node
```

## 5. Deploy to a testnet (Sepolia or Polygon Amoy)

Fill in `.env` first (`PRIVATE_KEY` for a **throwaway deploy wallet**,
funded with testnet ETH/POL from a faucet, plus an RPC URL from
Alchemy/Infura or a public endpoint).

```bash
npm run deploy:sepolia
# or, to match Mintique's production network (Polygon):
npm run deploy:amoy
```

The deploy script (`scripts/deploy.js`):
1. Deploys the contract with `name`, `symbol`, `owner`, `maxSupply` from `.env`.
2. Writes the compiled ABI to `../contracts/MintiqueNFT.abi.json` — the
   exact path Django already reads from.
3. Prints the deployed address to paste into Django's own `.env` as
   `NFT_CONTRACT_ADDRESS`.

After deploying, update Django's `.env`:

```
NFT_CONTRACT_ADDRESS=0x...      # printed by the deploy script
POLYGON_NETWORK=testnet          # or mainnet, once you deploy there
```

and restart the Django server — `WEB3_ENABLED` picks up automatically
since it's just `bool(NFT_CONTRACT_ADDRESS)`.

## 6. Mint NFTs with unique tokenIds

In normal operation this happens from the browser: a user mints an NFT
in Mintique's UI, `web3mint.js` pins metadata to IPFS via the Django
backend, then calls `mintNFT` through their own connected wallet. The
contract's internal counter (`_nextTokenId`) guarantees every mint gets
a fresh, unique id — see the "assigns strictly increasing, unique
tokenIds across many mints" test.

To mint from the command line instead (e.g. to smoke-test a fresh
deployment):

```bash
CONTRACT_ADDRESS=0x... TO_ADDRESS=0x... METADATA_URI=ipfs://... \
  npx hardhat run scripts/mint.js --network amoy
```

## 7. Frontend integration

Already wired up in this repo — nothing new to build:

- `static/js/web3mint.js` builds an `ethers.Contract` from the ABI
  served at `/contract/abi/` and the address baked into
  `onchain_mint_config_json` (see `nftapp/views.py`), then calls
  `mintNFT` through the user's MetaMask wallet.
- On success, the tx hash is reported back to Django
  (`confirm_onchain_mint_view`), which calls
  `blockchain.verify_mint_transaction()` — a read-only `web3.py` call
  that re-parses the `MintiqueMinted` event from the mined receipt
  before trusting the mint — and stamps `onchain_token_id`,
  `contract_address`, `chain_id`, etc. onto the `NFT` row.

If you ever want a non-Django/pure Ethers.js or Viem example to test
the contract in isolation, `scripts/mint.js` is exactly that: connect →
build contract instance from the ABI → call `mintNFT` → wait for
receipt → read the emitted `tokenId`.

## Contract summary

| Function | Access | Notes |
|---|---|---|
| `mintNFT(to, metadataUri, mintiqueTokenId, royaltyBps)` | public | Self-mint, gas-only, returns the new `tokenId` |
| `tokenURI(tokenId)` | public view | Per-token metadata URI (ERC721URIStorage) |
| `royaltyInfo(tokenId, salePrice)` | public view | ERC-2981 |
| `updateRoyalty(tokenId, receiver, feeBps)` | `onlyOwner` | Admin override, doesn't touch ownership |
| `totalMinted()` | public view | Convenience counter |

`maxSupply` is set at deploy time (constructor arg); `0` means uncapped.
