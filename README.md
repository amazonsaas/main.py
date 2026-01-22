# Amazon Product Verdict API

A FastAPI microservice that analyzes Amazon products and provides a verdict based on Best Sellers Rank (BSR) and reviews count.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Service

### Option 1: Using uvicorn directly
```bash
uvicorn main:app --reload
```

### Option 2: Using Python
```bash
python main.py
```

The API will be available at: `http://localhost:8000`

## API Endpoints

### GET /
Returns API information

### POST /verdict
Analyzes an Amazon product URL and returns a verdict.

**Request Body:**
```json
{
  "url": "https://www.amazon.com/dp/B08N5WRWNW"
}
```

**Response:**
```json
{
  "product_title": "Product Name",
  "price": "$29.99",
  "reviews_count": 150,
  "bsr": 15000,
  "verdict": "✅ SELL"
}
```

## Verdict Logic

- **✅ SELL**: BSR < 20000 AND Reviews < 200
- **❌ AVOID**: Reviews > 1000
- **⚠️ RISKY**: All other cases

## API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
