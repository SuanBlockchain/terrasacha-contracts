"""
Cardano Chain Context Management

Pure chain context functionality without console dependencies.
Handles network configuration and blockchain connection setup.
"""

from blockfrost import ApiUrls, BlockFrostApi
import pycardano as pc


class CardanoChainContext:
    """Manages Cardano chain context and network configuration"""
    
    def __init__(self, network: str = "testnet", blockfrost_api_key: str = None):
        """
        Initialize chain context
        
        Args:
            network: Network type ("testnet" or "mainnet")
            blockfrost_api_key: BlockFrost API key for chain queries
        """
        self.network = network
        self.blockfrost_api_key = blockfrost_api_key
        
        # Set network configuration
        if network == "testnet":
            self.base_url = ApiUrls.preview.value
            self.cardano_network = pc.Network.TESTNET
            self.cardanoscan = "https://preview.cardanoscan.io"
        else:
            self.base_url = ApiUrls.mainnet.value
            self.cardano_network = pc.Network.MAINNET
            self.cardanoscan = "https://cardanoscan.io"
        
        # Initialize API client if key provided
        self.api = None
        if blockfrost_api_key:
            self.api = BlockFrostApi(
                project_id=blockfrost_api_key,
                base_url=self.base_url
            )
        
        # Initialize chain context
        self.context = self._get_chain_context()
    
    def _get_chain_context(self) -> pc.ChainContext:
        """
        Create PyCardano chain context
        
        Returns:
            PyCardano chain context for transaction operations
        """
        if not self.blockfrost_api_key:
            raise ValueError("BlockFrost API key required for chain context")
            
        return pc.BlockFrostChainContext(
            project_id=self.blockfrost_api_key, 
            base_url=self.base_url
        )
    
    def get_context(self) -> pc.ChainContext:
        """Get the chain context"""
        return self.context
    
    def get_api(self) -> BlockFrostApi:
        """Get the BlockFrost API instance"""
        if not self.api:
            raise ValueError("BlockFrost API not initialized")
        return self.api
    
    def get_network_info(self) -> dict:
        """
        Get network configuration information
        
        Returns:
            Dictionary containing network information
        """
        return {
            'network': self.network,
            'cardano_network': self.cardano_network,
            'base_url': self.base_url,
            'cardanoscan': self.cardanoscan
        }
    
    def get_explorer_url(self, tx_id: str) -> str:
        """
        Get explorer URL for transaction
        
        Args:
            tx_id: Transaction ID
            
        Returns:
            Explorer URL for the transaction
        """
        return f"{self.cardanoscan}/transaction/{tx_id}"