"""
FastAPI Application - Payment System
Handles traditional (Wompi) and crypto (Binance Pay) payments for Colombia
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from .config import settings
from .database import Base, engine
from .routers import payments_router, webhooks_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Payment System API",
    description="""
    Payment system supporting traditional and cryptocurrency payments for Colombia.

    ## Features

    * **PSE** - Colombian bank transfers (via Wompi)
    * **Credit/Debit Cards** - Card payments with installments (via Wompi)
    * **Cryptocurrency** - Bitcoin, Ethereum, USDT, USDC, etc. (via Binance Pay)
    * **Secure Webhooks** - HMAC signature verification
    * **Real-time Status** - Payment tracking and updates

    ## Payment Providers

    * **Wompi** - Colombian payment gateway (PSE, cards, Nequi, cash)
    * **Binance Pay** - Cryptocurrency payments

    ## Getting Started

    1. Get banks list: `GET /api/v1/payments/banks`
    2. Create PSE payment: `POST /api/v1/payments/wompi/pse`
    3. Redirect customer to `payment_url`
    4. Receive webhook notification when payment completes

    ## Security

    All webhooks verify HMAC signatures to prevent tampering.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(payments_router)
app.include_router(webhooks_router)


@app.get("/")
async def root():
    """
    API root endpoint
    """
    return {
        "name": "Payment System API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "providers": {
            "traditional": "Wompi (PSE, Cards, Nequi)",
            "crypto": "Binance Pay (BTC, ETH, USDT, USDC, etc.)"
        },
        "endpoints": {
            "payments": "/api/v1/payments",
            "webhooks": "/api/v1/webhooks"
        }
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {
        "status": "healthy",
        "environment": settings.APP_ENV
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
