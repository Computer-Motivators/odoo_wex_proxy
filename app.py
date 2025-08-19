import os
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import base64
import logging
import time
import uuid
import random
from threading import Event, Lock, Thread

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

# New env-driven controls for TCP-like downstream delivery
try:
    MAX_DOWNSTREAM = int(os.getenv('MAX_DOWNSTREAM', '5') or '5')
except ValueError:
    MAX_DOWNSTREAM = 5
try:
    ACK_TIMEOUT_SECONDS = int(os.getenv('ACK_TIMEOUT_SECONDS', '10') or '10')
except ValueError:
    ACK_TIMEOUT_SECONDS = 10
try:
    DOWNSTREAM_RETRY_BASE_SECONDS = int(os.getenv('DOWNSTREAM_RETRY_BASE_SECONDS', '2') or '2')
except ValueError:
    DOWNSTREAM_RETRY_BASE_SECONDS = 2
try:
    DOWNSTREAM_POST_TIMEOUT_SECONDS = int(os.getenv('DOWNSTREAM_POST_TIMEOUT_SECONDS', '10') or '10')
except ValueError:
    DOWNSTREAM_POST_TIMEOUT_SECONDS = 10

# Mask sensitive values in logs
logging.debug(
    f'Loaded env: TEST_MODE={TEST_MODE}, WEX_API_URL={WEX_API_URL}, '
    f'MERCHANT_CODE={MERCHANT_CODE}, WEBHOOK_URL={WEBHOOK_URL}, '
    f'MAX_DOWNSTREAM={MAX_DOWNSTREAM}, ACK_TIMEOUT_SECONDS={ACK_TIMEOUT_SECONDS}, '
    f'DOWNSTREAM_RETRY_BASE_SECONDS={DOWNSTREAM_RETRY_BASE_SECONDS}, '
    f'DOWNSTREAM_POST_TIMEOUT_SECONDS={DOWNSTREAM_POST_TIMEOUT_SECONDS}'
)

app = Flask(__name__)

# ---- ACK tracking (payment_id -> Event) ----
_ACK_EVENTS = {}
_ACK_LOCK = Lock()

def _get_or_create_ack_event(payment_id: str) -> Event:
    with _ACK_LOCK:
        ev = _ACK_EVENTS.get(payment_id)
        if ev is None:
            ev = Event()
            _ACK_EVENTS[payment_id] = ev
        return ev

def _clear_ack_event(payment_id: str) -> None:
    with _ACK_LOCK:
        _ACK_EVENTS.pop(payment_id, None)

def _verify_auth_from_body_or_header(req_json):
    token = None
    if isinstance(req_json, dict):
        token = req_json.get('x_studio_proxy_auth_token')
    if not token:
        token = request.headers.get('X-Proxy-Auth-Token')
    if AUTH_TOKEN and token != AUTH_TOKEN:
        return False
    return True

def _forward_with_ack(payload: dict, payment_id: str):
    """
    Attempt to deliver payload to WEBHOOK_URL until we receive an ACK for payment_id
    via POST /ack. Exponential backoff between attempts. Stops early upon ACK.
    """
    ev = _get_or_create_ack_event(payment_id)
    delivery_id = payload.get('_delivery_id') or str(uuid.uuid4())
    attempts = MAX_DOWNSTREAM

    for attempt in range(1, attempts + 1):
        try:
            enriched = dict(payload)
            enriched['_delivery_id'] = delivery_id
            enriched['_delivery_attempt'] = attempt
            logging.info(f'Forwarding to downstream (attempt {attempt}/{attempts}) for payment_id={payment_id}')
            requests.post(
                WEBHOOK_URL,
                json=enriched,
                timeout=DOWNSTREAM_POST_TIMEOUT_SECONDS
            )
        except Exception as e:
            logging.error(f'POST to downstream failed on attempt {attempt}: {e}')

        logging.debug(f'Waiting up to {ACK_TIMEOUT_SECONDS}s for ACK of payment_id={payment_id}')
        if ev.wait(timeout=ACK_TIMEOUT_SECONDS):
            logging.info(f'ACK received for payment_id={payment_id}. Stopping retries.')
            _clear_ack_event(payment_id)
            return

        if attempt < attempts:
            # Exponential backoff with light jitter (+/- 20%)
            base = DOWNSTREAM_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            jitter = base * (random.uniform(-0.2, 0.2))
            sleep_s = max(1, int(base + jitter))
            logging.warning(f'No ACK yet for payment_id={payment_id}; sleeping {sleep_s}s before retry.')
            time.sleep(sleep_s)

    logging.error(f'No ACK after {attempts} attempts for payment_id={payment_id}. Giving up.')
    _clear_ack_event(payment_id)

@app.route('/ack', methods=['POST'])
def ack():
    """
    Odoo calls this to acknowledge receipt/processing of a previously delivered success payload.
    Body must include: { "payment_id": "...", "x_studio_proxy_auth_token": "..." }
    """
    try:
        data = request.get_json(force=True)
    except Exception as e:
        logging.error(f'ACK endpoint: invalid JSON: {e}')
        return jsonify({'error': 'Invalid JSON', 'message': str(e)}), 400

    if not _verify_auth_from_body_or_header(data):
        logging.warning('ACK endpoint: unauthorized')
        return jsonify({'error': 'Unauthorized'}), 401

    payment_id = data.get('payment_id') or data.get('x_name')
    if not payment_id:
        logging.warning('ACK endpoint: missing payment_id')
        return jsonify({'error': 'Missing payment_id'}), 400

    ev = _get_or_create_ack_event(payment_id)
    ev.set()
    logging.info(f'ACK set for payment_id={payment_id}')
    return jsonify({'status': 'acknowledged', 'payment_id': payment_id}), 200

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

    # Verify authorization token in body/header
    if not _verify_auth_from_body_or_header(data):
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
        logging.debug(
            f'Extracted fields: request_id={request_id}, payment_id={payment_id}, '
            f'hauler_name={hauler_name}, amount={amount}, invoice_number={invoice_number}, employee={employee}'
        )
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
        # Forward error to downstream webhook (single shot)
        try:
            logging.info('Forwarding error to downstream webhook (no retry)')
            requests.post(WEBHOOK_URL, json=error_payload, timeout=DOWNSTREAM_POST_TIMEOUT_SECONDS)
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
        # Optionally include: 'ack_url': f"{request.url_root.rstrip('/')}/ack"
    }
    logging.debug(f'Constructed response: {result}')

    # Start TCP-like downstream delivery in background
    try:
        logging.info('Starting background delivery with ACK tracking')
        t = Thread(target=_forward_with_ack, args=(result, payment_id), daemon=True)
        t.start()
    except Exception as e:
        logging.error(f'Failed to start delivery thread: {e}')

    # Respond to caller immediately
    return jsonify(result), 200

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
