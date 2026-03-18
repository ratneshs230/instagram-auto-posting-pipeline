#!/usr/bin/env python3
"""
Webhook Orchestrator (Reusable Template)
========================================
Starts the Flask webhook server + auto-responder in separate threads
and monitors system health.

Usage:
    python orchestrator.py          # Production mode
    python orchestrator.py --test   # Test with sample events
"""

import sys
import json
import time
import signal
import logging
import argparse
from datetime import datetime
from webhook_server import app, webhook_queue
from auto_responder import InstagramResponder
from config import PROJECT_NAME, WEBHOOK_PORT

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('orchestrator.log')],
)
logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self):
        self.running = False
        self.threads = []
        self.responder = InstagramResponder()
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, *_):
        logger.info("Shutting down...")
        self.stop()
        sys.exit(0)

    def start(self):
        import threading

        self.running = True

        # Start Flask in a daemon thread
        t1 = threading.Thread(target=lambda: app.run(
            host='0.0.0.0', port=WEBHOOK_PORT, debug=False, use_reloader=False), daemon=True)
        t1.start()
        self.threads.append(t1)
        time.sleep(2)

        # Start responder in a daemon thread
        t2 = threading.Thread(target=lambda: self.responder.run(webhook_queue), daemon=True)
        t2.start()
        self.threads.append(t2)

        print(f"\n{'=' * 50}")
        print(f"  {PROJECT_NAME} — Webhook Auto-Responder")
        print(f"{'=' * 50}")
        print(f"  Webhook : http://localhost:{WEBHOOK_PORT}/webhook")
        print(f"  Health  : http://localhost:{WEBHOOK_PORT}/health")
        print(f"  Ctrl+C to stop")
        print(f"{'=' * 50}\n")

        # Monitor loop
        while self.running:
            try:
                stats = self.responder.get_stats()
                qs = webhook_queue.qsize()
                logger.info(f"Queue: {qs} | Comments: {stats['comments_responded']}/{stats['comments_processed']} | "
                            f"DMs: {stats['dms_responded']}/{stats['dms_processed']} | Errors: {stats['errors']}")

                with open('system_status.json', 'w') as f:
                    json.dump({'timestamp': datetime.now().isoformat(), 'queue': qs, 'stats': stats}, f, indent=2)

                time.sleep(30)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(10)

    def stop(self):
        self.running = False
        stats = self.responder.get_stats()
        with open('final_stats.json', 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"\nFinal stats: {json.dumps(stats, indent=2)}")


def test_mode():
    """Inject sample events and process them."""
    samples = [
        {'type': 'comment', 'comment_id': 'test_1', 'text': 'Send pic please!',
         'username': 'test_user', 'media_id': 'media_1'},
        {'type': 'comment', 'comment_id': 'test_2', 'text': 'Would love to collaborate!',
         'username': 'creator_test', 'media_id': 'media_2'},
        {'type': 'direct_message', 'message_id': 'dm_1',
         'text': 'Hi! Can we feature each other?', 'sender_id': 'sender_1'},
    ]
    for e in samples:
        webhook_queue.put(e)

    orch = Orchestrator()
    time.sleep(15)
    print(json.dumps(orch.responder.get_stats(), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()

    if args.test:
        test_mode()
    else:
        Orchestrator().start()
