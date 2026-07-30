// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/token/common/ERC2981.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title MintiqueNFT
/// @notice ERC-721 contract backing Mintique's on-chain minting on Polygon.
/// Each Mintique listing already carries an off-chain UUID v4 `token_id`
/// (see nftapp.models.NFT) used as the platform's internal identifier and
/// a content hash of the artwork; this contract is the on-chain mirror of
/// that same mint event. Token metadata (name, image, description, the
/// Mintique UUID, and the content hash) lives on IPFS — `tokenURI` simply
/// points at the pinned `ipfs://<CID>` metadata JSON built by
/// nftapp.ipfs_utils.build_token_metadata, so the on-chain token and the
/// Mintique database record always resolve to the exact same metadata.
contract MintiqueNFT is ERC721URIStorage, ERC2981, Ownable {
    /// @dev Auto-incrementing on-chain token id. Independent from
    /// Mintique's own UUID v4 token_id, which is embedded in the IPFS
    /// metadata instead (an ERC-721 tokenId must be a uint256 counter,
    /// not a UUID).
    uint256 private _nextTokenId;

    /// @notice Emitted whenever a Mintique-originated NFT is minted, so
    /// off-chain indexers can cheaply correlate an on-chain tokenId back
    /// to the platform's own UUID without re-parsing IPFS metadata.
    event MintiqueMinted(uint256 indexed tokenId, address indexed to, string mintiqueTokenId, string tokenURI);

    constructor(address initialOwner)
        ERC721("Mintique", "MNTQ")
        Ownable(initialOwner)
    {
        // Default royalty: 2.5% to the contract owner (platform treasury),
        // overridden per-token below whenever a creator sets their own
        // royalty percentage on Mintique at mint time.
        _setDefaultRoyalty(initialOwner, 250);
    }

    /// @notice Mint a new Mintique NFT to `to`, pointing at IPFS metadata.
    /// @param to Recipient wallet address (the minting user's connected
    ///        MetaMask wallet).
    /// @param uri `ipfs://<CID>` URI of the metadata JSON pinned to IPFS.
    /// @param mintiqueTokenId The UUID v4 token_id already assigned to this
    ///        NFT in Mintique's own database, kept here purely for
    ///        indexing/cross-reference — the source of truth for it stays
    ///        the Mintique database.
    /// @param royaltyBps Resale royalty in basis points (100 = 1%), taken
    ///        from the creator's `royalty_percentage` field.
    function mintNFT(
        address to,
        string memory uri,
        string memory mintiqueTokenId,
        uint96 royaltyBps
    ) public returns (uint256) {
        uint256 tokenId = _nextTokenId++;
        _safeMint(to, tokenId);
        _setTokenURI(tokenId, uri);
        if (royaltyBps > 0) {
            _setTokenRoyalty(tokenId, to, royaltyBps);
        }
        emit MintiqueMinted(tokenId, to, mintiqueTokenId, uri);
        return tokenId;
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
