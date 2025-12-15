"""
Chain Context Dependency

FastAPI dependency for accessing CardanoChainContext with BlockFrost API.
"""

import os

from fastapi import HTTPException

from cardano_offchain.chain_context import CardanoChainContext


# Global state for chain context
_chain_context: CardanoChainContext | None = None


def get_chain_context() -> CardanoChainContext:
    """
    Get or initialize the chain context.

    Returns:
        CardanoChainContext: Initialized chain context with BlockFrost API

    Raises:
        HTTPException: If blockfrost_api_key is missing from environment
    """
    global _chain_context
    if _chain_context is None:
        network = os.getenv("network", "testnet")
        blockfrost_api_key = os.getenv("blockfrost_api_key")
        if not blockfrost_api_key:
            raise HTTPException(
                status_code=500,
                detail="Missing blockfrost_api_key environment variable"
            )
        _chain_context = CardanoChainContext(network, blockfrost_api_key)
    return _chain_context
