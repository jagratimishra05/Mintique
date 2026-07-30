// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC1155/extensions/ERC1155URIStorage.sol";
import "@openzeppelin/contracts/token/ERC1155/extensions/ERC1155Supply.sol";
import "@openzeppelin/contracts/token/common/ERC2981.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title MintiqueNFT1155
/// @notice ERC-1155 companion to MintiqueNFT.sol (ERC-721), for
/// multi-edition / multi-token drops on Polygon — e.g. a creator
/// minting 100 copies of the same artwork as one token id, instead of
/// 100 separate ERC-721 tokens. Deliberately a *separate* contract
/// rather than a rewrite of MintiqueNFT.sol: the two standards have
/// different transfer/balance semantics (ownerOf vs balanceOf), so
/// keeping them as sibling contracts sharing the same mint/metadata
/// conventions is simpler and safer than one contract trying to satisfy
/// both ABIs.
///
/// Mirrors MintiqueNFT.sol's non-custodial pattern: Mintique's backend
/// never holds a private key here either — the creator's own MetaMask
/// wallet signs and pays gas for `mintNFT`, and Django only records the
/// resulting transaction (see nftapp/blockchain.py's CONTRACT_REGISTRY
/// and nftapp/views.confirm_onchain_mint_view, both already written to
/// key off `token_standard` so wiring this contract in is a config
/// change, not a code change).
contract MintiqueNFT1155 is ERC1155URIStorage, ERC1155Supply, ERC2981, Ownable {
    /// @dev Auto-incrementing on-chain token id, independent from
    /// Mintique's own UUID v4 token_id embedded in the IPFS metadata —
    /// same convention as MintiqueNFT.sol.
    uint256 private _nextTokenId;

    /// @notice Emitted whenever a Mintique-originated multi-edition NFT
    /// is minted, mirroring MintiqueNFT.sol's `MintiqueMinted` event so
    /// off-chain indexers/verification code can treat both the same way.
    event MintiqueMinted1155(
        uint256 indexed tokenId, address indexed to, uint256 amount, string mintiqueTokenId, string tokenURI
    );

    constructor(address initialOwner) ERC1155("") Ownable(initialOwner) {
        // Default royalty: 2.5% to the contract owner (platform treasury),
        // overridden per-token below whenever a creator sets their own
        // royalty percentage on Mintique at mint time — same convention
        // as MintiqueNFT.sol.
        _setDefaultRoyalty(initialOwner, 250);
    }

    /// @notice Mint `amount` copies of a new Mintique multi-edition NFT
    /// to `to`, pointing at IPFS metadata.
    /// @param to Recipient wallet address (the minting user's connected
    ///        MetaMask wallet).
    /// @param amount Number of editions/copies to mint under this token id.
    /// @param uri `ipfs://<CID>` URI of the metadata JSON pinned to IPFS.
    /// @param mintiqueTokenId The UUID v4 token_id already assigned to
    ///        this NFT in Mintique's own database, kept here purely for
    ///        indexing/cross-reference.
    /// @param royaltyBps Resale royalty in basis points (100 = 1%), taken
    ///        from the creator's `royalty_percentage` field.
    function mintNFT(
        address to,
        uint256 amount,
        string memory uri,
        string memory mintiqueTokenId,
        uint96 royaltyBps
    ) public returns (uint256) {
        require(amount > 0, "MintiqueNFT1155: amount must be > 0");
        uint256 tokenId = _nextTokenId++;
        _mint(to, tokenId, amount, "");
        _setURI(tokenId, uri);
        if (royaltyBps > 0) {
            _setTokenRoyalty(tokenId, to, royaltyBps);
        }
        emit MintiqueMinted1155(tokenId, to, amount, mintiqueTokenId, uri);
        return tokenId;
    }

    function uri(uint256 tokenId) public view override(ERC1155URIStorage, ERC1155) returns (string memory) {
        return super.uri(tokenId);
    }

    function _update(address from, address to, uint256[] memory ids, uint256[] memory values)
        internal
        override(ERC1155, ERC1155Supply)
    {
        super._update(from, to, ids, values);
    }

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC1155, ERC2981)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }
}
