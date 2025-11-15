# Payment System API - Wompi & Binance Pay Integration

This is a complete FastAPI implementation for accepting payments in Colombia through:
- **Wompi**: PSE, cards, Nequi, cash networks (Efecty, Baloto)
- **Binance Pay**: Cryptocurrency payments

## Features

- PSE (Colombian bank transfers) integration
- Credit/debit card payments
- Cryptocurrency payments via Binance Pay
- Secure webhook handling with signature verification
- Payment status tracking
- Error handling and logging
- Database integration with SQLAlchemy

## Project Structure

```
payment-examples/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration
│   ├── database.py             # Database setup
│   ├── models/
│   │   ├── __init__.py
│   │   └── payment.py          # Payment database models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── wompi_service.py    # Wompi integration
│   │   └── binance_service.py  # Binance Pay integration
│   └── routers/
│       ├── __init__.py
│       ├── payments.py         # Payment endpoints
│       └── webhooks.py         # Webhook handlers
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

3. Update `.env` with your credentials

4. Run the application:
```bash
uvicorn app.main:app --reload
```

## API Endpoints

### Payment Creation
- `POST /api/v1/payments/wompi/pse` - Create PSE payment
- `POST /api/v1/payments/wompi/card` - Create card payment
- `POST /api/v1/payments/binance` - Create crypto payment

### Webhooks
- `POST /api/v1/webhooks/wompi` - Wompi webhook handler
- `POST /api/v1/webhooks/binance` - Binance Pay webhook handler

### Payment Status
- `GET /api/v1/payments/{payment_id}` - Get payment status

## Testing

Use the provided examples to test payment creation and webhook handling.

## Security

- All webhooks validate signatures before processing
- Environment variables for sensitive data
- Proper error handling and logging
- Database transactions for payment updates

## Documentation

Once running, visit:
- API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
