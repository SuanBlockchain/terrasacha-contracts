"""
Payment API routes
Endpoints for creating and managing payments
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
import uuid
import logging

from ..database import get_db
from ..models.payment import Payment, PaymentStatus, PaymentProvider, PaymentMethod
from ..services.wompi_service import WompiService
from ..services.binance_service import BinancePayService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


# Pydantic models for request/response validation

class PSEPaymentRequest(BaseModel):
    """Request model for PSE payment creation"""
    amount: float = Field(..., description="Amount in COP (e.g., 50000.00)")
    customer_email: EmailStr
    customer_phone: str = Field(..., pattern=r"^3\d{9}$", description="Colombian mobile: 3001234567")
    customer_document_type: str = Field(..., description="CC, CE, NIT, etc.")
    customer_document_number: str
    customer_full_name: str
    financial_institution_code: str = Field(..., description="Bank code from /banks endpoint")
    user_type: str = Field(..., pattern=r"^[01]$", description="0=Person, 1=Business")
    payment_description: str
    redirect_url: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "amount": 50000.00,
                "customer_email": "juan.perez@example.com",
                "customer_phone": "3001234567",
                "customer_document_type": "CC",
                "customer_document_number": "1234567890",
                "customer_full_name": "Juan Pérez",
                "financial_institution_code": "1007",  # Bancolombia
                "user_type": "0",
                "payment_description": "Pago de servicio",
                "redirect_url": "https://mysite.com/payment/result"
            }
        }


class CardPaymentRequest(BaseModel):
    """Request model for card payment creation"""
    amount: float = Field(..., description="Amount in COP")
    customer_email: EmailStr
    customer_phone: str
    customer_full_name: str
    installments: int = Field(1, ge=1, le=36, description="Number of installments")
    redirect_url: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "amount": 100000.00,
                "customer_email": "maria.garcia@example.com",
                "customer_phone": "3109876543",
                "customer_full_name": "María García",
                "installments": 3,
            }
        }


class CryptoPaymentRequest(BaseModel):
    """Request model for crypto payment creation"""
    amount: float = Field(..., description="Amount in USD (Binance uses USD)")
    customer_email: Optional[EmailStr] = None
    product_name: str
    product_detail: Optional[str] = None
    accepted_currencies: Optional[List[str]] = Field(
        default=["USDT", "USDC", "BTC"],
        description="Accepted cryptocurrencies"
    )
    redirect_url: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "amount": 50.00,  # USD
                "customer_email": "crypto.user@example.com",
                "product_name": "Premium Subscription",
                "product_detail": "Monthly subscription",
                "accepted_currencies": ["USDT", "USDC", "BUSD"],
            }
        }


class PaymentResponse(BaseModel):
    """Response model for payment creation"""
    success: bool
    payment_id: int
    reference: str
    transaction_id: str
    payment_url: Optional[str]
    status: str
    amount: float
    currency: str
    provider: str
    payment_method: str
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# PSE PAYMENT ENDPOINTS
# ============================================================================

@router.get("/banks")
async def get_banks():
    """
    Get list of Colombian banks available for PSE
    Returns bank codes and names for PSE payment form
    """
    try:
        wompi_service = WompiService()
        banks = await wompi_service.get_financial_institutions()
        return banks
    except Exception as e:
        logger.error(f"Error fetching banks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wompi/pse", response_model=PaymentResponse)
async def create_pse_payment(
    payment_request: PSEPaymentRequest,
    db: Session = Depends(get_db),
):
    """
    Create a PSE payment (Colombian bank transfer)

    This endpoint creates a PSE payment and returns a payment URL.
    The customer should be redirected to this URL to complete the payment
    in their bank's website.

    Steps:
    1. Create payment record in database
    2. Call Wompi API to create PSE transaction
    3. Return payment URL for customer redirect
    4. Webhook will update payment status when completed
    """
    try:
        # Generate unique reference
        reference = f"PSE-{uuid.uuid4().hex[:12].upper()}"

        # Create payment record
        payment = Payment(
            transaction_id=reference,
            reference=reference,
            provider=PaymentProvider.WOMPI,
            payment_method=PaymentMethod.PSE,
            amount=payment_request.amount,
            currency="COP",
            status=PaymentStatus.PENDING,
            customer_email=payment_request.customer_email,
            customer_phone=payment_request.customer_phone,
            customer_document_type=payment_request.customer_document_type,
            customer_document_number=payment_request.customer_document_number,
            customer_full_name=payment_request.customer_full_name,
            pse_financial_institution_code=payment_request.financial_institution_code,
            pse_user_type=payment_request.user_type,
            pse_payment_description=payment_request.payment_description,
            redirect_url=payment_request.redirect_url,
        )

        db.add(payment)
        db.commit()
        db.refresh(payment)

        # Create PSE transaction with Wompi
        wompi_service = WompiService()
        amount_in_cents = int(payment_request.amount * 100)

        wompi_response = await wompi_service.create_pse_payment(
            amount=amount_in_cents,
            reference=reference,
            customer_email=payment_request.customer_email,
            customer_phone=payment_request.customer_phone,
            customer_document_type=payment_request.customer_document_type,
            customer_document_number=payment_request.customer_document_number,
            customer_full_name=payment_request.customer_full_name,
            financial_institution_code=payment_request.financial_institution_code,
            user_type=payment_request.user_type,
            payment_description=payment_request.payment_description,
            redirect_url=payment_request.redirect_url,
        )

        # Update payment with Wompi response
        transaction_data = wompi_response.get("data", {})
        payment.provider_transaction_id = transaction_data.get("id")
        payment.payment_url = transaction_data.get("payment_link", {}).get("url")
        payment.provider_response = wompi_response

        db.commit()
        db.refresh(payment)

        logger.info(f"PSE payment created: {reference}")

        return PaymentResponse(
            success=True,
            payment_id=payment.id,
            reference=payment.reference,
            transaction_id=payment.provider_transaction_id,
            payment_url=payment.payment_url,
            status=payment.status.value,
            amount=float(payment.amount),
            currency=payment.currency,
            provider=payment.provider.value,
            payment_method=payment.payment_method.value,
            created_at=payment.created_at,
        )

    except Exception as e:
        logger.error(f"Error creating PSE payment: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CARD PAYMENT ENDPOINTS
# ============================================================================

@router.post("/wompi/card", response_model=PaymentResponse)
async def create_card_payment(
    payment_request: CardPaymentRequest,
    db: Session = Depends(get_db),
):
    """
    Create a card payment (credit/debit)

    Returns a checkout URL where the customer can enter their card details.
    Supports installment payments (cuotas).
    """
    try:
        reference = f"CARD-{uuid.uuid4().hex[:12].upper()}"

        # Create payment record
        payment = Payment(
            transaction_id=reference,
            reference=reference,
            provider=PaymentProvider.WOMPI,
            payment_method=PaymentMethod.CARD,
            amount=payment_request.amount,
            currency="COP",
            status=PaymentStatus.PENDING,
            customer_email=payment_request.customer_email,
            customer_phone=payment_request.customer_phone,
            customer_full_name=payment_request.customer_full_name,
            redirect_url=payment_request.redirect_url,
            metadata={"installments": payment_request.installments},
        )

        db.add(payment)
        db.commit()
        db.refresh(payment)

        # Create card transaction with Wompi
        wompi_service = WompiService()
        amount_in_cents = int(payment_request.amount * 100)

        wompi_response = await wompi_service.create_card_payment(
            amount=amount_in_cents,
            reference=reference,
            customer_email=payment_request.customer_email,
            customer_phone=payment_request.customer_phone,
            customer_full_name=payment_request.customer_full_name,
            installments=payment_request.installments,
            redirect_url=payment_request.redirect_url,
        )

        # Update payment
        transaction_data = wompi_response.get("data", {})
        payment.provider_transaction_id = transaction_data.get("id")
        payment.payment_url = transaction_data.get("payment_link", {}).get("url")
        payment.provider_response = wompi_response

        db.commit()
        db.refresh(payment)

        logger.info(f"Card payment created: {reference}")

        return PaymentResponse(
            success=True,
            payment_id=payment.id,
            reference=payment.reference,
            transaction_id=payment.provider_transaction_id,
            payment_url=payment.payment_url,
            status=payment.status.value,
            amount=float(payment.amount),
            currency=payment.currency,
            provider=payment.provider.value,
            payment_method=payment.payment_method.value,
            created_at=payment.created_at,
        )

    except Exception as e:
        logger.error(f"Error creating card payment: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CRYPTO PAYMENT ENDPOINTS
# ============================================================================

@router.post("/binance", response_model=PaymentResponse)
async def create_crypto_payment(
    payment_request: CryptoPaymentRequest,
    db: Session = Depends(get_db),
):
    """
    Create a cryptocurrency payment via Binance Pay

    Returns a checkout URL where the customer can pay with crypto.
    Supports multiple cryptocurrencies (BTC, ETH, USDT, USDC, etc.).

    Note: Amount is in USD. For Colombian customers, recommend using
    stablecoins (USDT, USDC) to avoid volatility.
    """
    try:
        reference = f"CRYPTO-{uuid.uuid4().hex[:12].upper()}"

        # Create payment record
        payment = Payment(
            transaction_id=reference,
            reference=reference,
            provider=PaymentProvider.BINANCE_PAY,
            payment_method=PaymentMethod.CRYPTO,
            amount=payment_request.amount,
            currency="USD",  # Binance uses USD
            status=PaymentStatus.PENDING,
            customer_email=payment_request.customer_email,
            redirect_url=payment_request.redirect_url,
            metadata={
                "accepted_currencies": payment_request.accepted_currencies,
                "product_name": payment_request.product_name,
            },
        )

        db.add(payment)
        db.commit()
        db.refresh(payment)

        # Create Binance Pay order
        binance_service = BinancePayService()

        binance_response = await binance_service.create_order(
            merchant_trade_no=reference,
            total_amount=payment_request.amount,
            currency="USD",
            product_name=payment_request.product_name,
            product_detail=payment_request.product_detail,
            buyer_email=payment_request.customer_email,
            return_url=payment_request.redirect_url,
            accepted_currencies=payment_request.accepted_currencies,
        )

        # Update payment with Binance response
        order_data = binance_response.get("data", {})
        payment.provider_transaction_id = order_data.get("prepayId")
        payment.payment_url = order_data.get("checkoutUrl")
        payment.provider_response = binance_response

        db.commit()
        db.refresh(payment)

        logger.info(f"Crypto payment created: {reference}")

        return PaymentResponse(
            success=True,
            payment_id=payment.id,
            reference=payment.reference,
            transaction_id=payment.provider_transaction_id,
            payment_url=payment.payment_url,
            status=payment.status.value,
            amount=float(payment.amount),
            currency=payment.currency,
            provider=payment.provider.value,
            payment_method=payment.payment_method.value,
            created_at=payment.created_at,
        )

    except Exception as e:
        logger.error(f"Error creating crypto payment: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PAYMENT STATUS ENDPOINTS
# ============================================================================

@router.get("/{payment_id}")
async def get_payment(payment_id: int, db: Session = Depends(get_db)):
    """
    Get payment details by ID
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    return payment.to_dict()


@router.get("/reference/{reference}")
async def get_payment_by_reference(reference: str, db: Session = Depends(get_db)):
    """
    Get payment details by reference
    """
    payment = db.query(Payment).filter(Payment.reference == reference).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    return payment.to_dict()


@router.get("/")
async def list_payments(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    List payments with optional status filter
    """
    query = db.query(Payment)

    if status:
        query = query.filter(Payment.status == status)

    payments = query.order_by(Payment.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "payments": [payment.to_dict() for payment in payments],
        "count": len(payments),
    }
