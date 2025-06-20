# Odoo Studio to Wex Proxy

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Flask](https://img.shields.io/badge/flask-latest-green.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A Flask-based API proxy service that interfaces between Odoo and the WEX API for payment processing. This service handles virtual card generation for vendor payments with comprehensive logging and error handling.

## 📋 Table of Contents

- [Features](#-features)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Development](#-development)
- [Deployment](#-deployment)
- [API Documentation](#-api-documentation)
- [Testing](#-testing)
- [Troubleshooting](#-troubleshooting)

## ✨ Features

- 🔄 **API Proxy**: Seamless integration between Odoo and WEX API
- 💳 **Virtual Card Generation**: Automated virtual card creation for payments
- 🔐 **Authentication**: Token-based security for API endpoints
- 📊 **Comprehensive Logging**: Detailed logging for debugging and monitoring
- 🧪 **Test Mode**: Built-in test mode for development and testing
- 🐳 **Docker Support**: Containerized deployment with Docker Compose
- 🔄 **Webhook Integration**: Automatic forwarding of responses to downstream systems
- ⚡ **Production Ready**: Uses Waitress WSGI server for production deployment

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

- Python 3.11+
- Docker and Docker Compose (for containerized deployment)
- WEX API credentials
- Access to target webhook endpoint

## ⚙️ Configuration

Create a `.env` file in the project root with the following variables:

```env
# Authentication
AUTH_TOKEN=your_secure_auth_token

# WEX API Configuration
WEX_API_URL=https://api.wex.com/endpoint
WEX_USERNAME=your_wex_username
WEX_PASSWORD=your_wex_password
MERCHANT_CODE=*

# Application Settings
TEST_MODE=false
WEBHOOK_URL=https://your-webhook-endpoint.com
```

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `AUTH_TOKEN` | Authentication token for API security | No | None |
| `WEX_API_URL` | WEX API endpoint URL | Yes | None |
| `WEX_USERNAME` | WEX API username | Yes | None |
| `WEX_PASSWORD` | WEX API password | Yes | None |
| `MERCHANT_CODE` | Merchant identifier for WEX | No | `*` |
| `TEST_MODE` | Enable test mode (true/false) | No | `false` |
| `WEBHOOK_URL` | Downstream webhook URL | Yes | None |

## 💻 Development

### Running Locally

```bash
# Activate virtual environment
source venv/bin/activate

# Set environment variables
export FLASK_ENV=development
export FLASK_DEBUG=1

# Run the application
python app.py
```

The application will be available at `http://localhost:5000`

### Development with Test Mode

Enable test mode to simulate WEX API responses:

```bash
export TEST_MODE=true
python app.py
```

## 🚢 Deployment

### Docker Compose (Recommended)

1. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

2. **Deploy the service**
   ```bash
   docker-compose up -d
   ```

3. **Check service status**
   ```bash
   docker-compose ps
   docker-compose logs odoo_wex_proxy
   ```

The service will be available at `http://localhost:8844`

### Manual Docker Deployment

```bash
# Build the image
docker build -t odoo_wex_proxy .

# Run the container
docker run -d \
  --name wex_docker \
  -p 8844:5000 \
  --env-file .env \
  odoo_wex_proxy
```

## 📚 API Documentation

### POST /proxy

Processes payment requests and generates virtual cards through the WEX API.

#### Request Body

```json
{
  "auth_token": "your_auth_token",
  "_id": "unique_request_id",
  "x_name": "payment_id",
  "x_studio_vendor_name": "Vendor Company Name",
  "x_studio_vendor_payment_amount_requested": 150.00,
  "x_studio_hauler_invoice_or_remittance_advice_memo": "INV12345",
  "x_studio_employee_name": "John Doe"
}
```

#### Success Response (200)

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

#### Error Response (4xx/5xx)

```json
{
  "_model": "x_requests",
  "_id": "unique_request_id",
  "status": 400,
  "error": "Error message from WEX API"
}
```

## 🧪 Testing

### Manual Testing

Use curl or any HTTP client to test the endpoint:

```bash
curl -X POST http://localhost:8844/proxy \
  -H "Content-Type: application/json" \
  -d '{
    "auth_token": "your_token",
    "_id": "test-123",
    "x_name": "PAY-001",
    "x_studio_vendor_name": "Test Vendor",
    "x_studio_vendor_payment_amount_requested": 100.50,
    "x_studio_hauler_invoice_or_remittance_advice_memo": "TEST-INV-001",
    "x_studio_employee_name": "Test Employee"
  }'
```

### Test Mode

Enable test mode for development:

```bash
export TEST_MODE=true
```

In test mode, the application simulates WEX API responses without making actual API calls.

## 🔍 Troubleshooting

### Common Issues

1. **Port already in use**
   ```bash
   # Check what's using the port
   lsof -i :8844
   # Kill the process or change the port in docker-compose.yaml
   ```

2. **Environment variables not loaded**
   ```bash
   # Verify .env file exists and has correct format
   cat .env
   # Restart the container
   docker-compose restart
   ```

3. **WEX API authentication errors**
   - Verify `WEX_USERNAME` and `WEX_PASSWORD` are correct
   - Check `WEX_API_URL` is accessible
   - Ensure credentials are properly base64 encoded

### Logging

The application provides comprehensive logging. Check logs with:

```bash
# Docker Compose
docker-compose logs -f odoo_wex_proxy

# Docker
docker logs -f wex_docker

# Local development
# Logs are printed to console
```

### Health Check

Verify the service is running:

```bash
# Check if the service responds
curl -X GET http://localhost:8844/
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

For support and questions:
- Check the [Troubleshooting](#-troubleshooting) section
- Review application logs
- Contact us at [Computer Motivators](https://www.computermotivators.com)

---

Built with ❤️ for our client in waste management