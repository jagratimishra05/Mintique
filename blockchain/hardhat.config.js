require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

const { SEPOLIA_RPC_URL, AMOY_RPC_URL, POLYGON_RPC_URL, PRIVATE_KEY, ETHERSCAN_API_KEY, POLYGONSCAN_API_KEY } =
  process.env;

const accounts = PRIVATE_KEY ? [PRIVATE_KEY] : [];

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      evmVersion: "cancun",
    },
  },
  networks: {
    hardhat: {},
    localhost: {
      url: "http://127.0.0.1:8545",
    },
    // Ethereum testnet — good for quick, well-documented testing.
    sepolia: {
      url: SEPOLIA_RPC_URL || "",
      accounts,
      chainId: 11155111,
    },
    // Polygon testnet — matches Mintique's production target network
    // (see mintique/settings.py POLYGON_NETWORKS / blockchain.py).
    amoy: {
      url: AMOY_RPC_URL || "",
      accounts,
      chainId: 80002,
    },
    polygon: {
      url: POLYGON_RPC_URL || "",
      accounts,
      chainId: 137,
    },
  },
  etherscan: {
    apiKey: {
      sepolia: ETHERSCAN_API_KEY || "",
      polygonAmoy: POLYGONSCAN_API_KEY || "",
      polygon: POLYGONSCAN_API_KEY || "",
    },
  },
};
