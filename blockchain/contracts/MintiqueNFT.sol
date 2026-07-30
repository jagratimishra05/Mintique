// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {ERC721URIStorage} from "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import {ERC2981} from "@openzeppelin/contracts/token/common/ERC2981.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title MintiqueNFT
/// @notice ERC-721 contract backing Mintique's marketplace. Minting is a
/// public, self-service call signed by the minter's own wallet (Mintique's
/// backend never holds a private key or pays gas — see static/js/web3mint.js
/// and nftapp/blockchain.py). Each token carries its own metadata URI
/// (pinned to IPFS before the mint call) and an optional ERC-2981 royalty.
///
/// `mintiqueTokenId` is Mintique's own Django `NFT.pk`, emitted in the mint
/// event purely so the backend's `verify_mint_transaction()` can be
/// extended later to cross-check it — the source of truth for the real
/// tokenId is always the on-chain `tokenId` returned/emitted here.
contract MintiqueNFT is ERC721URIStorage, ERC2981, Ownable, ReentrancyGuard {
    /// @notice Emitted on every successful mint. `blockchain.py`'s
    /// verify_mint_transaction() reads `tokenId` and `to` from this event
    /// to confirm a client-reported tx hash before trusting it.
    event MintiqueMinted(
        address indexed to,
        uint256 indexed tokenId,
        uint256 indexed mintiqueTokenId,
        string metadataUri,
        uint256 royaltyBps
    );

    /// @notice Optional hard cap on total supply. 0 = uncapped.
    uint256 public immutable maxSupply;

    /// @dev Upper bound so a bad royaltyBps value can't silently exceed
    /// what marketplaces (and ERC-2981) treat as 100%.
    uint96 private constant MAX_ROYALTY_BPS = 10_000;

    uint256 private _nextTokenId = 1;

    constructor(
        string memory name_,
        string memory symbol_,
        address initialOwner,
        uint256 maxSupply_
    ) ERC721(name_, symbol_) Ownable(initialOwner) {
        maxSupply = maxSupply_;
    }

    /// @notice Mint a new token to `to`, pointing at `metadataUri`
    /// (already pinned to IPFS), with an optional per-token royalty.
    /// @dev Public and unpriced by design, matching the existing frontend
    /// call (`contract.mintNFT(walletAddress, cfg.metadataUri,
    /// cfg.mintiqueTokenId, cfg.royaltyBps || 0)` in web3mint.js) — the
    /// connected wallet only ever pays network gas, never a mint price.
    /// @param to Recipient address (the connected wallet minting for itself).
    /// @param metadataUri IPFS/HTTPS URI of the token's JSON metadata.
    /// @param mintiqueTokenId Mintique's internal NFT.pk, for event indexing only.
    /// @param royaltyBps Secondary-sale royalty in basis points (0-10000), 0 = none.
    /// @return tokenId The newly minted on-chain token id.
    function mintNFT(
        address to,
        string calldata metadataUri,
        uint256 mintiqueTokenId,
        uint256 royaltyBps
    ) external nonReentrant returns (uint256 tokenId) {
        require(to != address(0), "MintiqueNFT: mint to zero address");
        require(bytes(metadataUri).length > 0, "MintiqueNFT: empty metadata URI");
        require(royaltyBps <= MAX_ROYALTY_BPS, "MintiqueNFT: royalty exceeds 100%");

        tokenId = _nextTokenId++;
        if (maxSupply != 0) {
            require(tokenId <= maxSupply, "MintiqueNFT: max supply reached");
        }

        _safeMint(to, tokenId);
        _setTokenURI(tokenId, metadataUri);

        if (royaltyBps > 0) {
            _setTokenRoyalty(tokenId, to, uint96(royaltyBps));
        }

        emit MintiqueMinted(to, tokenId, mintiqueTokenId, metadataUri, royaltyBps);
    }

    /// @notice Total tokens minted so far.
    function totalMinted() external view returns (uint256) {
        return _nextTokenId - 1;
    }

    /// @notice Owner-only escape hatch to update a token's royalty terms
    /// after mint (e.g. creator changing payout address). Does not touch
    /// tokenURI or ownership.
    function updateRoyalty(uint256 tokenId, address receiver, uint96 feeBps) external onlyOwner {
        require(feeBps <= MAX_ROYALTY_BPS, "MintiqueNFT: royalty exceeds 100%");
        _setTokenRoyalty(tokenId, receiver, feeBps);
    }

    // --- Required overrides for multiple inheritance -----------------

    function tokenURI(uint256 tokenId)
        public
        view
        override(ERC721URIStorage)
        returns (string memory)
    {
        return super.tokenURI(tokenId);
    }

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721URIStorage, ERC2981)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }
}
