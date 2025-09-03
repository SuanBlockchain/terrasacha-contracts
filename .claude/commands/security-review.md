---
description: "Comprehensive security analysis of OpShin smart contracts"
tools: ["read", "grep"]
---

# Security Review

Perform a thorough security analysis of the OpShin smart contracts, focusing on Cardano-specific vulnerabilities and best practices.

Usage: `/security-review [contract-name]`

This analysis covers:

## 🔍 **Core Security Checks**

1. **UTXO Handling**
   - Proper input/output validation
   - Prevention of double-spending
   - Linear progression enforcement

2. **Token Economics**
   - Minting/burning constraints
   - Token supply validation
   - Unauthorized token creation prevention

3. **Access Control**
   - Admin authorization checks
   - Multi-signature requirements
   - Permission escalation prevention

4. **Datum/Redeemer Validation**
   - Input sanitization
   - Type safety verification
   - Malformed data handling

## 🛡️ **Cardano-Specific Vulnerabilities**

- **Script Address Validation**: Ensuring funds don't move to unintended addresses
- **Value Preservation**: Checking that value is properly conserved across transactions  
- **Datum Continuity**: Validating that critical datum fields remain unchanged
- **NFT Uniqueness**: Verifying UTXO-based uniqueness mechanisms
- **Linear Contract Patterns**: Ensuring one-input-to-one-output constraints

## 📋 **Analysis Targets**

${1:+**Analyzing specific contract: $1**}

Focus areas:
- `src/terrasacha_contracts/validators/protocol.py` - Protocol validation logic
- `src/terrasacha_contracts/minting_policies/protocol_nfts.py` - NFT minting constraints
- `src/terrasacha_contracts/util.py` - Utility functions and helpers
- `src/terrasacha_contracts/types.py` - Type definitions and constants

I'll analyze the contracts for common smart contract vulnerabilities, Cardano-specific issues, and alignment with best practices. The review will include specific recommendations for any identified issues.