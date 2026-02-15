# PaymentService API

## Quick Start

```bash
pip install payment-service==1.2.3
```

## Authentication

All requests require an API key passed via the `X-Api-Key` header:

```bash
curl -H "X-Api-Key: your-key" https://api.payment.example.com/v1/charge
```

## Endpoints

### POST /v1/charge

Create a new charge.

**Request:**
```json
{
  "amount": 1000,
  "currency": "usd",
  "source": "tok_visa",
  "description": "Test charge"
}
```

**Response:**
```json
{
  "id": "ch_123",
  "status": "succeeded",
  "amount": 1000
}
```

### GET /v1/charges/{id}

Retrieve a charge by ID. Returns the same schema as POST.

### POST /v2/payments

> **Note:** v2 API uses OAuth2 instead of API keys.

Create a payment intent.

**Request:**
```json
{
  "amount": 1000,
  "currency": "usd",
  "payment_method": "pm_card_visa"
}
```

**Response (v2):**
```json
{
  "id": "pi_456",
  "status": "requires_confirmation",
  "client_secret": "pi_456_secret_789"
}
```

## Error Handling

All errors return HTTP 400 with a JSON body:

```json
{
  "error": {
    "code": "invalid_amount",
    "message": "Amount must be positive"
  }
}
```

Note: v2 errors use a different format (see v2 migration guide, link TBD).

## Rate Limits

- Free tier: 100 requests/minute
- Pro tier: 1000 requests/minute

Exceeding limits returns HTTP 429.

## Changelog

- v1.2.3 (2024-01-15): Added `description` field to charges
- v1.2.0 (2023-09-01): Initial release
