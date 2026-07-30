const fs = require("fs");
const path = require("path");
const { ethers, network } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log(`Deploying MintiqueNFT to "${network.name}" from ${deployer.address}...`);

  const name = process.env.NFT_NAME || "Mintique";
  const symbol = process.env.NFT_SYMBOL || "MNTQ";
  const owner = process.env.NFT_OWNER_ADDRESS || deployer.address;
  const maxSupply = process.env.NFT_MAX_SUPPLY || "0";

  const MintiqueNFT = await ethers.getContractFactory("MintiqueNFT");
  const contract = await MintiqueNFT.deploy(name, symbol, owner, maxSupply);
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log(`MintiqueNFT deployed at: ${address}`);
  console.log(`  name=${name} symbol=${symbol} owner=${owner} maxSupply=${maxSupply}`);

  // --- Export the ABI to the exact path Django's nftapp/blockchain.py
  // reads via settings.NFT_CONTRACT_ABI_PATH (contracts/MintiqueNFT.abi.json
  // at the repo root, one level up from this blockchain/ project). ---
  const artifact = await hre_artifacts_readSafe();
  const repoRoot = path.resolve(__dirname, "..", "..");
  const outDir = path.join(repoRoot, "contracts");
  const outFile = path.join(outDir, "MintiqueNFT.abi.json");
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(outFile, JSON.stringify(artifact.abi, null, 2));
  console.log(`ABI written to: ${outFile}`);

  console.log("\nNext steps:");
  console.log(`  1. Add to Django's .env: NFT_CONTRACT_ADDRESS=${address}`);
  console.log(`  2. Confirm POLYGON_CHAIN_ID / POLYGON_NETWORK in mintique/settings.py match "${network.name}".`);
  console.log("  3. Restart the Django server so WEB3_ENABLED picks up the new address.");

  async function hre_artifacts_readSafe() {
    const hre = require("hardhat");
    return hre.artifacts.readArtifact("MintiqueNFT");
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
