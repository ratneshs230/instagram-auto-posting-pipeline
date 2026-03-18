#!/usr/bin/env python3
"""
Instagram Auto-Responder (Reusable Template)
=============================================
Processes webhook events from the queue and sends AI-generated responses
via the Facebook Graph API.
"""

import os
import json
import time
import queue
import random
import logging
import requests
import google.generativeai as genai
from datetime import datetime
from typing import Dict, Optional

from config import (
    PROJECT_NAME, CREDENTIALS_FILE,
    GRAPH_API_BASE, GRAPH_API_VERSION,
    RESPONDER_MODEL, SAFETY_SETTINGS,
    RESPONSE_DELAY_SECONDS, MAX_CACHE_SIZE,
    RESPONDER_PERSONALITY, RESPONSE_TEMPLATES, INTENT_KEYWORDS,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('auto_responder.log')],
)
logger = logging.getLogger(__name__)

GRAPH = f"{GRAPH_API_BASE}/{GRAPH_API_VERSION}"


# ===================================================================
# Credentials
# ===================================================================

def _load_credentials() -> Dict:
    creds = {}
    with open(CREDENTIALS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line and '=' in line:
                k, v = line.split('=', 1)
                creds[k.strip().lower()] = v.strip()
    return creds


def _load_gemini_keys() -> list:
    with open(CREDENTIALS_FILE, 'r') as f:
        for line in f:
            if 'GEMINI_API_KEYS' in line:
                _, keys = line.strip().split('=', 1)
                return [k.strip() for k in keys.split(',') if k.strip()]
    return []


# ===================================================================
# Intent Detection
# ===================================================================

def detect_intent(text: str) -> Dict:
    """Classify comment intent using keyword matching."""
    lower = text.lower()
    intent = {
        'is_spam': any(p in lower for p in INTENT_KEYWORDS['spam_patterns']),
        'is_collaboration': any(k in lower for k in INTENT_KEYWORDS['collab_keywords']),
        'is_appreciation': any(k in lower for k in INTENT_KEYWORDS['appreciation_keywords']),
        'is_question': '?' in text or any(w in lower for w in ['what', 'where', 'when', 'how', 'why']),
    }
    return intent


def should_respond(text: str, username: str, own_handle: str) -> bool:
    """Decide whether to respond to a comment."""
    if username.lower() == own_handle.lower():
        return False
    if len(text.strip()) < 2:
        return False

    intent = detect_intent(text)
    if intent['is_question'] or intent['is_collaboration'] or intent['is_spam']:
        return True
    if intent['is_appreciation']:
        return random.random() < 0.5
    return random.random() < 0.3


# ===================================================================
# AI Response Generation
# ===================================================================

class AIResponder:
    """Generates responses using Gemini AI with key rotation."""

    def __init__(self):
        self.api_keys = _load_gemini_keys()
        self.idx = 0
        self._configure()

    def _configure(self):
        if self.api_keys:
            genai.configure(api_key=self.api_keys[self.idx])
            self.model = genai.GenerativeModel(RESPONDER_MODEL, safety_settings=SAFETY_SETTINGS)

    def _rotate(self):
        self.idx = (self.idx + 1) % len(self.api_keys)
        self._configure()

    def generate(self, text: str, username: str, context_type: str = 'comment') -> str:
        """Generate a response, falling back to templates on error."""
        intent = detect_intent(text)

        # Use template for clear intents
        if intent['is_spam'] and 'spam_pic_request' in RESPONSE_TEMPLATES:
            return random.choice(RESPONSE_TEMPLATES['spam_pic_request']).format(username=username)
        if intent['is_collaboration'] and 'collaboration' in RESPONSE_TEMPLATES:
            return random.choice(RESPONSE_TEMPLATES['collaboration']).format(username=username)
        if intent['is_appreciation'] and not intent['is_question'] and random.random() < 0.5:
            return random.choice(RESPONSE_TEMPLATES.get('appreciation', [])).format(username=username)

        # AI-generated response
        try:
            prompt = RESPONDER_PERSONALITY.format(project_name=PROJECT_NAME)
            prompt += f"\n\nFrom: @{username}\n{context_type.title()}: \"{text}\"\n\nResponse:"
            resp = self.model.generate_content(prompt)
            if resp and resp.text:
                reply = resp.text.strip('"\'')
                if username.lower() not in reply.lower():
                    reply = f"@{username} {reply}"
                return reply[:280]
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            self._rotate()

        # Final fallback
        return f"Thanks for your comment @{username}!"


# ===================================================================
# Instagram API Actions
# ===================================================================

class InstagramResponder:
    """Processes webhook events and responds via Graph API."""

    def __init__(self):
        self.credentials = _load_credentials()
        self.access_token = self.credentials.get('access token', '')
        self.ig_account_id = self.credentials.get('instagram account id', '')
        self.own_handle = self.credentials.get('instagram handle', '')
        self.ai = AIResponder()

        # Duplicate prevention
        self.cache_file = 'responded_cache.json'
        self.cache = self._load_cache()

        # Stats
        self.stats = {
            'comments_processed': 0, 'comments_responded': 0,
            'dms_processed': 0, 'dms_responded': 0,
            'errors': 0, 'start_time': datetime.now().isoformat(),
        }

    # --- cache ---
    def _load_cache(self) -> set:
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file) as f:
                    return set(json.load(f).get('responded', []))
        except Exception:
            pass
        return set()

    def _save_cache(self):
        items = list(self.cache)[-MAX_CACHE_SIZE:]
        with open(self.cache_file, 'w') as f:
            json.dump({'responded': items}, f)

    # --- Graph API calls ---
    def reply_to_comment(self, comment_id: str, message: str) -> bool:
        r = requests.post(f"{GRAPH}/{comment_id}/replies",
                          params={'access_token': self.access_token, 'message': message})
        if r.status_code == 200:
            self.stats['comments_responded'] += 1
            return True
        logger.error(f"Reply failed: {r.text}")
        self.stats['errors'] += 1
        return False

    def send_dm(self, recipient_id: str, message: str) -> bool:
        r = requests.post(f"{GRAPH}/{self.ig_account_id}/messages",
                          json={'access_token': self.access_token,
                                'recipient': {'id': recipient_id},
                                'message': {'text': message}})
        if r.status_code == 200:
            self.stats['dms_responded'] += 1
            return True
        logger.error(f"DM failed: {r.text}")
        self.stats['errors'] += 1
        return False

    # --- event processing ---
    def process_event(self, event: Dict):
        etype = event.get('type')
        eid = event.get('comment_id') or event.get('message_id')

        if eid in self.cache:
            return

        if etype == 'comment':
            self.stats['comments_processed'] += 1
            text = event.get('text', '')
            user = event.get('username', 'friend')

            if not should_respond(text, user, self.own_handle):
                self.cache.add(eid)
                return

            reply = self.ai.generate(text, user, 'comment')
            time.sleep(RESPONSE_DELAY_SECONDS)
            self.reply_to_comment(eid, reply)
            self._log_interaction('comment', event, reply)

        elif etype == 'direct_message':
            self.stats['dms_processed'] += 1
            text = event.get('text', '')
            reply = self.ai.generate(text, '', 'dm')
            time.sleep(RESPONSE_DELAY_SECONDS)
            self.send_dm(event.get('sender_id'), reply)
            self._log_interaction('dm', event, reply)

        self.cache.add(eid)
        self._save_cache()

    def _log_interaction(self, itype: str, data: Dict, response: str):
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': itype,
            'input': data.get('text', ''),
            'username': data.get('username', data.get('sender_id', '')),
            'response': response,
        }
        with open('interaction_log.jsonl', 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def get_stats(self) -> Dict:
        runtime = (datetime.now() - datetime.fromisoformat(self.stats['start_time'])).total_seconds() / 3600
        return {**self.stats, 'runtime_hours': round(runtime, 2), 'cache_size': len(self.cache)}

    # --- queue loop ---
    def run(self, event_queue: queue.Queue):
        """Main processing loop — blocks until interrupted."""
        logger.info("Auto-responder started")
        while True:
            try:
                event = event_queue.get(timeout=5)
                logger.info(f"Processing {event.get('type')} from {event.get('username', 'unknown')}")
                self.process_event(event)
                event_queue.task_done()
            except queue.Empty:
                continue
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Processing error: {e}")
                self.stats['errors'] += 1
                time.sleep(5)
