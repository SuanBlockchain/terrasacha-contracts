"""
Webhook handlers for payment providers
Includes signature verification for security
"""
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from typing import Optional
import json
import logging
from datetime import datetime

from ..database import get_db
from ..models.payment import Payment, PaymentStatus, PaymentProvider
from ..services.wompi_service import WompiService
from ..services.binance_service import BinancePayService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/wompi")
async def wompi_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_event_signature: Optional[str] = Header(None, alias="X-Event-Signature"),
    x_event_timestamp: Optional[str] = Header(None, alias="X-Event-Timestamp"),
):
    """
    Wompi webhook handler
    Receives payment status updates from Wompi

    Security: Verifies webhook signature using HMAC-SHA256

    Events received:
    - transaction.updated: Transaction status changed
    - transaction.created: New transaction created

    Wompi sends:
    - X-Event-Signature: HMAC signature
    - X-Event-Timestamp: Event timestamp
    - Body: Event data with transaction info
    """
    try:
        # Get raw request body for signature verification
        raw_body = await request.body()
        body_str = raw_body.decode('utf-8')

        # Parse JSON data
        event_data = json.loads(body_str)

        logger.info(f"Wompi webhook received: {event_data.get('event')}")

        # Verify webhook signature (CRITICAL for security)
        if not x_event_signature or not x_event_timestamp:
            logger.error("Missing signature headers")
            raise HTTPException(status_code=400, detail="Missing signature headers")

        wompi_service = WompiService()
        is_valid = wompi_service.verify_webhook_signature(
            signature=x_event_signature,
            timestamp=x_event_timestamp,
            request_body=body_str,
        )

        if not is_valid:
            logger.error("Invalid webhook signature - possible attack!")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Extract event information
        event_type = event_data.get("event")
        transaction_data = event_data.get("data", {}).get("transaction", {})

        # Get transaction details
        transaction_id = transaction_data.get("id")
        reference = transaction_data.get("reference")
        status = transaction_data.get("status")
        amount = transaction_data.get("amount_in_cents", 0) / 100  # Convert to decimal

        logger.info(f"Transaction {transaction_id}: {status}")

        # Find payment in database by reference or transaction_id
        payment = db.query(Payment).filter(
            (Payment.reference == reference) |
            (Payment.provider_transaction_id == transaction_id)
        ).first()

        if not payment:
            logger.warning(f"Payment not found for reference: {reference}")
            # Still return 200 to acknowledge receipt
            return {"status": "payment_not_found", "message": "Payment record not found"}

        # Update payment status
        old_status = payment.status
        payment.status = wompi_service.map_wompi_status_to_payment_status(status)
        payment.provider_transaction_id = transaction_id
        payment.webhook_data = event_data
        payment.updated_at = datetime.utcnow()

        # Update payment method specific data
        payment_method_type = transaction_data.get("payment_method_type")

        if payment_method_type == "PSE":
            # PSE specific updates
            pse_data = transaction_data.get("payment_method", {})
            payment.pse_financial_institution_code = pse_data.get("financial_institution_code")

        elif payment_method_type == "CARD":
            # Card specific updates
            card_data = transaction_data.get("payment_method", {})
            payment.card_last_four = card_data.get("extra", {}).get("last_four")
            payment.card_brand = card_data.get("extra", {}).get("brand")

        # If payment is now approved, set completion time
        if payment.status == PaymentStatus.APPROVED and old_status != PaymentStatus.APPROVED:
            payment.completed_at = datetime.utcnow()
            logger.info(f"Payment APPROVED: {reference} - ${amount} COP")

        # If payment failed or declined
        elif payment.status in [PaymentStatus.DECLINED, PaymentStatus.ERROR]:
            error_data = transaction_data.get("status_message")
            payment.error_message = error_data
            logger.warning(f"Payment FAILED: {reference} - {error_data}")

        # Save changes
        db.commit()

        logger.info(f"Payment {reference} updated: {old_status} -> {payment.status}")

        # Return success response
        return {
            "status": "success",
            "reference": reference,
            "payment_status": payment.status.value,
        }

    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing Wompi webhook: {str(e)}", exc_info=True)
        db.rollback()
        # Still return 200 to prevent retries for application errors
        return {"status": "error", "message": str(e)}


@router.post("/binance")
async def binance_webhook(
    request: Request,
    db: Session = Depends(get_db),
    binancepay_signature: Optional[str] = Header(None, alias="BinancePay-Signature"),
    binancepay_timestamp: Optional[str] = Header(None, alias="BinancePay-Timestamp"),
    binancepay_nonce: Optional[str] = Header(None, alias="BinancePay-Nonce"),
    binancepay_certificate_sn: Optional[str] = Header(None, alias="BinancePay-Certificate-SN"),
):
    """
    Binance Pay webhook handler
    Receives payment status updates from Binance Pay

    Security: Verifies webhook signature using HMAC-SHA512

    Events received:
    - Order payment success
    - Order payment failed
    - Order closed

    Binance sends:
    - BinancePay-Signature: HMAC-SHA512 signature
    - BinancePay-Timestamp: Event timestamp
    - BinancePay-Nonce: Random nonce
    - BinancePay-Certificate-SN: Certificate serial number
    """
    try:
        # Get raw request body for signature verification
        raw_body = await request.body()
        body_str = raw_body.decode('utf-8')

        # Parse JSON data
        event_data = json.loads(body_str)

        logger.info(f"Binance Pay webhook received: {event_data.get('bizType')}")

        # Verify webhook signature (CRITICAL for security)
        if not all([binancepay_signature, binancepay_timestamp, binancepay_nonce]):
            logger.error("Missing Binance Pay signature headers")
            raise HTTPException(status_code=400, detail="Missing signature headers")

        binance_service = BinancePayService()
        is_valid = binance_service.verify_webhook_signature(
            signature=binancepay_signature,
            timestamp=binancepay_timestamp,
            nonce=binancepay_nonce,
            request_body=body_str,
        )

        if not is_valid:
            logger.error("Invalid Binance webhook signature - possible attack!")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Extract event information
        biz_type = event_data.get("bizType")  # Event type
        biz_id = event_data.get("bizId")  # Binance order ID
        biz_status = event_data.get("bizStatus")  # Order status

        # Get order data
        data = event_data.get("data", {})
        merchant_trade_no = data.get("merchantTradeNo")  # Our reference
        order_amount = data.get("orderAmount")
        currency = data.get("currency")
        crypto_currency = data.get("cryptocurrency")
        crypto_amount = data.get("cryptoAmount")
        transaction_id = data.get("transactionId")

        logger.info(f"Binance order {merchant_trade_no}: {biz_status}")

        # Find payment in database
        payment = db.query(Payment).filter(
            Payment.reference == merchant_trade_no
        ).first()

        if not payment:
            logger.warning(f"Payment not found for reference: {merchant_trade_no}")
            # Still return success to acknowledge receipt
            return {"returnCode": "SUCCESS", "returnMessage": "Payment not found"}

        # Update payment status
        old_status = payment.status
        payment.status = binance_service.map_binance_status_to_payment_status(biz_status)
        payment.provider_transaction_id = biz_id
        payment.webhook_data = event_data
        payment.updated_at = datetime.utcnow()

        # Update crypto specific data
        if crypto_currency:
            payment.crypto_currency = crypto_currency
            payment.crypto_transaction_hash = transaction_id

        # If payment is now approved
        if payment.status == PaymentStatus.APPROVED and old_status != PaymentStatus.APPROVED:
            payment.completed_at = datetime.utcnow()
            logger.info(
                f"Crypto Payment APPROVED: {merchant_trade_no} - "
                f"{crypto_amount} {crypto_currency} (${order_amount} {currency})"
            )

        # If payment failed
        elif payment.status in [PaymentStatus.DECLINED, PaymentStatus.ERROR]:
            error_message = data.get("errorMessage", "Unknown error")
            payment.error_message = error_message
            logger.warning(f"Crypto Payment FAILED: {merchant_trade_no} - {error_message}")

        # Save changes
        db.commit()

        logger.info(f"Payment {merchant_trade_no} updated: {old_status} -> {payment.status}")

        # Binance expects this specific response format
        return {
            "returnCode": "SUCCESS",
            "returnMessage": None
        }

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Binance webhook")
        return {"returnCode": "FAIL", "returnMessage": "Invalid JSON"}
    except Exception as e:
        logger.error(f"Error processing Binance webhook: {str(e)}", exc_info=True)
        db.rollback()
        # Return success to prevent retries
        return {"returnCode": "SUCCESS", "returnMessage": str(e)}


@router.get("/test")
async def test_webhook():
    """
    Test endpoint to verify webhook router is working
    """
    return {
        "status": "ok",
        "message": "Webhook endpoints are ready",
        "endpoints": {
            "wompi": "/api/v1/webhooks/wompi",
            "binance": "/api/v1/webhooks/binance",
        }
    }
