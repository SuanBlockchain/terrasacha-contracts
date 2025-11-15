"""
Wompi Payment Service
Handles PSE, card, and other Colombian payment methods
"""
import httpx
import hashlib
import hmac
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from ..config import settings
from ..models.payment import Payment, PaymentStatus, PaymentProvider, PaymentMethod
import logging

logger = logging.getLogger(__name__)


class WompiService:
    """
    Service class for Wompi payment integration
    Documentation: https://docs.wompi.co/
    """

    def __init__(self):
        self.api_url = settings.WOMPI_API_URL
        self.public_key = settings.WOMPI_PUBLIC_KEY
        self.private_key = settings.WOMPI_PRIVATE_KEY
        self.event_secret = settings.WOMPI_EVENT_SECRET

    async def get_financial_institutions(self) -> Dict[str, Any]:
        """
        Get list of available banks for PSE
        Returns list of Colombian banks that support PSE payments
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/pse/financial_institutions",
                    headers={"Authorization": f"Bearer {self.public_key}"}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching financial institutions: {str(e)}")
            raise

    async def create_pse_payment(
        self,
        amount: int,  # Amount in COP cents (e.g., 50000 = $500.00 COP)
        reference: str,
        customer_email: str,
        customer_phone: str,
        customer_document_type: str,  # CC, CE, NIT, etc.
        customer_document_number: str,
        customer_full_name: str,
        financial_institution_code: str,  # Bank code from get_financial_institutions()
        user_type: str,  # "0" = Person, "1" = Business
        payment_description: str,
        redirect_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a PSE payment transaction

        Args:
            amount: Amount in cents (50000 = $500.00 COP)
            reference: Unique payment reference
            customer_email: Customer email
            customer_phone: Customer phone (format: 3001234567)
            customer_document_type: Document type (CC, CE, NIT, etc.)
            customer_document_number: Document number
            customer_full_name: Customer full name
            financial_institution_code: Bank code (from get_financial_institutions)
            user_type: "0" for person, "1" for business
            payment_description: Payment description
            redirect_url: URL to redirect after payment

        Returns:
            Dict with transaction details and payment URL
        """
        try:
            # Generate integrity signature
            # Format: reference + amount + currency + integrity_secret
            currency = "COP"
            integrity_string = f"{reference}{amount}{currency}{self.private_key}"
            integrity_signature = hashlib.sha256(integrity_string.encode()).hexdigest()

            # Prepare payment data
            payment_data = {
                "acceptance_token": await self._get_acceptance_token(),
                "amount_in_cents": amount,
                "currency": currency,
                "signature:integrity": integrity_signature,
                "customer_email": customer_email,
                "reference": reference,
                "redirect_url": redirect_url or settings.WOMPI_REDIRECT_URL,
                "payment_method": {
                    "type": "PSE",
                    "user_type": user_type,  # 0 = Person, 1 = Business
                    "user_legal_id_type": customer_document_type,  # CC, CE, NIT
                    "user_legal_id": customer_document_number,
                    "financial_institution_code": financial_institution_code,
                    "payment_description": payment_description,
                },
                "customer_data": {
                    "phone_number": customer_phone,
                    "full_name": customer_full_name,
                },
            }

            # Make API request
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/transactions",
                    json=payment_data,
                    headers={
                        "Authorization": f"Bearer {self.private_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                result = response.json()

            logger.info(f"PSE payment created: {result.get('data', {}).get('id')}")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error creating PSE payment: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error creating PSE payment: {str(e)}")
            raise

    async def create_card_payment(
        self,
        amount: int,
        reference: str,
        customer_email: str,
        customer_phone: str,
        customer_full_name: str,
        installments: int = 1,
        redirect_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a card payment transaction (returns checkout URL)

        Args:
            amount: Amount in cents
            reference: Unique payment reference
            customer_email: Customer email
            customer_phone: Customer phone
            customer_full_name: Customer full name
            installments: Number of installments (1, 2, 3, 6, 12, etc.)
            redirect_url: URL to redirect after payment

        Returns:
            Dict with checkout link for card payment
        """
        try:
            currency = "COP"
            integrity_string = f"{reference}{amount}{currency}{self.private_key}"
            integrity_signature = hashlib.sha256(integrity_string.encode()).hexdigest()

            # For card payments, we create a payment link
            payment_data = {
                "acceptance_token": await self._get_acceptance_token(),
                "amount_in_cents": amount,
                "currency": currency,
                "signature:integrity": integrity_signature,
                "customer_email": customer_email,
                "reference": reference,
                "redirect_url": redirect_url or settings.WOMPI_REDIRECT_URL,
                "payment_method": {
                    "type": "CARD",
                    "installments": installments,
                },
                "customer_data": {
                    "phone_number": customer_phone,
                    "full_name": customer_full_name,
                },
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/transactions",
                    json=payment_data,
                    headers={
                        "Authorization": f"Bearer {self.private_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                result = response.json()

            logger.info(f"Card payment created: {result.get('data', {}).get('id')}")
            return result

        except Exception as e:
            logger.error(f"Error creating card payment: {str(e)}")
            raise

    async def create_payment_link(
        self,
        amount: int,
        reference: str,
        customer_email: str,
        description: str,
        redirect_url: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Create a payment link (supports all payment methods: PSE, cards, Nequi, etc.)
        This is the easiest way to accept payments - Wompi handles the checkout UI

        Args:
            amount: Amount in cents
            reference: Unique payment reference
            customer_email: Customer email
            description: Payment description
            redirect_url: URL to redirect after payment
            expires_at: When the link expires (default: 7 days)

        Returns:
            Dict with payment link URL
        """
        try:
            currency = "COP"
            integrity_string = f"{reference}{amount}{currency}{self.private_key}"
            integrity_signature = hashlib.sha256(integrity_string.encode()).hexdigest()

            # Default expiration: 7 days
            if not expires_at:
                expires_at = datetime.utcnow() + timedelta(days=7)

            link_data = {
                "name": description,
                "description": description,
                "single_use": True,
                "collect_shipping": False,
                "currency": currency,
                "amount_in_cents": amount,
                "redirect_url": redirect_url or settings.WOMPI_REDIRECT_URL,
                "expires_at": expires_at.isoformat(),
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/payment_links",
                    json=link_data,
                    headers={
                        "Authorization": f"Bearer {self.private_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                result = response.json()

            logger.info(f"Payment link created: {result.get('data', {}).get('id')}")
            return result

        except Exception as e:
            logger.error(f"Error creating payment link: {str(e)}")
            raise

    async def get_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """
        Get transaction details by ID

        Args:
            transaction_id: Wompi transaction ID

        Returns:
            Dict with transaction details
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/transactions/{transaction_id}",
                    headers={"Authorization": f"Bearer {self.private_key}"}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching transaction: {str(e)}")
            raise

    async def _get_acceptance_token(self) -> str:
        """
        Get acceptance token for terms and conditions
        Required for all transactions
        """
        try:
            async with httpx.AsyncClient() as client:
                # First get the current acceptance document
                response = await client.get(
                    f"{self.api_url}/merchants/{self.public_key}"
                )
                response.raise_for_status()
                merchant_data = response.json()

                presigned_acceptance = merchant_data["data"]["presigned_acceptance"]

                # Accept the terms
                acceptance_response = await client.post(
                    f"{self.api_url}/tokens/acceptance",
                    json={
                        "acceptance_token": presigned_acceptance["acceptance_token"],
                        "permalink": presigned_acceptance["permalink"],
                        "type": "END_USER_POLICY",
                    },
                    headers={"Authorization": f"Bearer {self.public_key}"}
                )
                acceptance_response.raise_for_status()
                result = acceptance_response.json()

                return result["data"]["acceptance_token"]

        except Exception as e:
            logger.error(f"Error getting acceptance token: {str(e)}")
            raise

    def verify_webhook_signature(
        self,
        signature: str,
        timestamp: str,
        request_body: str,
    ) -> bool:
        """
        Verify webhook signature from Wompi

        Args:
            signature: Signature from X-Event-Signature header
            timestamp: Timestamp from X-Event-Timestamp header
            request_body: Raw request body as string

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Wompi signature format: timestamp.request_body
            message = f"{timestamp}.{request_body}"

            # Calculate expected signature
            expected_signature = hmac.new(
                self.event_secret.encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()

            # Compare signatures
            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False

    def map_wompi_status_to_payment_status(self, wompi_status: str) -> PaymentStatus:
        """
        Map Wompi transaction status to internal PaymentStatus

        Wompi statuses: PENDING, APPROVED, DECLINED, VOIDED, ERROR
        """
        status_mapping = {
            "PENDING": PaymentStatus.PENDING,
            "APPROVED": PaymentStatus.APPROVED,
            "DECLINED": PaymentStatus.DECLINED,
            "VOIDED": PaymentStatus.VOIDED,
            "ERROR": PaymentStatus.ERROR,
        }
        return status_mapping.get(wompi_status, PaymentStatus.ERROR)
