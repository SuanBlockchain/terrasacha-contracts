"""
API Configuration

Centralized settings for the FastAPI application.
API metadata is hardcoded, while environment-specific settings load from .env file.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from api.database.connection import DatabaseSettings


# Get the project root directory (one level up from api/)
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    """
    Application settings for the Terrasacha API

    API metadata (title, description, version, contact) are hardcoded.
    Environment-specific settings are loaded from .env file.
    """

    # ============================================================================
    # API Metadata (hardcoded - versioned with code)
    # ============================================================================

    api_title: str = "Terrasacha API"
    api_description: str = (
        "Carbon credit tokens and NFTs management API for the Terrasacha platform. "
        "Provides endpoints for protocol management, project operations, token minting, "
        "and investment contract interactions on the Cardano blockchain."
    )
    api_version: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Contact information
    contact_name: str = "Terrasacha"
    contact_url: str = "https://terrasacha.com"

    # ============================================================================
    # Environment Settings (loaded from .env)
    # ============================================================================

    environment: str = "development"  # development, staging, production
    api_port: int = 8000

    api_key_dev: str  # No default - must be set in .env

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    @property
    def contact(self) -> dict[str, str]:
        """FastAPI contact information"""
        return {"name": self.contact_name, "url": self.contact_url}

    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.environment.lower() == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment.lower() == "production"


# ============================================================================
# Global settings instance
# ============================================================================

settings = Settings()  # type: ignore[call-arg]  # Pydantic settings loads from env

# Database settings instance (for convenience)
db_settings = DatabaseSettings()  # type: ignore[call-arg]  # Pydantic settings loads from env
