# Odoo Studio to Wex Proxy

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Flask](https://img.shields.io/badge/flask-latest-green.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A Flask-based API proxy that bridges Odoo and the WEX API for payment processing. It generates virtual cards for vendor payments, **reliably forwards results to Odoo with TCP-like retries + ACKs**, and includes comprehensive logging and error handling.

## 📋 Table of Contents

* [Features](#-features)
* [Project Structure](#-project-structure)
* [Prerequisites](#-prerequisites)
* [Configuration](#-configuration)
* [Development](#-development)
* [Deployment](#-deployment)
* [API Documentation](#-api-documentation)
* [Testing](#-testing)
* [Troubleshooting](#-troubleshooting)

## ✨ Features

* 🔄 **API Proxy**: Seamless integration between Odoo and the WEX API
* 💳 **Virtual Card Generation**: Automated virtual card creation for payments
* 🔐 **Authentication**: Token in **body** (`x_studio_proxy_auth_token`) **or** header (`X-Proxy-Auth-Token`)
* 📊 **Comprehensive Logging**: Structured logs for debugging and monitoring
* 🧪 **Test Mode**: Built-in simulator; no external WEX calls
* 🐳 **Docker Support**: Containerized deployment with Compose
* 📣 **Webhook Integration**: Automatic forwarding of success/error to your downstream Odoo webhook
* 🛰️ **Reliable Delivery (New)**: TCP-like retries with **ACK** from Odoo, **exponential backoff**, and **idempotency** fields (`_delivery_id`, `_delivery_attempt`)
* ⚡ **Production Ready**: Waitress WSGI server

## 📁 Project Structure

```
odoo_wex_proxy/
├── app.py                # Main Flask application
├── requirements.txt      # Python dependencies
├── Dockerfile            # Docker container configuration
├── docker-compose.yaml   # Docker Compose setup
├── .env                  # Environment variables (not in repo)
└── README.md             # This file
```

## 🔧 Prerequisites

* Python 3.11+
* Docker and Docker Compose (optional but recommended)
* WEX API credentials
* Access to the downstream Odoo webhook endpoint

## ⚙️ Configuration

Create a `.env` file in the project root:

```env
# Authentication
AUTH_TOKEN=your_secure_auth_token

# WEX API Configuration
WEX_API_URL=https://api.wex.com/merchant/log
WEX_USERNAME=your_wex_username
WEX_PASSWORD=your_wex_password
MERCHANT_CODE=*

# App Settings
TEST_MODE=false
WEBHOOK_URL=https://your-webhook-endpoint.com

# Reliable Delivery Controls (TCP-like)
MAX_DOWNSTREAM=5                       # Max delivery attempts
ACK_TIMEOUT_SECONDS=10                 # Wait for ACK after each attempt
DOWNSTREAM_RETRY_BASE_SECONDS=2        # Backoff base: 2,4,8,...
DOWNSTREAM_POST_TIMEOUT_SECONDS=10     # HTTP timeout per attempt
```

### Environment Variables

| Variable                          | Description                                                                                            | Required | Default |
| --------------------------------- | ------------------------------------------------------------------------------------------------------ | -------- | ------- |
| `AUTH_TOKEN`                      | Token for securing `/proxy` & `/ack` (body `x_studio_proxy_auth_token` or header `X-Proxy-Auth-Token`) | No       | None    |
| `WEX_API_URL`                     | WEX API endpoint URL                                                                                   | Yes      | —       |
| `WEX_USERNAME`                    | WEX API username                                                                                       | Yes      | —       |
| `WEX_PASSWORD`                    | WEX API password                                                                                       | Yes      | —       |
| `MERCHANT_CODE`                   | Merchant identifier for WEX                                                                            | No       | `*`     |
| `TEST_MODE`                       | Simulate WEX responses                                                                                 | No       | `false` |
| `WEBHOOK_URL`                     | Downstream Odoo webhook URL                                                                            | Yes      | —       |
| `MAX_DOWNSTREAM`                  | Max downstream attempts (success only)                                                                 | No       | `5`     |
| `ACK_TIMEOUT_SECONDS`             | Seconds to wait for ACK per attempt                                                                    | No       | `10`    |
| `DOWNSTREAM_RETRY_BASE_SECONDS`   | Exponential backoff base seconds                                                                       | No       | `2`     |
| `DOWNSTREAM_POST_TIMEOUT_SECONDS` | Timeout for each POST to webhook                                                                       | No       | `10`    |

**Idempotency:** Each downstream delivery includes `_delivery_id` (stable UUID for the success) and `_delivery_attempt` (1..N). Your Odoo intake should de-duplicate by `_delivery_id` (or by `payment_id` if you prefer).

## 💻 Development

### Running Locally

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export FLASK_ENV=development
export FLASK_DEBUG=1
python app.py
```

App listens on `http://localhost:5000`.

### Development with Test Mode

```bash
export TEST_MODE=true
python app.py
```

## 🚢 Deployment

### Docker Compose (Recommended)

1. **Configure environment variables**

   ```bash
   cp .env.example .env  # or create .env from the snippet above
   ```

2. **Deploy**

   ```bash
   docker-compose up -d
   ```

3. **Check status & logs**

   ```bash
   docker-compose ps
   docker-compose logs -f odoo_wex_proxy
   ```

Service is available at `http://localhost:8844`.

### Manual Docker

```bash
docker build -t odoo_wex_proxy .
docker run -d \
  --name wex_docker \
  -p 8844:5000 \
  --env-file .env \
  odoo_wex_proxy
```

## 📚 API Documentation

### POST `/proxy`

Processes a payment request from Odoo, calls WEX (or simulates), and **starts reliable downstream delivery** to `WEBHOOK_URL`. The HTTP response to the caller is immediate; retries happen in the background until an **ACK** is received.

#### Request Body

Either send the token in the body **or** the header.

**Body fields:**

```json
{
  "x_studio_proxy_auth_token": "your_auth_token",
  "_id": "unique_request_id",
  "x_name": "payment_id",
  "x_studio_vendor_name": "Vendor Company Name",
  "x_studio_vendor_payment_amount_requested": 150.00,
  "x_studio_hauler_invoice_or_remittance_advice_memo": "INV12345",
  "x_studio_employee_name": "John Doe"
}
```

**Header alternative:**

```
X-Proxy-Auth-Token: your_auth_token
```

#### Success Response (200)

> This is the synchronous response to the caller.
> The **downstream webhook** will receive the same object **plus** `_delivery_id` and `_delivery_attempt`.

```json
{
  "_model": "x_requests",
  "_id": "unique_request_id",
  "status": 200,
  "card_number": "4111222233334444",
  "expiration_month": "09",
  "expiration_year": "2027",
  "security_code": "123",
  "payment_id": "payment_id",
  "amount": "150.00",
  "hauler_name": "Vendor Company Name",
  "employee": "John Doe",
  "invoice_number": "INV12345"
}
```

**Downstream delivery (example extra fields):**

```json
{
  "...": "...",
  "_delivery_id": "e8f0e6e8-1a9b-4d2f-8f7f-2a3b4c5d6e7f",
  "_delivery_attempt": 2
}
```

#### Error Response (4xx/5xx)

(Forwarded **once** to the downstream webhook; no retries.)

```json
{
  "_model": "x_requests",
  "_id": "unique_request_id",
  "status": 400,
  "error": "Error message from WEX API"
}
```

---

### POST `/ack`  **(New)**

Odoo must call this to acknowledge successful processing of a **success** delivery. The proxy stops retrying once it receives the ACK.

#### Request Body

```json
{
  "payment_id": "payment_id",               // or "x_name"
  "x_studio_proxy_auth_token": "your_auth_token"
}
```

**Header alternative:**

```
X-Proxy-Auth-Token: your_auth_token
```

#### Response (200)

```json
{
  "status": "acknowledged",
  "payment_id": "payment_id"
}
```

> Tip: If your Odoo intake is idempotent, you can safely ACK the first time you see a `_delivery_id` you haven’t processed yet.

## 🧪 Testing

### Manual Testing (success path)

1. **Kick off a payment (test mode shown here):**

   ```bash
   curl -X POST http://localhost:8844/proxy \
     -H "Content-Type: application/json" \
     -H "X-Proxy-Auth-Token: your_token" \
     -d '{
       "_id": "test-123",
       "x_name": "PAY-001",
       "x_studio_vendor_name": "Test Vendor",
       "x_studio_vendor_payment_amount_requested": 100.50,
       "x_studio_hauler_invoice_or_remittance_advice_memo": "TEST-INV-001",
       "x_studio_employee_name": "Test Employee"
     }'
   ```

2. **Simulate Odoo’s ACK once your webhook receives the success:**

   ```bash
   curl -X POST http://localhost:8844/ack \
     -H "Content-Type: application/json" \
     -H "X-Proxy-Auth-Token: your_token" \
     -d '{ "payment_id": "PAY-001" }'
   ```

Observe logs for retry attempts and the “ACK received” message.

## 🔍 Troubleshooting

### Not receiving downstream deliveries

* Confirm `WEBHOOK_URL` is reachable from the container (network/firewall).
* Ensure your Odoo endpoint returns **200 OK** (failures still count as “no ACK”).
* Watch logs for lines like: `No ACK yet ... sleeping ...` — tune:

  * `ACK_TIMEOUT_SECONDS` (increase wait per attempt)
  * `MAX_DOWNSTREAM` (more attempts)
  * `DOWNSTREAM_RETRY_BASE_SECONDS` (slower/faster backoff)

### Duplicates at Odoo

* Deduplicate on `_delivery_id` (recommended) or `payment_id`.
* ACK promptly after persisting; retries stop immediately on ACK.

### Auth errors

* Use **either** body `x_studio_proxy_auth_token` **or** header `X-Proxy-Auth-Token`.
* Verify `AUTH_TOKEN` in `.env`.

### WEX API errors

* Check credentials and `WEX_API_URL`.
* Use `TEST_MODE=true` to isolate proxy logic from WEX.

### Logging

```bash
# Docker Compose
docker-compose logs -f odoo_wex_proxy

# Docker
docker logs -f wex_docker

# Local
# Logs print to console (DEBUG by default)
```

### Health

* Use container status + logs (`docker ps`, `docker logs`).
* Optionally add your own healthcheck in Compose that curls `/proxy` with `-X OPTIONS` or hits your Odoo webhook from a separate monitor.

## 📄 License

MIT — see [LICENSE](LICENSE).

## 📞 Support

For support and questions:

* Check [Troubleshooting](#-troubleshooting)
* Review application logs
* Contact **Computer Motivators**: [https://www.computermotivators.com](https://www.computermotivators.com)

---

Built with ❤️ for our client in waste management.
