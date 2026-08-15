const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MintiqueNFT", function () {
  const NAME = "Mintique";
  const SYMBOL = "MNTQ";

  async function deployFixture({ maxSupply = 0 } = {}) {
    const [owner, alice, bob, carol] = await ethers.getSigners();
    const MintiqueNFT = await ethers.getContractFactory("MintiqueNFT");
    const contract = await MintiqueNFT.deploy(NAME, SYMBOL, owner.address, maxSupply);
    await contract.waitForDeployment();
    return { contract, owner, alice, bob, carol };
  }

  describe("deployment", function () {
    it("sets name, symbol, and owner", async function () {
      const { contract, owner } = await deployFixture();
      expect(await contract.name()).to.equal(NAME);
      expect(await contract.symbol()).to.equal(SYMBOL);
      expect(await contract.owner()).to.equal(owner.address);
    });

    it("starts with zero tokens minted", async function () {
      const { contract } = await deployFixture();
      expect(await contract.totalMinted()).to.equal(0n);
    });
  });

  describe("minting", function () {
    it("mints to the caller-specified recipient and sets tokenURI", async function () {
      const { contract, alice } = await deployFixture();
      const uri = "ipfs://bafy-metadata-1";

      const tx = await contract.mintNFT(alice.address, uri, 42, 500);
      const receipt = await tx.wait();

      expect(await contract.ownerOf(1)).to.equal(alice.address);
      expect(await contract.tokenURI(1)).to.equal(uri);
      expect(await contract.totalMinted()).to.equal(1n);

      const event = receipt.logs
        .map((l) => { try { return contract.interface.parseLog(l); } catch { return null; } })
        .find((e) => e && e.name === "MintiqueMinted");
      expect(event).to.not.be.undefined;
      expect(event.args.to).to.equal(alice.address);
      expect(event.args.tokenId).to.equal(1n);
      expect(event.args.mintiqueTokenId).to.equal(42n);
      expect(event.args.metadataUri).to.equal(uri);
      expect(event.args.royaltyBps).to.equal(500n);
    });

    it("is a public, unpermissioned call — any wallet can mint for itself", async function () {
      const { contract, alice, bob } = await deployFixture();
      await expect(contract.connect(alice).mintNFT(alice.address, "ipfs://a", 1, 0)).to.not.be.reverted;
      await expect(contract.connect(bob).mintNFT(bob.address, "ipfs://b", 2, 0)).to.not.be.reverted;
    });

    it("assigns strictly increasing, unique tokenIds across many mints", async function () {
      const { contract, alice } = await deployFixture();
      const seen = new Set();
      for (let i = 0; i < 5; i++) {
        const tx = await contract.mintNFT(alice.address, `ipfs://item-${i}`, i, 0);
        const receipt = await tx.wait();
        const event = receipt.logs
          .map((l) => { try { return contract.interface.parseLog(l); } catch { return null; } })
          .find((e) => e && e.name === "MintiqueMinted");
        const tokenId = event.args.tokenId.toString();
        expect(seen.has(tokenId)).to.equal(false, `tokenId ${tokenId} was reused`);
        seen.add(tokenId);
      }
      expect(seen.size).to.equal(5);
      expect(await contract.totalMinted()).to.equal(5n);
    });

    it("reverts when minting to the zero address", async function () {
      const { contract } = await deployFixture();
      await expect(
        contract.mintNFT(ethers.ZeroAddress, "ipfs://x", 1, 0)
      ).to.be.revertedWith("MintiqueNFT: mint to zero address");
    });

    it("reverts on an empty metadata URI", async function () {
      const { contract, alice } = await deployFixture();
      await expect(
        contract.mintNFT(alice.address, "", 1, 0)
      ).to.be.revertedWith("MintiqueNFT: empty metadata URI");
    });

    it("reverts when royaltyBps exceeds 100%", async function () {
      const { contract, alice } = await deployFixture();
      await expect(
        contract.mintNFT(alice.address, "ipfs://x", 1, 10_001)
      ).to.be.revertedWith("MintiqueNFT: royalty exceeds 100%");
    });

    it("enforces maxSupply when set", async function () {
      const { contract, alice } = await deployFixture({ maxSupply: 2 });
      await contract.mintNFT(alice.address, "ipfs://1", 1, 0);
      await contract.mintNFT(alice.address, "ipfs://2", 2, 0);
      await expect(
        contract.mintNFT(alice.address, "ipfs://3", 3, 0)
      ).to.be.revertedWith("MintiqueNFT: max supply reached");
    });

    it("allows unlimited minting when maxSupply is 0", async function () {
      const { contract, alice } = await deployFixture({ maxSupply: 0 });
      for (let i = 0; i < 10; i++) {
        await contract.mintNFT(alice.address, `ipfs://${i}`, i, 0);
      }
      expect(await contract.totalMinted()).to.equal(10n);
    });
  });

  describe("transfers", function () {
    it("lets the owner transfer their token", async function () {
      const { contract, alice, bob } = await deployFixture();
      await contract.mintNFT(alice.address, "ipfs://x", 1, 0);

      await contract.connect(alice).transferFrom(alice.address, bob.address, 1);
      expect(await contract.ownerOf(1)).to.equal(bob.address);
    });

    it("lets an approved address transfer on the owner's behalf", async function () {
      const { contract, alice, bob, carol } = await deployFixture();
      await contract.mintNFT(alice.address, "ipfs://x", 1, 0);

      await contract.connect(alice).approve(bob.address, 1);
      await contract.connect(bob).transferFrom(alice.address, carol.address, 1);
      expect(await contract.ownerOf(1)).to.equal(carol.address);
    });

    it("reverts if a non-owner, non-approved address tries to transfer", async function () {
      const { contract, alice, bob, carol } = await deployFixture();
      await contract.mintNFT(alice.address, "ipfs://x", 1, 0);

      await expect(
        contract.connect(bob).transferFrom(alice.address, carol.address, 1)
      ).to.be.revertedWithCustomError(contract, "ERC721InsufficientApproval");
    });

    it("keeps tokenURI and royalty attached to the token after transfer", async function () {
      const { contract, alice, bob } = await deployFixture();
      await contract.mintNFT(alice.address, "ipfs://sticky", 1, 750);

      await contract.connect(alice).transferFrom(alice.address, bob.address, 1);

      expect(await contract.tokenURI(1)).to.equal("ipfs://sticky");
      const [receiver, amount] = await contract.royaltyInfo(1, 10_000);
      expect(receiver).to.equal(alice.address); // royalty receiver set at mint time
      expect(amount).to.equal(750n);
    });
  });

  describe("ownership / access control", function () {
    it("only the contract owner can call updateRoyalty", async function () {
      const { contract, owner, alice, bob } = await deployFixture();
      await contract.mintNFT(alice.address, "ipfs://x", 1, 500);

      await expect(
        contract.connect(alice).updateRoyalty(1, bob.address, 1000)
      ).to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");

      await expect(contract.connect(owner).updateRoyalty(1, bob.address, 1000)).to.not.be.reverted;
      const [receiver, amount] = await contract.royaltyInfo(1, 10_000);
      expect(receiver).to.equal(bob.address);
      expect(amount).to.equal(1000n);
    });

    it("supports ERC-721 and ERC-2981 interface detection", async function () {
      const { contract } = await deployFixture();
      const ERC721_INTERFACE_ID = "0x80ac58cd";
      const ERC2981_INTERFACE_ID = "0x2a55205a";
      expect(await contract.supportsInterface(ERC721_INTERFACE_ID)).to.equal(true);
      expect(await contract.supportsInterface(ERC2981_INTERFACE_ID)).to.equal(true);
    });

    it("ownership of the token, not the contract, gates approve/transfer rights", async function () {
      const { contract, alice, bob } = await deployFixture();
      await contract.mintNFT(alice.address, "ipfs://x", 1, 0);

      await expect(
        contract.connect(bob).approve(bob.address, 1)
      ).to.be.revertedWithCustomError(contract, "ERC721InvalidApprover");
    });
  });
});
