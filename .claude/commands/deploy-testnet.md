---
description: "Deploy contracts to Cardano testnet environment"
tools: ["bash", "read"]
---

# Deploy to Testnet

Deploy the compiled OpShin contracts to Cardano testnet for testing and validation.

Usage: `/deploy-testnet [contract-name]`

This command will:
1. Check that contracts are built and available in `artifacts/`
2. Verify environment variables are configured (`.env` file)
3. Deploy the specified contract or all contracts to testnet
4. Generate deployment addresses and transaction IDs
5. Update deployment records

**Prerequisites:**
- Contracts must be compiled first (`/build-contracts`)
- `.env` file with required variables:
  ```
  BLOCKFROST_PROJECT_ID=your_testnet_project_id
  NETWORK=testnet
  WALLET_MNEMONIC=your_wallet_mnemonic
  ```

**Contract deployment:**
${1:+Deploying specific contract: $1}

```bash
# Ensure contracts are built
if [ ! -d "artifacts" ]; then
    echo "❌ Artifacts directory not found. Run /build-contracts first."
    exit 1
fi

# Check environment
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Please configure environment variables."
    exit 1
fi

echo "🚀 Deploying to Cardano testnet..."
echo "📋 Available contracts in artifacts/:"
find artifacts/ -name "*.plutus" -exec basename {} .plutus \;

# TODO: Add actual deployment script when available
echo "⚠️  Deployment script not yet implemented."
echo "📝 Next steps:"
echo "   1. Implement deployment script using pycardano"
echo "   2. Configure wallet and network connections"
echo "   3. Add contract address generation logic"
```