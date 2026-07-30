// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title ERC-5192 — Minimal Soulbound NFT interface
/// @notice Standard interface for declaring an ERC-721 token
/// non-transferable ("soulbound") — e.g. proof-of-attendance,
/// credentials, or membership badges that shouldn't be resellable.
/// Reference: https://eips.ethereum.org/EIPS/eip-5192
///
/// Not implemented on-chain yet. This interface is declared as the
/// documented extension point: when soulbound minting is needed, a new
/// contract (e.g. MintiqueNFTSoulbound.sol) implements this by
/// overriding ERC721's `_update`/transfer hooks to revert whenever
/// `locked(tokenId)` is true, and emits `Locked` right after `_safeMint`
/// in its own mint function. nftapp.models.NFT.is_soulbound already
/// exists as the off-chain mirror of that on-chain lock state, set by
/// the mint flow once a token from a soulbound-capable contract is
/// confirmed.
interface IERC5192 {
    /// @notice Emitted when a token is locked (made non-transferable).
    event Locked(uint256 tokenId);

    /// @notice Emitted when a token is unlocked (made transferable
    /// again) — implementations that mint permanently-soulbound tokens
    /// may simply never emit this.
    event Unlocked(uint256 tokenId);

    /// @notice Returns whether `tokenId` is locked (non-transferable).
    function locked(uint256 tokenId) external view returns (bool);
}
