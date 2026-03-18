#!/usr/bin/env python3
"""
Instagram Content Generation & Posting Pipeline (Reusable Template)
===================================================================
Generates AI content and posts to Instagram via Facebook Graph API.

Usage:
    python posting_pipeline.py              # Run full pipeline
    python posting_pipeline.py --test       # Generate content without posting
    python posting_pipeline.py --loop 30    # Post every 30 minutes
"""

import os
import sys
import json
import time
import base64
import hashlib
import signal
import random
import argparse
import logging
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path
from PIL import Image
from typing import Dict, Optional, List
import google.generativeai as genai

from config import (
    PROJECT_NAME, CREDENTIALS_FILE, EXCEL_FILE, EXCEL_SHEET, OUTPUT_FOLDER,
    GRAPH_API_BASE, GRAPH_API_VERSION,
    PRIMARY_TEXT_MODEL, SECONDARY_TEXT_MODEL, IMAGE_GEN_MODEL,
    SAFETY_SETTINGS, PROMPT_JSON_SCHEMA, CAPTION_STYLE,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('pipeline.log', mode='a'),
    ],
)
logger = logging.getLogger(__name__)
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

GRAPH = f"{GRAPH_API_BASE}/{GRAPH_API_VERSION}"


# ===================================================================
# CREDENTIALS
# ===================================================================

def load_credentials(filepath: str = CREDENTIALS_FILE) -> Dict:
    """Load KEY=VALUE credentials from a text file."""
    creds: Dict = {}
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line and '=' in line:
                key, value = line.split('=', 1)
                creds[key.strip()] = value.strip()

    # Parse comma-separated Gemini keys
    raw_keys = creds.get('GEMINI_API_KEYS', '')
    creds['_gemini_keys'] = [k.strip() for k in raw_keys.split(',') if k.strip()]

    if not creds['_gemini_keys']:
        raise ValueError("No GEMINI_API_KEYS found in credentials file")

    logger.info(f"Loaded credentials ({len(creds['_gemini_keys'])} Gemini keys)")
    return creds


# ===================================================================
# GEMINI HELPERS (key rotation + model fallback)
# ===================================================================

class GeminiClient:
    """Wrapper around Gemini with API-key rotation and model fallback."""

    def __init__(self, api_keys: List[str]):
        self.api_keys = api_keys
        self.idx = 0
        self._configure()

    def _configure(self):
        genai.configure(api_key=self.api_keys[self.idx])

    def _rotate(self) -> bool:
        if self.idx < len(self.api_keys) - 1:
            self.idx += 1
            self._configure()
            logger.info(f"Rotated to API key {self.idx + 1}/{len(self.api_keys)}")
            return True
        return False

    def _reset(self):
        self.idx = 0
        self._configure()

    # --- text generation with rotation + fallback ---
    def generate_text(self, prompt: str, primary: str = PRIMARY_TEXT_MODEL,
                      secondary: str = SECONDARY_TEXT_MODEL) -> str:
        """Try primary model with all keys, then secondary model with all keys."""
        for model_name in (primary, secondary):
            self._reset()
            for _ in range(len(self.api_keys)):
                try:
                    model = genai.GenerativeModel(model_name)
                    resp = model.generate_content(prompt)
                    logger.info(f"Generated with {model_name} (key {self.idx + 1})")
                    return resp.text
                except Exception as e:
                    logger.warning(f"{model_name} key {self.idx + 1} failed: {e}")
                    if not self._rotate():
                        break
        raise RuntimeError("All models and keys exhausted for text generation")

    # --- image generation via REST (NanoBanana / Gemini 2.5 Flash Image) ---
    def generate_image(self, prompt: str) -> bytes:
        """Generate an image and return raw PNG bytes."""
        for i, key in enumerate(self.api_keys):
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{IMAGE_GEN_MODEL}:generateContent?key={key}")
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            }
            try:
                r = requests.post(url, json=payload, timeout=60)
                if r.status_code == 429:
                    logger.warning(f"Rate limit on key {i + 1}, rotating...")
                    continue
                r.raise_for_status()
                result = r.json()
                for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                    if "inlineData" in part and part["inlineData"].get("mimeType") == "image/png":
                        logger.info(f"Image generated with key {i + 1}")
                        return base64.b64decode(part["inlineData"]["data"])
            except Exception as e:
                logger.warning(f"Image gen key {i + 1} failed: {e}")
                continue

        raise RuntimeError("Image generation failed with all API keys")


# ===================================================================
# IMAGE UPLOAD (temporary hosting for Graph API)
# ===================================================================

def upload_image(image_path: str) -> str:
    """Upload image to temporary hosting and return public URL."""
    # Try catbox.moe first (fastest)
    try:
        with open(image_path, 'rb') as f:
            r = requests.post(
                'https://catbox.moe/user/api.php',
                data={'reqtype': 'fileupload'},
                files={'fileToUpload': f},
                timeout=30,
            )
        if r.status_code == 200 and r.text.strip().startswith('https://'):
            logger.info(f"Uploaded to catbox.moe: {r.text.strip()}")
            return r.text.strip()
    except Exception as e:
        logger.warning(f"catbox.moe failed: {e}")

    # Fallback: tmpfiles.org
    try:
        with open(image_path, 'rb') as f:
            r = requests.post('https://tmpfiles.org/api/v1/upload', files={'file': f}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') == 'success':
                url = data['data']['url'].replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                logger.info(f"Uploaded to tmpfiles.org: {url}")
                return url
    except Exception as e:
        logger.warning(f"tmpfiles.org failed: {e}")

    raise RuntimeError("All image upload services failed")


# ===================================================================
# INSTAGRAM GRAPH API POSTING
# ===================================================================

def get_ig_user_id(credentials: Dict) -> str:
    """Get Instagram Business Account ID."""
    # Prefer stored ID
    stored = credentials.get('Instagram Account ID')
    if stored:
        return stored.strip()

    # Fallback: query Graph API
    access_token = credentials['Access Token']
    r = requests.get(f"{GRAPH}/me/accounts",
                     params={"access_token": access_token,
                             "fields": "id,name,instagram_business_account"})
    r.raise_for_status()
    for page in r.json().get("data", []):
        ig = page.get("instagram_business_account")
        if ig and "id" in ig:
            return ig["id"]
    raise RuntimeError("No Instagram Business/Creator account found")


def post_to_instagram(credentials: Dict, image_path: str, caption: str) -> Optional[str]:
    """Upload image and publish to Instagram. Returns media ID or None."""
    access_token = credentials['Access Token']
    ig_user_id = get_ig_user_id(credentials)

    # Convert to JPEG if needed
    if image_path.lower().endswith('.png'):
        image_path = convert_to_jpeg(image_path)

    # Upload to temp hosting
    image_url = upload_image(image_path)

    # Step 1: Create media container
    r = requests.post(
        f"{GRAPH}/{ig_user_id}/media",
        data={"caption": caption, "image_url": image_url, "access_token": access_token},
        timeout=60,
    )
    if r.status_code != 200:
        error = r.json().get('error', {})
        logger.error(f"Container creation failed: {error.get('message', r.text)}")
        r.raise_for_status()
    creation_id = r.json()["id"]
    logger.info(f"Container created: {creation_id}")

    # Step 2: Wait for processing
    time.sleep(5)

    # Step 3: Publish
    r = requests.post(
        f"{GRAPH}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=60,
    )
    if r.status_code != 200:
        error = r.json().get('error', {})
        logger.error(f"Publishing failed: {error.get('message', r.text)}")
        r.raise_for_status()

    media_id = r.json()["id"]
    logger.info(f"Published! Media ID: {media_id}")
    return media_id


# ===================================================================
# IMAGE PROCESSING
# ===================================================================

def convert_to_jpeg(png_path: str) -> str:
    """Convert PNG to Instagram-compatible JPEG."""
    img = Image.open(png_path)
    if img.mode in ('RGBA', 'LA', 'P'):
        bg = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = bg
    else:
        img = img.convert('RGB')

    jpg_path = png_path.rsplit('.', 1)[0] + '.jpg'
    img.save(jpg_path, 'JPEG', quality=95)
    os.remove(png_path)
    return jpg_path


def save_image(image_bytes: bytes, model_tag: str = "gen") -> str:
    """Save raw image bytes to output folder and convert to JPEG."""
    Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    png_path = os.path.join(OUTPUT_FOLDER, f"{model_tag}_{ts}.png")
    with open(png_path, 'wb') as f:
        f.write(image_bytes)
    return convert_to_jpeg(png_path)


# ===================================================================
# EXCEL TRACKING
# ===================================================================

def load_excel(filepath: str = EXCEL_FILE) -> pd.DataFrame:
    """Load tracking spreadsheet."""
    try:
        return pd.read_excel(filepath, sheet_name=EXCEL_SHEET)
    except FileNotFoundError:
        logger.info(f"Creating new tracking file: {filepath}")
        df = pd.DataFrame(columns=[
            'Post ID', 'Prompt to the model', 'JSON_Image_Generation',
            'Image generation status', 'Image Path', 'Caption',
            'Publish Status', 'Media ID', 'Timestamp',
        ])
        df.to_excel(filepath, sheet_name=EXCEL_SHEET, index=False)
        return df


def get_existing_prompts(df: pd.DataFrame) -> str:
    """Get previously used prompts to avoid duplicates."""
    if 'JSON_Image_Generation' in df.columns:
        prompts = df['JSON_Image_Generation'].dropna().tolist()
        return "\n".join(str(p) for p in prompts)
    return ""


def update_excel(df: pd.DataFrame, post_data: Dict, filepath: str = EXCEL_FILE):
    """Append a new row to the tracking spreadsheet."""
    new_row = pd.DataFrame([{
        'Post ID': post_data.get('prompt_id', ''),
        'Prompt to the model': post_data.get('prompt_template', ''),
        'JSON_Image_Generation': post_data.get('prompt_text', ''),
        'Image generation status': 'completed',
        'Image Path': post_data.get('image_path', ''),
        'Caption': post_data.get('caption', ''),
        'Publish Status': 'published' if post_data.get('media_id') else 'failed',
        'Media ID': post_data.get('media_id', ''),
        'Timestamp': datetime.now().isoformat(),
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    with pd.ExcelWriter(filepath, mode='a', if_sheet_exists='replace') as w:
        df.to_excel(w, sheet_name=EXCEL_SHEET, index=False)
    logger.info("Excel updated")
    return df


# ===================================================================
# MAIN PIPELINE
# ===================================================================

def run_pipeline(credentials: Dict, gemini: GeminiClient, prompt_template: str,
                 df: pd.DataFrame, test_mode: bool = False) -> pd.DataFrame:
    """
    Full pipeline: generate prompt -> generate image -> generate caption -> post.
    """
    logger.info("=" * 50)
    logger.info(f"Starting {PROJECT_NAME} Content Pipeline")
    logger.info("=" * 50)

    # --- Step 1: Generate unique prompt ---
    logger.info("[Step 1/4] Generating content prompt...")
    existing = get_existing_prompts(df)
    full_prompt = f"{prompt_template}\n\nAlready generated (avoid duplicates):\n{existing}"
    raw = gemini.generate_text(full_prompt)

    # Clean markdown fences
    raw = raw.strip()
    if raw.startswith('```json'):
        raw = raw[7:]
    if raw.endswith('```'):
        raw = raw[:-3]
    prompt_json = json.loads(raw.strip())
    prompt_id = hashlib.md5(raw.encode()).hexdigest()[:24]
    logger.info(f"Prompt generated: {json.dumps(prompt_json, indent=2)[:200]}")

    # --- Step 2: Generate image ---
    logger.info("[Step 2/4] Generating image...")
    parts = []
    for key, desc in PROMPT_JSON_SCHEMA.items():
        if key in prompt_json:
            parts.append(f"{key.replace('_', ' ').title()}: {prompt_json[key]}")
    image_prompt = ". ".join(parts) + ". Photorealistic, high quality, Instagram ready."
    image_bytes = gemini.generate_image(image_prompt)
    image_path = save_image(image_bytes)
    logger.info(f"Image saved: {image_path}")

    # --- Step 3: Generate caption ---
    logger.info("[Step 3/4] Generating caption...")
    details = "\n".join(f"- {k}: {v}" for k, v in prompt_json.items())
    caption_prompt = CAPTION_STYLE.format(project_name=PROJECT_NAME, details=details)
    caption = gemini.generate_text(caption_prompt).strip()
    logger.info(f"Caption: {caption[:100]}...")

    # --- Step 4: Post to Instagram ---
    media_id = None
    if not test_mode:
        logger.info("[Step 4/4] Posting to Instagram...")
        media_id = post_to_instagram(credentials, image_path, caption)
    else:
        logger.info("[Step 4/4] SKIPPED (test mode)")

    # --- Update tracking ---
    post_data = {
        'prompt_id': prompt_id,
        'prompt_template': prompt_template,
        'prompt_text': raw.strip(),
        'image_path': image_path,
        'caption': caption,
        'media_id': media_id,
    }
    df = update_excel(df, post_data)

    status = "POSTED" if media_id else "TEST"
    logger.info(f"Pipeline complete [{status}]")
    return df


# ===================================================================
# ENTRY POINT
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description=f"{PROJECT_NAME} Instagram Pipeline")
    parser.add_argument('--test', action='store_true', help='Generate without posting')
    parser.add_argument('--loop', type=int, default=0,
                        help='Run every N minutes (0 = run once)')
    args = parser.parse_args()

    # Load everything
    credentials = load_credentials()
    gemini = GeminiClient(credentials['_gemini_keys'])
    df = load_excel()

    # Get prompt template from first row of Excel
    if len(df) > 0 and 'Prompt to the model' in df.columns and pd.notna(df.iloc[0].get('Prompt to the model')):
        prompt_template = df.iloc[0]['Prompt to the model']
    else:
        logger.error("No prompt template found in Excel. Add one to the first row "
                      "of the 'Prompt to the model' column.")
        sys.exit(1)

    # Graceful shutdown
    stop = [False]

    def on_signal(sig, frame):
        logger.info("Shutdown signal received...")
        stop[0] = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    # Run
    if args.loop > 0:
        logger.info(f"Running every {args.loop} minutes. Ctrl+C to stop.")
        while not stop[0]:
            try:
                df = run_pipeline(credentials, gemini, prompt_template, df, args.test)
            except Exception as e:
                logger.error(f"Pipeline error: {e}", exc_info=True)
            if not stop[0]:
                logger.info(f"Sleeping {args.loop} minutes...")
                for _ in range(args.loop * 60):
                    if stop[0]:
                        break
                    time.sleep(1)
    else:
        run_pipeline(credentials, gemini, prompt_template, df, args.test)


if __name__ == "__main__":
    main()
