"""
Payment database models
"""
from sqlalchemy import Column, String, Integer, DateTime, Enum, Numeric, JSON, Text
from sqlalchemy.sql import func
from datetime import datetime
import enum
from ..database import Base


class PaymentStatus(str, enum.Enum):
    """Payment status enumeration"""
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    VOIDED = "voided"
    ERROR = "error"
    EXPIRED = "expired"


class PaymentProvider(str, enum.Enum):
    """Payment provider enumeration"""
    WOMPI = "wompi"
    BINANCE_PAY = "binance_pay"


class PaymentMethod(str, enum.Enum):
    """Payment method enumeration"""
    PSE = "pse"  # Colombian bank transfer
    CARD = "card"  # Credit/debit card
    NEQUI = "nequi"  # Nequi wallet
    BANCOLOMBIA_TRANSFER = "bancolombia_transfer"
    CRYPTO = "crypto"  # Cryptocurrency
    CASH = "cash"  # Cash networks (Efecty, Baloto)


class Payment(Base):
    """
    Payment transaction model
    Stores all payment transactions from any provider
    """
    __tablename__ = "payments"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # External reference IDs
    transaction_id = Column(String(100), unique=True, index=True, nullable=False)
    provider_transaction_id = Column(String(200), index=True)  # Wompi/Binance transaction ID
    reference = Column(String(200), unique=True, index=True)  # Internal reference

    # Provider information
    provider = Column(Enum(PaymentProvider), nullable=False)
    payment_method = Column(Enum(PaymentMethod), nullable=False)

    # Payment details
    amount = Column(Numeric(precision=20, scale=2), nullable=False)  # Support large COP amounts
    currency = Column(String(10), nullable=False, default="COP")
    status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING, index=True)

    # Customer information
    customer_email = Column(String(255), index=True)
    customer_phone = Column(String(50))
    customer_document_type = Column(String(20))  # CC, CE, NIT, etc.
    customer_document_number = Column(String(50))
    customer_full_name = Column(String(255))

    # PSE specific fields
    pse_financial_institution_code = Column(String(10))  # Bank code for PSE
    pse_user_type = Column(String(1))  # 0=Person, 1=Business
    pse_payment_description = Column(String(255))

    # Card specific fields
    card_last_four = Column(String(4))
    card_brand = Column(String(50))  # Visa, Mastercard, etc.
    card_holder_name = Column(String(255))

    # Crypto specific fields
    crypto_currency = Column(String(10))  # BTC, ETH, USDT, etc.
    crypto_network = Column(String(50))  # Bitcoin, Ethereum, BSC, etc.
    crypto_wallet_address = Column(String(255))
    crypto_transaction_hash = Column(String(255))

    # URLs
    payment_url = Column(Text)  # URL to redirect user for payment
    redirect_url = Column(Text)  # URL to redirect after payment

    # Provider response
    provider_response = Column(JSON)  # Full response from provider
    webhook_data = Column(JSON)  # Webhook notification data

    # Error handling
    error_message = Column(Text)
    error_code = Column(String(50))

    # Metadata
    metadata = Column(JSON)  # Additional flexible data

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))  # When payment was completed
    expires_at = Column(DateTime(timezone=True))  # When payment expires

    def __repr__(self):
        return f"<Payment(id={self.id}, reference={self.reference}, status={self.status}, amount={self.amount} {self.currency})>"

    def to_dict(self):
        """Convert payment to dictionary"""
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "reference": self.reference,
            "provider": self.provider.value if self.provider else None,
            "payment_method": self.payment_method.value if self.payment_method else None,
            "amount": float(self.amount) if self.amount else None,
            "currency": self.currency,
            "status": self.status.value if self.status else None,
            "customer_email": self.customer_email,
            "payment_url": self.payment_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
