"""
Binance Pay Service
Handles cryptocurrency payments via Binance Pay
"""
import httpx
import hmac
import hashlib
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from ..config import settings
from ..models.payment import Payment, PaymentStatus
import logging

logger = logging.getLogger(__name__)


class BinancePayService:
    """
    Service class for Binance Pay integration
    Documentation: https://developers.binance.com/docs/binance-pay
    """

    def __init__(self):
        self.api_url = settings.BINANCE_API_URL
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET
        self.merchant_id = settings.BINANCE_MERCHANT_ID

    def _generate_signature(self, payload: str, timestamp: int) -> str:
        """
        Generate HMAC SHA512 signature for Binance Pay API

        Args:
            payload: JSON string of request body
            timestamp: Current timestamp in milliseconds

        Returns:
            Hex signature string
        """
        # Binance Pay signature format: timestamp + "\n" + nonce + "\n" + payload
        nonce = str(int(time.time() * 1000))
        message = f"{timestamp}\n{nonce}\n{payload}\n"

        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha512
        ).hexdigest().upper()

        return signature

    def _get_headers(self, payload: str) -> Dict[str, str]:
        """
        Generate headers for Binance Pay API request

        Args:
            payload: JSON string of request body

        Returns:
            Dict of headers
        """
        timestamp = int(time.time() * 1000)
        nonce = str(timestamp)

        return {
            "Content-Type": "application/json",
            "BinancePay-Timestamp": str(timestamp),
            "BinancePay-Nonce": nonce,
            "BinancePay-Certificate-SN": self.api_key,
            "BinancePay-Signature": self._generate_signature(payload, timestamp),
        }

    async def create_order(
        self,
        merchant_trade_no: str,  # Your unique order reference
        total_amount: float,  # Amount in fiat
        currency: str,  # Fiat currency (USD, COP not directly supported - use USD)
        product_name: str,
        product_detail: Optional[str] = None,
        buyer_email: Optional[str] = None,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
        accepted_currencies: Optional[List[str]] = None,  # e.g., ["USDT", "BTC", "ETH"]
    ) -> Dict[str, Any]:
        """
        Create a Binance Pay order (checkout URL for customer)

        Args:
            merchant_trade_no: Your unique order reference
            total_amount: Amount in fiat currency
            currency: Fiat currency code (use "USD" for Colombia)
            product_name: Product/service name
            product_detail: Product/service description
            buyer_email: Customer email
            return_url: Success redirect URL
            cancel_url: Cancel redirect URL
            accepted_currencies: List of crypto currencies to accept

        Returns:
            Dict with checkout URL and order details

        Note: For Colombia, use USD as currency and accept USDT/USDC for stability
        """
        try:
            # Default to stablecoins for Colombia
            if not accepted_currencies:
                accepted_currencies = ["USDT", "USDC", "BUSD"]

            # Prepare order data
            order_data = {
                "env": {
                    "terminalType": "WEB"
                },
                "merchantTradeNo": merchant_trade_no,
                "orderAmount": total_amount,
                "currency": currency,
                "goods": {
                    "goodsType": "01",  # 01 = Virtual goods, 02 = Physical goods
                    "goodsCategory": "0000",  # Category code
                    "referenceGoodsId": merchant_trade_no,
                    "goodsName": product_name,
                    "goodsDetail": product_detail or product_name,
                },
                "returnUrl": return_url or settings.FRONTEND_URL,
                "cancelUrl": cancel_url or settings.FRONTEND_URL,
                "webhook": settings.BINANCE_WEBHOOK_URL,
            }

            # Add buyer info if provided
            if buyer_email:
                order_data["buyer"] = {
                    "buyerEmail": buyer_email
                }

            # Specify accepted cryptocurrencies
            order_data["supportPayCurrency"] = ",".join(accepted_currencies)

            # Convert to JSON string for signature
            payload = json.dumps(order_data)

            # Make API request
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/binancepay/openapi/v2/order",
                    content=payload,
                    headers=self._get_headers(payload),
                )
                response.raise_for_status()
                result = response.json()

            # Check if request was successful
            if result.get("status") != "SUCCESS":
                logger.error(f"Binance Pay order creation failed: {result}")
                raise Exception(f"Binance Pay error: {result.get('errorMessage', 'Unknown error')}")

            logger.info(f"Binance Pay order created: {result.get('data', {}).get('prepayId')}")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error creating Binance Pay order: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error creating Binance Pay order: {str(e)}")
            raise

    async def query_order(
        self,
        merchant_trade_no: Optional[str] = None,
        prepay_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query order status

        Args:
            merchant_trade_no: Your order reference (use this OR prepay_id)
            prepay_id: Binance Pay order ID (use this OR merchant_trade_no)

        Returns:
            Dict with order status and details
        """
        try:
            if not merchant_trade_no and not prepay_id:
                raise ValueError("Must provide either merchant_trade_no or prepay_id")

            query_data = {}
            if merchant_trade_no:
                query_data["merchantTradeNo"] = merchant_trade_no
            if prepay_id:
                query_data["prepayId"] = prepay_id

            payload = json.dumps(query_data)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/binancepay/openapi/v2/order/query",
                    content=payload,
                    headers=self._get_headers(payload),
                )
                response.raise_for_status()
                result = response.json()

            if result.get("status") != "SUCCESS":
                logger.error(f"Binance Pay query failed: {result}")
                raise Exception(f"Binance Pay error: {result.get('errorMessage', 'Unknown error')}")

            return result

        except Exception as e:
            logger.error(f"Error querying Binance Pay order: {str(e)}")
            raise

    async def close_order(self, merchant_trade_no: str) -> Dict[str, Any]:
        """
        Close/cancel an unpaid order

        Args:
            merchant_trade_no: Your order reference

        Returns:
            Dict with close result
        """
        try:
            close_data = {
                "merchantTradeNo": merchant_trade_no
            }

            payload = json.dumps(close_data)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/binancepay/openapi/v2/order/close",
                    content=payload,
                    headers=self._get_headers(payload),
                )
                response.raise_for_status()
                result = response.json()

            if result.get("status") != "SUCCESS":
                logger.error(f"Binance Pay close order failed: {result}")
                raise Exception(f"Binance Pay error: {result.get('errorMessage', 'Unknown error')}")

            logger.info(f"Binance Pay order closed: {merchant_trade_no}")
            return result

        except Exception as e:
            logger.error(f"Error closing Binance Pay order: {str(e)}")
            raise

    def verify_webhook_signature(
        self,
        signature: str,
        timestamp: str,
        nonce: str,
        request_body: str,
    ) -> bool:
        """
        Verify webhook signature from Binance Pay

        Args:
            signature: Signature from BinancePay-Signature header
            timestamp: Timestamp from BinancePay-Timestamp header
            nonce: Nonce from BinancePay-Nonce header
            request_body: Raw request body as string

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Binance Pay webhook signature format
            message = f"{timestamp}\n{nonce}\n{request_body}\n"

            expected_signature = hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha512
            ).hexdigest().upper()

            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            logger.error(f"Error verifying Binance webhook signature: {str(e)}")
            return False

    def map_binance_status_to_payment_status(self, binance_status: str) -> PaymentStatus:
        """
        Map Binance Pay order status to internal PaymentStatus

        Binance statuses:
        - INITIAL: Order created, waiting for payment
        - PENDING: Payment detected, confirming
        - PAID: Payment confirmed and completed
        - CANCELED: Order canceled
        - EXPIRED: Order expired
        - ERROR: Payment error
        """
        status_mapping = {
            "INITIAL": PaymentStatus.PENDING,
            "PENDING": PaymentStatus.PENDING,
            "PAID": PaymentStatus.APPROVED,
            "CANCELED": PaymentStatus.VOIDED,
            "EXPIRED": PaymentStatus.EXPIRED,
            "ERROR": PaymentStatus.ERROR,
        }
        return status_mapping.get(binance_status, PaymentStatus.ERROR)

    def get_supported_cryptocurrencies(self) -> List[str]:
        """
        Get list of supported cryptocurrencies
        Commonly accepted in Colombia: USDT, USDC, BTC, ETH, BNB, BUSD
        """
        return [
            "USDT",  # Tether (most popular stablecoin in LATAM)
            "USDC",  # USD Coin (stablecoin)
            "BUSD",  # Binance USD (stablecoin)
            "BTC",   # Bitcoin
            "ETH",   # Ethereum
            "BNB",   # Binance Coin
            "DAI",   # DAI (stablecoin)
        ]
