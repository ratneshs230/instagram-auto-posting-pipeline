#!/usr/bin/env python3
"""
Instagram Webhook Server (Reusable Template)
=============================================
Receives webhook notifications for comments, mentions, and DMs.
Puts events into a queue for the auto-responder to process.
"""

import json
import hmac
import hashlib
import logging
import queue
import threading
from datetime import datetime
from flask import Flask, request, jsonify

from config import WEBHOOK_VERIFY_TOKEN, WEBHOOK_PORT, CREDENTIALS_FILE, GRAPH_API_BASE, GRAPH_API_VERSION

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('webhook_server.log')],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
webhook_queue = queue.Queue()


def _load_app_secret() -> str:
    """Load Instagram App Secret from credentials file."""
    try:
        with open(CREDENTIALS_FILE, 'r') as f:
            for line in f:
                if line.strip().startswith('Instagram App Secret'):
                    return line.strip().split('=', 1)[1].strip()
    except Exception as e:
        logger.error(f"Failed to load app secret: {e}")
    return ""


APP_SECRET = _load_app_secret()


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify webhook HMAC-SHA256 signature from Instagram."""
    if not APP_SECRET:
        logger.warning("App secret not configured, skipping signature verification")
        return True
    expected = hmac.new(APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


# ---------------------------------------------------------------------------
# Webhook Endpoint
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """Handle webhook verification (GET) and event delivery (POST)."""
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == WEBHOOK_VERIFY_TOKEN:
            logger.info("Webhook verified")
            return challenge
        return 'Forbidden', 403

    # POST — incoming event
    sig = request.headers.get('X-Hub-Signature-256', '')
    if not verify_signature(request.data, sig):
        return 'Unauthorized', 401

    data = request.json
    logger.info(f"Webhook event received: {json.dumps(data, indent=2)[:300]}")

    # Parse and enqueue events in background
    threading.Thread(target=_process_entries, args=(data,), daemon=True).start()
    return 'OK', 200


def _process_entries(data: dict):
    """Parse webhook payload and enqueue events."""
    for entry in data.get('entry', []):
        # Comments & mentions
        for change in entry.get('changes', []):
            field = change.get('field')
            value = change.get('value', {})

            if field == 'comments':
                from_user = value.get('from', {})
                webhook_queue.put({
                    'type': 'comment',
                    'comment_id': value.get('id'),
                    'text': value.get('text', ''),
                    'username': from_user.get('username', 'Unknown'),
                    'user_id': from_user.get('id'),
                    'media_id': value.get('media', {}).get('id'),
                    'timestamp': datetime.now().isoformat(),
                })
            elif field == 'mentions':
                webhook_queue.put({
                    'type': 'mention',
                    'comment_id': value.get('comment_id'),
                    'media_id': value.get('media_id'),
                    'timestamp': datetime.now().isoformat(),
                })

        # Direct messages
        for msg in entry.get('messaging', []):
            if 'message' in msg:
                m = msg['message']
                webhook_queue.put({
                    'type': 'direct_message',
                    'sender_id': msg.get('sender', {}).get('id'),
                    'text': m.get('text', ''),
                    'message_id': m.get('mid'),
                    'timestamp': datetime.now().isoformat(),
                })


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'queue_size': webhook_queue.qsize(),
                    'timestamp': datetime.now().isoformat()})


@app.route('/queue/status', methods=['GET'])
def queue_status():
    return jsonify({'queue_size': webhook_queue.qsize(),
                    'timestamp': datetime.now().isoformat()})


if __name__ == '__main__':
    logger.info(f"Starting webhook server on port {WEBHOOK_PORT}")
    app.run(host='0.0.0.0', port=WEBHOOK_PORT, debug=False)
