# Payment System Examples

Complete examples for integrating Wompi PSE payments and Binance Pay cryptocurrency payments.

---

## Table of Contents

1. [PSE Payment Flow (Wompi)](#pse-payment-flow)
2. [Card Payment Flow (Wompi)](#card-payment-flow)
3. [Crypto Payment Flow (Binance Pay)](#crypto-payment-flow)
4. [Webhook Testing](#webhook-testing)
5. [Frontend Integration](#frontend-integration)

---

## PSE Payment Flow (Wompi)

### Step 1: Get Available Banks

```bash
curl -X GET http://localhost:8000/api/v1/payments/banks
```

**Response:**
```json
{
  "data": [
    {
      "financial_institution_code": "1007",
      "financial_institution_name": "BANCOLOMBIA"
    },
    {
      "financial_institution_code": "1051",
      "financial_institution_name": "DAVIVIENDA"
    },
    {
      "financial_institution_code": "1001",
      "financial_institution_name": "BANCO DE BOGOTA"
    }
  ]
}
```

### Step 2: Create PSE Payment

```bash
curl -X POST http://localhost:8000/api/v1/payments/wompi/pse \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 50000.00,
    "customer_email": "juan.perez@example.com",
    "customer_phone": "3001234567",
    "customer_document_type": "CC",
    "customer_document_number": "1234567890",
    "customer_full_name": "Juan Pérez",
    "financial_institution_code": "1007",
    "user_type": "0",
    "payment_description": "Pago de servicio mensual",
    "redirect_url": "https://mysite.com/payment/result"
  }'
```

**Response:**
```json
{
  "success": true,
  "payment_id": 1,
  "reference": "PSE-A1B2C3D4E5F6",
  "transaction_id": "12345-1234567890-12",
  "payment_url": "https://checkout.wompi.co/l/abc123xyz",
  "status": "pending",
  "amount": 50000.0,
  "currency": "COP",
  "provider": "wompi",
  "payment_method": "pse",
  "created_at": "2025-01-15T10:30:00Z"
}
```

### Step 3: Redirect Customer

Redirect the customer to the `payment_url`:

```javascript
// Frontend JavaScript
window.location.href = response.payment_url;
```

### Step 4: Customer Completes Payment

1. Customer is redirected to their bank's website
2. Customer logs into their bank account
3. Customer authorizes the PSE payment
4. Customer is redirected back to your `redirect_url`

### Step 5: Receive Webhook Notification

Your webhook endpoint will receive a POST request:

```json
{
  "event": "transaction.updated",
  "data": {
    "transaction": {
      "id": "12345-1234567890-12",
      "reference": "PSE-A1B2C3D4E5F6",
      "status": "APPROVED",
      "amount_in_cents": 5000000,
      "currency": "COP",
      "customer_email": "juan.perez@example.com",
      "payment_method_type": "PSE",
      "payment_method": {
        "type": "PSE",
        "financial_institution_code": "1007"
      }
    }
  },
  "timestamp": "2025-01-15T10:35:00Z"
}
```

### Step 6: Check Payment Status

```bash
curl -X GET http://localhost:8000/api/v1/payments/reference/PSE-A1B2C3D4E5F6
```

**Response:**
```json
{
  "id": 1,
  "reference": "PSE-A1B2C3D4E5F6",
  "status": "approved",
  "amount": 50000.0,
  "currency": "COP",
  "customer_email": "juan.perez@example.com",
  "payment_url": "https://checkout.wompi.co/l/abc123xyz",
  "created_at": "2025-01-15T10:30:00Z",
  "completed_at": "2025-01-15T10:35:00Z"
}
```

---

## Card Payment Flow (Wompi)

### Create Card Payment with Installments

```bash
curl -X POST http://localhost:8000/api/v1/payments/wompi/card \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 300000.00,
    "customer_email": "maria.garcia@example.com",
    "customer_phone": "3109876543",
    "customer_full_name": "María García",
    "installments": 6,
    "redirect_url": "https://mysite.com/payment/result"
  }'
```

**Response:**
```json
{
  "success": true,
  "payment_id": 2,
  "reference": "CARD-X1Y2Z3A4B5C6",
  "transaction_id": "12345-1234567890-13",
  "payment_url": "https://checkout.wompi.co/l/def456uvw",
  "status": "pending",
  "amount": 300000.0,
  "currency": "COP",
  "provider": "wompi",
  "payment_method": "card",
  "created_at": "2025-01-15T11:00:00Z"
}
```

Customer enters card details at the `payment_url` and chooses 6 monthly installments.

---

## Crypto Payment Flow (Binance Pay)

### Create Cryptocurrency Payment

```bash
curl -X POST http://localhost:8000/api/v1/payments/binance \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 50.00,
    "customer_email": "crypto.user@example.com",
    "product_name": "Premium Subscription",
    "product_detail": "1 month premium access",
    "accepted_currencies": ["USDT", "USDC", "BTC", "ETH"],
    "redirect_url": "https://mysite.com/payment/result"
  }'
```

**Response:**
```json
{
  "success": true,
  "payment_id": 3,
  "reference": "CRYPTO-M1N2O3P4Q5R6",
  "transaction_id": "29383937493839474747",
  "payment_url": "https://pay.binance.com/checkout/xyz789",
  "status": "pending",
  "amount": 50.0,
  "currency": "USD",
  "provider": "binance_pay",
  "payment_method": "crypto",
  "created_at": "2025-01-15T12:00:00Z"
}
```

### Customer Payment Process

1. Customer clicks the `payment_url`
2. Customer chooses cryptocurrency (USDT, BTC, ETH, etc.)
3. Customer scans QR code or copies wallet address
4. Customer sends payment from their wallet
5. Binance confirms transaction on blockchain
6. Webhook notifies your system
7. Customer is redirected to your site

### Binance Webhook Notification

```json
{
  "bizType": "PAY",
  "bizId": "29383937493839474747",
  "bizStatus": "PAID",
  "data": {
    "merchantTradeNo": "CRYPTO-M1N2O3P4Q5R6",
    "orderAmount": 50.00,
    "currency": "USD",
    "cryptocurrency": "USDT",
    "cryptoAmount": "50.00",
    "network": "TRC20",
    "transactionId": "0x1234567890abcdef",
    "payerInfo": {
      "email": "crypto.user@example.com"
    }
  }
}
```

---

## Webhook Testing

### Testing Wompi Webhooks Locally

Use ngrok to expose your local server:

```bash
# Install ngrok
# Download from https://ngrok.com/

# Start your FastAPI server
uvicorn app.main:app --reload

# In another terminal, start ngrok
ngrok http 8000
```

You'll get a public URL like: `https://abc123.ngrok.io`

Configure your webhook URL in Wompi dashboard:
```
https://abc123.ngrok.io/api/v1/webhooks/wompi
```

### Manual Webhook Testing

Test webhook endpoint with curl:

```bash
# Generate test signature
# signature = HMAC-SHA256(timestamp + "." + body, event_secret)

curl -X POST http://localhost:8000/api/v1/webhooks/wompi \
  -H "Content-Type: application/json" \
  -H "X-Event-Signature: your_calculated_signature" \
  -H "X-Event-Timestamp: 1234567890" \
  -d '{
    "event": "transaction.updated",
    "data": {
      "transaction": {
        "id": "12345-1234567890-12",
        "reference": "PSE-A1B2C3D4E5F6",
        "status": "APPROVED",
        "amount_in_cents": 5000000,
        "currency": "COP"
      }
    }
  }'
```

### Testing Binance Webhooks

```bash
curl -X POST http://localhost:8000/api/v1/webhooks/binance \
  -H "Content-Type: application/json" \
  -H "BinancePay-Signature: your_calculated_signature" \
  -H "BinancePay-Timestamp: 1234567890000" \
  -H "BinancePay-Nonce: abc123" \
  -H "BinancePay-Certificate-SN: your_api_key" \
  -d '{
    "bizType": "PAY",
    "bizId": "29383937493839474747",
    "bizStatus": "PAID",
    "data": {
      "merchantTradeNo": "CRYPTO-M1N2O3P4Q5R6",
      "orderAmount": 50.00,
      "currency": "USD",
      "cryptocurrency": "USDT"
    }
  }'
```

---

## Frontend Integration

### React Example

```javascript
import React, { useState } from 'react';

function PSEPaymentForm() {
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    const paymentData = {
      amount: 50000.00,
      customer_email: "juan.perez@example.com",
      customer_phone: "3001234567",
      customer_document_type: "CC",
      customer_document_number: "1234567890",
      customer_full_name: "Juan Pérez",
      financial_institution_code: "1007",
      user_type: "0",
      payment_description: "Pago de servicio",
      redirect_url: `${window.location.origin}/payment/result`
    };

    try {
      const response = await fetch('http://localhost:8000/api/v1/payments/wompi/pse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(paymentData)
      });

      const result = await response.json();

      if (result.success) {
        // Redirect to payment page
        window.location.href = result.payment_url;
      }
    } catch (error) {
      console.error('Payment error:', error);
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Form fields */}
      <button type="submit" disabled={loading}>
        {loading ? 'Procesando...' : 'Pagar con PSE'}
      </button>
    </form>
  );
}

export default PSEPaymentForm;
```

### Python Client Example

```python
import requests

def create_pse_payment():
    """Create PSE payment"""

    payment_data = {
        "amount": 50000.00,
        "customer_email": "juan.perez@example.com",
        "customer_phone": "3001234567",
        "customer_document_type": "CC",
        "customer_document_number": "1234567890",
        "customer_full_name": "Juan Pérez",
        "financial_institution_code": "1007",
        "user_type": "0",
        "payment_description": "Pago de servicio",
        "redirect_url": "https://mysite.com/payment/result"
    }

    response = requests.post(
        "http://localhost:8000/api/v1/payments/wompi/pse",
        json=payment_data
    )

    if response.status_code == 200:
        result = response.json()
        print(f"Payment created: {result['reference']}")
        print(f"Payment URL: {result['payment_url']}")
        return result
    else:
        print(f"Error: {response.text}")
        return None

# Create payment and get URL
payment = create_pse_payment()
```

---

## Common Colombian Payment Scenarios

### Scenario 1: PSE Payment (Most Common)

**Customer:** Colombian with bank account
**Method:** PSE
**Amount:** $50,000 COP
**Flow:** Direct bank transfer

### Scenario 2: Card Payment with Installments

**Customer:** Colombian with credit card
**Method:** Card
**Amount:** $300,000 COP
**Installments:** 6 months (cuotas)

### Scenario 3: Crypto Payment (Stablecoin)

**Customer:** Colombian or international
**Method:** Cryptocurrency
**Amount:** $50 USD
**Crypto:** USDT (Tether)
**Network:** TRC20 (low fees)

### Scenario 4: Mixed Approach

Offer multiple options:
1. **PSE** - For customers with bank accounts (most common)
2. **Card** - For customers preferring cards/installments
3. **Crypto (USDT/USDC)** - For customers wanting to avoid fees or currency conversion

---

## Error Handling

### Handling Failed Payments

```python
# Check payment status
response = requests.get(
    f"http://localhost:8000/api/v1/payments/reference/{reference}"
)

payment = response.json()

if payment['status'] == 'declined':
    # Payment was declined
    error_message = payment.get('error_message', 'Payment declined')
    print(f"Payment failed: {error_message}")

elif payment['status'] == 'expired':
    # Payment link expired
    print("Payment expired. Please create a new payment.")

elif payment['status'] == 'approved':
    # Success!
    print("Payment approved!")
```

### Webhook Retry Logic

Wompi and Binance will retry webhooks if they don't receive a 200 response:
- Wompi: Retries up to 10 times over 24 hours
- Binance: Retries up to 12 times over 24 hours

Your webhook handler should:
1. Verify signature FIRST
2. Return 200 immediately
3. Process async if needed
4. Handle duplicates (idempotency)

---

## Security Best Practices

1. **Always verify webhook signatures** - Prevents fraudulent notifications
2. **Use HTTPS in production** - Protects data in transit
3. **Store API keys in environment variables** - Never commit to version control
4. **Validate payment amounts** - Check amounts match your records
5. **Use unique references** - Prevents duplicate payments
6. **Log all transactions** - Audit trail for debugging
7. **Handle race conditions** - Webhooks may arrive out of order
8. **Implement idempotency** - Same webhook may be sent multiple times

---

## Production Checklist

- [ ] Switch to production API URLs (Wompi, Binance)
- [ ] Use production API keys
- [ ] Configure public webhook URLs (not localhost)
- [ ] Set up SSL/HTTPS certificates
- [ ] Configure CORS for your frontend domain
- [ ] Set up database backups
- [ ] Configure logging and monitoring
- [ ] Test webhook signature verification
- [ ] Test payment failure scenarios
- [ ] Set up alerts for failed payments
- [ ] Document Colombian compliance requirements (DIAN, taxes)
- [ ] Test with real bank accounts in sandbox mode first
