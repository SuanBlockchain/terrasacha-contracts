"""
Chain Context Dependency

FastAPI dependency for accessing CardanoChainContext with BlockFrost API.
"""

import logging
import os

from fastapi import HTTPException

from cardano_offchain.chain_context import CardanoChainContext

logger = logging.getLogger(__name__)

# Global state for chain context
_chain_context: CardanoChainContext | None = None


def get_chain_context() -> CardanoChainContext:
    """
    Get or initialize the chain context.

    Supported networks:
    - "testnet" or "preview": Cardano Preview testnet
    - "preprod": Cardano Pre-production testnet
    - "mainnet": Cardano Mainnet

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
        logger.info(f"Chain context initialized: network={network}, base_url={_chain_context.base_url}")
    return _chain_context
