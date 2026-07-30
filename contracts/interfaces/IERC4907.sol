// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title ERC-4907 — Rental NFT interface
/// @notice Standard interface for adding a time-limited "user" role to an
/// ERC-721 token, distinct from ownership — lets an owner "rent out" an
/// NFT (e.g. lend game-item or membership access) without transferring
/// title. Reference: https://eips.ethereum.org/EIPS/eip-4907
///
/// Not implemented on-chain yet. This interface is declared as the
/// documented extension point: when rentable NFTs are needed, a new
/// contract (e.g. MintiqueNFTRentable.sol) implements this alongside
/// ERC721URIStorage, and nftapp.models.NFT.standard_metadata already has
/// a place to cache the current renter/expiry off-chain
/// (`{"rental_user": "0x..", "rental_expires": <unix ts>}`) for fast
/// reads without an RPC call on every page view.
interface IERC4907 {
    /// @dev Emitted when the "user" of an NFT or the "expires" of the
    /// "user" is changed. The zero address for user indicates that
    /// there is no user address.
    event UpdateUser(uint256 indexed tokenId, address indexed user, uint64 expires);

    /// @notice Set the user and expiry date of a token.
    /// @dev The zero address indicates there is no user.
    function setUser(uint256 tokenId, address user, uint64 expires) external;

    /// @notice Get the user address of a token.
    /// @dev The zero address indicates that there is no user or the
    /// user's rental period has expired.
    function userOf(uint256 tokenId) external view returns (address);

    /// @notice Get the user expiry date (unix timestamp) of a token.
    function userExpires(uint256 tokenId) external view returns (uint256);
}
