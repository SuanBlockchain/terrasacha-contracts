# Quick Start Guide

Get your payment system running in 5 minutes!

## Prerequisites

- Python 3.9+
- PostgreSQL database
- Wompi account (https://comercios.wompi.co/)
- Binance Pay merchant account (https://merchant.binance.com/)

## Installation

### 1. Clone and Setup

```bash
cd payment-examples
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Database Setup

```bash
# Create PostgreSQL database
createdb payment_db

# Or using psql:
psql -U postgres
CREATE DATABASE payment_db;
\q
```

### 3. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/payment_db

# Wompi (from https://comercios.wompi.co/)
WOMPI_PUBLIC_KEY=pub_test_xxxxx
WOMPI_PRIVATE_KEY=prv_test_xxxxx
WOMPI_EVENT_SECRET=your_event_secret

# Binance Pay (from https://merchant.binance.com/)
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_MERCHANT_ID=your_merchant_id
```

### 4. Run the Server

```bash
uvicorn app.main:app --reload
```

Visit: http://localhost:8000/docs

## Test Your First Payment

### Option 1: PSE Payment (Colombian Bank Transfer)

```bash
# 1. Get banks list
curl http://localhost:8000/api/v1/payments/banks

# 2. Create PSE payment
curl -X POST http://localhost:8000/api/v1/payments/wompi/pse \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 50000,
    "customer_email": "test@example.com",
    "customer_phone": "3001234567",
    "customer_document_type": "CC",
    "customer_document_number": "1234567890",
    "customer_full_name": "Test User",
    "financial_institution_code": "1007",
    "user_type": "0",
    "payment_description": "Test payment"
  }'

# 3. Open the payment_url in your browser
# Customer completes payment at their bank
```

### Option 2: Crypto Payment (USDT, BTC, ETH)

```bash
curl -X POST http://localhost:8000/api/v1/payments/binance \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 50.00,
    "product_name": "Test Product",
    "customer_email": "test@example.com",
    "accepted_currencies": ["USDT", "BTC", "ETH"]
  }'

# Open the payment_url to complete crypto payment
```

## Webhook Setup (Local Testing)

### Using ngrok

```bash
# Install ngrok: https://ngrok.com/download

# In terminal 1: Run your API
uvicorn app.main:app --reload

# In terminal 2: Start ngrok
ngrok http 8000
```

You'll get a URL like: `https://abc123.ngrok.io`

Configure webhooks:
- Wompi: `https://abc123.ngrok.io/api/v1/webhooks/wompi`
- Binance: `https://abc123.ngrok.io/api/v1/webhooks/binance`

## Common Issues

### Issue: Database Connection Error

```bash
# Make sure PostgreSQL is running
sudo service postgresql start  # Linux
brew services start postgresql  # Mac

# Verify database exists
psql -U postgres -l
```

### Issue: Import Errors

```bash
# Reinstall dependencies
pip install -r requirements.txt --upgrade
```

### Issue: Wompi API Errors

- Check your API keys are correct
- Verify you're using sandbox mode keys for testing
- Check Wompi dashboard for errors

### Issue: Signature Verification Failed

- Make sure `WOMPI_EVENT_SECRET` is correct
- Verify webhook payload is not modified
- Check system time is synchronized

## What's Next?

1. **Read Examples** - See [EXAMPLES.md](EXAMPLES.md) for detailed integration examples
2. **Configure Production** - Update to production API keys when ready
3. **Add Business Logic** - Integrate with your application
4. **Test Webhooks** - Ensure webhook handlers work correctly
5. **Deploy** - Deploy to production with HTTPS

## API Documentation

Visit these URLs when server is running:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **API Root**: http://localhost:8000/

## Support

- Wompi Documentation: https://docs.wompi.co/
- Binance Pay Docs: https://developers.binance.com/docs/binance-pay
- FastAPI Docs: https://fastapi.tiangolo.com/

## Colombian Payment Tips

### PSE is Essential
- 70%+ of Colombian online shoppers use PSE
- Must support PSE to succeed in Colombian market

### Installments (Cuotas) are Popular
- Colombians prefer paying in installments
- Offer 3, 6, or 12-month options for larger amounts

### Crypto is Growing
- Colombia has high crypto adoption
- USDT/USDC popular for avoiding peso volatility
- Many use crypto for remittances

### Document Types
- **CC** (Cédula de Ciudadanía) - Colombian national ID
- **CE** (Cédula de Extranjería) - Foreign resident ID
- **NIT** - Business tax ID
- **PP** (Pasaporte) - Passport

### Phone Numbers
- Colombian mobile: Start with 3, 10 digits total
- Format: 3XX XXX XXXX
- Example: 3001234567

---

## Quick Reference

### PSE Payment Flow
1. Get banks → 2. Create payment → 3. Redirect customer → 4. Receive webhook

### Card Payment Flow
1. Create payment → 2. Customer enters card → 3. Choose installments → 4. Receive webhook

### Crypto Payment Flow
1. Create order → 2. Customer chooses crypto → 3. Send payment → 4. Receive webhook

---

Happy coding! 🚀
