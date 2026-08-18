const { ethers, network } = require("hardhat");

async function main() {
    const [deployer] = await ethers.getSigners();
    const balance = await ethers.provider.getBalance(deployer.address);

    console.log("Network:", network.name);
    console.log("Deployer address:", deployer.address);
    console.log("Balance:", ethers.formatEther(balance), "POL");
    console.log("\nCompare this address to the one you funded via faucet.");
    console.log("Check it directly at: https://amoy.polygonscan.com/address/" + deployer.address);
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});