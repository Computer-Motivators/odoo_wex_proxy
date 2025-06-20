import os
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import base64
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()
AUTH_TOKEN = os.getenv('AUTH_TOKEN')
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true'
WEX_API_URL = os.getenv('WEX_API_URL')
WEX_USERNAME = os.getenv('WEX_USERNAME')
WEX_PASSWORD = os.getenv('WEX_PASSWORD')
MERCHANT_CODE = os.getenv('MERCHANT_CODE', '*')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

logging.debug(f'Loaded environment variables: AUTH_TOKEN={AUTH_TOKEN}, TEST_MODE={TEST_MODE}, WEX_API_URL={WEX_API_URL}, WEX_USERNAME={WEX_USERNAME}, MERCHANT_CODE={MERCHANT_CODE}, WEBHOOK_URL={WEBHOOK_URL}')

app = Flask(__name__)

@app.route('/proxy', methods=['POST'])
def proxy():
    logging.debug('Received request at /proxy endpoint')

    # Parse and validate input JSON
    try:
        data = request.get_json(force=True)
        logging.debug(f'Received JSON payload: {data}')
    except Exception as e:
        logging.error(f'Error parsing JSON: {e}')
        return jsonify({'error': 'Invalid JSON', 'message': str(e)}), 400

    # Verify authorization token in body
    logging.debug(f'Verifying that AUTH_TOKEN=\'{AUTH_TOKEN}\' matches x_studio_proxy_auth_token=\'{data.get("x_studio_proxy_auth_token")}\'')
    if AUTH_TOKEN and data.get('x_studio_proxy_auth_token') != AUTH_TOKEN:
        logging.warning('Unauthorized access attempt')
        return jsonify({'error': 'Unauthorized'}), 401

    # Extract and validate fields
    try:
        request_id = data.get('_id') or data.get('id')
        payment_id = data['x_name']
        hauler_name = data['x_studio_vendor_name']
        amount = data['x_studio_vendor_payment_amount_requested']
        invoice_number = data['x_studio_hauler_invoice_or_remittance_advice_memo']
        employee = data.get('x_studio_employee_name')
        # Ensure amount is float
        if not isinstance(amount, (int, float)):
            amount = float(amount)
        logging.debug(f'Extracted fields: request_id={request_id}, payment_id={payment_id}, hauler_name={hauler_name}, amount={amount}, invoice_number={invoice_number}, employee={employee}')
    except Exception as e:
        logging.error(f'Error extracting fields: {e}')
        return jsonify({'error': 'Invalid input', 'message': str(e)}), 400

    # Build payload for Wex API
    payload = {
        'merchant_code': MERCHANT_CODE,
        'total_amount': amount,
        'user_defined_fields': [hauler_name, payment_id],
        'invoices': [{
            'invoice_number': invoice_number,
            'invoice_date': datetime.utcnow().isoformat() + 'Z',
            'total_amount': amount
        }]
    }
    logging.debug(f'Constructed Wex API payload: {payload}')

    # Call Wex (or simulate in test mode)
    if TEST_MODE:
        logging.info('Test mode enabled, simulating Wex API response')
        wex_status = 200
        wex_json = {
            'virtual_card': {
                'number': '4111222233334444',
                'security_code': '123',
                'expiration': '2027-09-01T00:00:00Z'
            },
            'detailed_response_message': 'Success: Test mode transaction'
        }
    else:
        try:
            logging.info('Calling Wex API')
            credentials = f"{WEX_USERNAME}:{WEX_PASSWORD}"
            encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
            auth_header = f"Basic {encoded_credentials}"

            resp = requests.post(
                WEX_API_URL,
                json=payload,
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'Authorization': auth_header
                }
            )
            wex_status = resp.status_code
            wex_json = resp.json()
            logging.debug(f'Received Wex API response: status={wex_status}, body={wex_json}')
        except Exception as e:
            logging.error(f'Wex API request failed: {e}')
            return jsonify({'status': 502, 'error': 'Wex API request failed', 'message': str(e)}), 502

    # Check for success
    msg = wex_json.get('detailed_response_message', '')
    if not (200 <= wex_status < 300 and msg.startswith('Success:')):
        logging.warning(f'Wex API call failed: status={wex_status}, message={msg}')
        error_payload = {
            '_model': 'x_requests',
            '_id': request_id,
            'status': wex_status,
            'error': msg or wex_json
        }
        # Forward error to downstream webhook
        try:
            logging.info('Forwarding error to downstream webhook')
            requests.post(WEBHOOK_URL, json=error_payload)
        except Exception as e:
            logging.error(f'Failed to forward error to webhook: {e}')
        return jsonify(error_payload), wex_status

    # Parse virtual card and build response
    vc = wex_json['virtual_card']
    date_part = vc['expiration'].split('T')[0]
    year, month, _ = date_part.split('-')
    result = {
        '_model': 'x_requests',
        '_id': request_id,
        'status': wex_status,
        'card_number': vc.get('number'),
        'expiration_month': month,
        'expiration_year': year,
        'security_code': vc.get('security_code'),
        'payment_id': payment_id,
        'amount': f"{amount:.2f}",
        'hauler_name': hauler_name,
        'employee': employee,
        'invoice_number': invoice_number
    }
    logging.debug(f'Constructed response: {result}')

    # Forward success to downstream webhook
    try:
        logging.info('Forwarding success to downstream webhook')
        requests.post(WEBHOOK_URL, json=result)
    except Exception as e:
        logging.error(f'Failed to forward success to webhook: {e}')

    return jsonify(result), 200

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))