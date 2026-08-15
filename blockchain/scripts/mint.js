// Mint one NFT from the command line — useful for smoke-testing a
// deployment outside the Django/wallet flow. Usage:
//
//   CONTRACT_ADDRESS=0x... TO_ADDRESS=0x... METADATA_URI=ipfs://... \
//     npx hardhat run scripts/mint.js --network amoy
//
// tokenId is assigned by the contract itself (auto-incrementing
// _nextTokenId), so every mint gets a fresh, unique id with no
// coordination needed between callers.
const { ethers } = require("hardhat");

async function main() {
  const contractAddress = process.env.CONTRACT_ADDRESS;
  if (!contractAddress) throw new Error("Set CONTRACT_ADDRESS in the environment.");

  const [signer] = await ethers.getSigners();
  const toAddress = process.env.TO_ADDRESS || signer.address;
  const metadataUri = process.env.METADATA_URI || "ipfs://replace-with-real-metadata-cid";
  const mintiqueTokenId = process.env.MINTIQUE_TOKEN_ID || "0";
  const royaltyBps = process.env.ROYALTY_BPS || "0";

  const contract = await ethers.getContractAt("MintiqueNFT", contractAddress, signer);

  console.log(`Minting to ${toAddress} with metadataUri=${metadataUri} ...`);
  const tx = await contract.mintNFT(toAddress, metadataUri, mintiqueTokenId, royaltyBps);
  const receipt = await tx.wait();

  const mintedEvent = receipt.logs
    .map((log) => {
      try {
        return contract.interface.parseLog(log);
      } catch {
        return null;
      }
    })
    .find((parsed) => parsed && parsed.name === "MintiqueMinted");

  if (mintedEvent) {
    console.log(`Minted tokenId=${mintedEvent.args.tokenId.toString()} tx=${tx.hash}`);
  } else {
    console.log(`Mint transaction mined (tx=${tx.hash}) but event log wasn't found.`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
