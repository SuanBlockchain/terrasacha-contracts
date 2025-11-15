"""
Configuration settings for the payment system
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    APP_NAME: str = "Payment System API"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str

    # Database
    DATABASE_URL: str

    # Wompi Settings
    WOMPI_PUBLIC_KEY: str
    WOMPI_PRIVATE_KEY: str
    WOMPI_EVENT_SECRET: str
    WOMPI_API_URL: str = "https://sandbox.wompi.co/v1"

    # Binance Pay Settings
    BINANCE_API_KEY: str
    BINANCE_API_SECRET: str
    BINANCE_MERCHANT_ID: str
    BINANCE_API_URL: str = "https://bpay.binanceapi.com"

    # URLs
    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_URL: str = "http://localhost:8000"
    WOMPI_REDIRECT_URL: str
    WOMPI_WEBHOOK_URL: str
    BINANCE_WEBHOOK_URL: str

    # Colombian Settings
    DEFAULT_CURRENCY: str = "COP"
    TIMEZONE: str = "America/Bogota"

    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
