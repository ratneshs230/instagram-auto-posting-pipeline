# Instagram/Facebook Automated Posting Pipeline — Setup Guide

## Quick Start

```bash
# 1. Clone/copy this template into your new project folder
# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and fill in credentials
cp credentials.example.txt credentials.txt
# Edit credentials.txt with your values (see Section A below)

# 5. Edit config.py for your niche (see Section B below)

# 6. Create Excel with prompt template (see Section C below)

# 7. Run
python posting_pipeline.py --test     # Test without posting
python posting_pipeline.py            # Post once
python posting_pipeline.py --loop 30  # Post every 30 minutes
```

---

## Section A: Facebook/Instagram API Credentials

### Step 1 — Create a Facebook App

1. Go to **https://developers.facebook.com**
2. Click **My Apps** → **Create App**
3. Select **Business** type → Next
4. Enter App name and contact email → **Create App**
5. Note down your **App ID** and **App Secret** (Settings → Basic)

### Step 2 — Set Up Instagram Business Account

1. Open Instagram → Settings → Account → Switch to **Professional Account** → Choose **Business**
2. Connect your Instagram account to a **Facebook Page**:
   - Instagram Settings → Account → Linked Accounts → Facebook
   - Select or create a Facebook Page

### Step 3 — Add Instagram Graph API to Your App

1. In Facebook Developer Dashboard → your app
2. Click **Add Product** → find **Instagram Graph API** → **Set Up**
3. Go to **App Settings → Advanced** → set **App Type** to **Business**

### Step 4 — Generate Access Token

**Option A: Graph API Explorer (quick, short-lived)**
1. Go to **https://developers.facebook.com/tools/explorer/**
2. Select your App from the dropdown
3. Click **Generate Access Token**
4. Select these permissions:
   - `instagram_basic`
   - `instagram_content_publish`
   - `instagram_manage_comments`
   - `instagram_manage_messages`
   - `pages_manage_engagement`
   - `pages_show_list`
   - `pages_read_engagement`
5. Click **Generate Access Token** → approve the prompts
6. This gives you a **short-lived token** (valid ~1 hour)

**Option B: Convert to Long-Lived Token (recommended)**

```bash
# Replace the placeholders:
curl -X GET "https://graph.facebook.com/v21.0/oauth/access_token?\
grant_type=fb_exchange_token&\
client_id=YOUR_APP_ID&\
client_secret=YOUR_APP_SECRET&\
fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"
```

This returns a **long-lived token** valid for ~60 days. Save it in `credentials.txt`.

**Option C: Get a Permanent Page Token (never expires)**

```bash
# 1. Get long-lived user token (Option B above)
# 2. Get page tokens:
curl -X GET "https://graph.facebook.com/v21.0/me/accounts?\
access_token=YOUR_LONG_LIVED_USER_TOKEN"

# 3. The page token returned here is permanent (never expires)
# Use it as your Access Token
```

### Step 5 — Get Your Instagram Account ID

```bash
# Using Graph API Explorer or curl:
curl -X GET "https://graph.facebook.com/v21.0/me/accounts?\
fields=instagram_business_account&\
access_token=YOUR_ACCESS_TOKEN"
```

The response will include your numeric Instagram Business Account ID (e.g., `17841477292366911`).

### Step 6 — Fill In credentials.txt

```
Instagram App ID=123456789
Instagram App Secret=abc123def456
Gmail=you@gmail.com
Instagram Handle=your_handle
Instagram Password=your_password
Access Token=EAAxxxxxxx...
Instagram Account ID=17841477292366911
GEMINI_API_KEYS=AIzaSy...,AIzaSy...,AIzaSy...
```

### Step 7 — Get Gemini API Keys

1. Go to **https://aistudio.google.com/app/apikey**
2. Click **Create API Key** → select a Google Cloud project
3. Copy the key
4. Repeat to create multiple keys (recommended: 5-10 minimum for rotation)
5. Add all keys comma-separated to `GEMINI_API_KEYS` in credentials.txt

---

## Section B: Customize config.py for Your Niche

Open `config.py` and update:

### 1. Project Identity
```python
PROJECT_NAME = "World of Cats"   # Your page name
```

### 2. Prompt JSON Schema
Define the fields that describe your content:
```python
PROMPT_JSON_SCHEMA = {
    "cat_breed": "Specific breed of cat",
    "activity": "What the cat is doing",
    "expression": "Facial expression or mood",
    "setting": "Where the scene takes place",
    "props": "Items or accessories in the scene",
    "camera_style": "Camera angle",
    "lighting": "Lighting style",
}
```

### 3. Caption Style
Customize the caption prompt for your brand voice.

### 4. Response Templates
Edit templates for how the auto-responder handles spam, collaboration requests, and appreciation.

### 5. Intent Keywords
Customize the keyword lists for detecting comment intents specific to your niche.

---

## Section C: Set Up Excel Tracking File

Create `content_tracker.xlsx` with a sheet named `Posts` containing these columns:

| Column | Purpose |
|--------|---------|
| `Prompt to the model` | Your master prompt template (Row 1 only) |
| `JSON_Image_Generation` | Stores generated prompts (auto-filled) |
| `Post ID` | Unique ID (auto-filled) |
| `Image generation status` | Status (auto-filled) |
| `Image Path` | Local path to image (auto-filled) |
| `Caption` | Generated caption (auto-filled) |
| `Publish Status` | published/failed (auto-filled) |
| `Media ID` | Instagram media ID (auto-filled) |
| `Timestamp` | When posted (auto-filled) |

**Row 1, "Prompt to the model"** should contain your master prompt. Example:

```
Generate a unique JSON object describing a cat image for Instagram.
Return ONLY valid JSON with these keys:
- cat_breed: a specific cat breed
- activity: what the cat is doing
- expression: the cat's expression
- setting: the background/location
- props: any objects in the scene
- camera_style: the camera angle
- lighting: the lighting style

Make it creative, unique, and visually interesting.
Do NOT repeat any of the prompts listed below.
```

The pipeline will auto-create this file on first run if it doesn't exist.

---

## Section D: Webhook Auto-Responder Setup (Optional)

Only needed if you want automatic comment/DM replies.

### 1. Install ngrok

```bash
# Download from https://ngrok.com/download
# Or on Linux:
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok-v3-stable-linux-amd64.tgz | tar xz
./ngrok authtoken YOUR_NGROK_AUTH_TOKEN
```

### 2. Start the System

```bash
# Terminal 1: Start ngrok tunnel
ngrok http 5000

# Terminal 2: Start the orchestrator
python orchestrator.py
```

### 3. Configure Webhook in Facebook App

1. Copy the ngrok HTTPS URL (e.g., `https://abc123.ngrok.io`)
2. Go to Facebook Developer Dashboard → your app → Webhooks
3. Click **Add Subscription** → **Instagram**
4. **Callback URL**: `https://abc123.ngrok.io/webhook`
5. **Verify Token**: must match `WEBHOOK_VERIFY_TOKEN` in config.py
6. Subscribe to: `comments`, `mentions`, `messages`

### 4. Test

```bash
python orchestrator.py --test
```

---

## File Structure

```
your_project/
├── config.py                  # All configuration in one place
├── credentials.txt            # API keys & secrets (DO NOT commit)
├── credentials.example.txt    # Template for credentials
├── requirements.txt           # Python dependencies
├── content_tracker.xlsx       # Prompt tracking & post history
│
├── posting_pipeline.py        # Main: generate content & post
├── webhook_server.py          # Flask webhook listener
├── auto_responder.py          # AI response generation & posting
├── orchestrator.py            # Starts webhook + responder
│
├── output_images/             # Generated images
├── pipeline.log               # Pipeline logs
├── webhook_server.log         # Webhook logs
├── auto_responder.log         # Responder logs
├── orchestrator.log           # Orchestrator logs
├── interaction_log.jsonl      # All interactions (audit)
├── responded_cache.json       # Duplicate prevention
├── system_status.json         # Live health status
└── final_stats.json           # Stats on shutdown
```

---

## Common Issues

| Problem | Solution |
|---------|----------|
| `OAuthException: Invalid access token` | Token expired — regenerate (see Step 4) |
| `Application does not have permission` | Missing permissions — re-authorize with all scopes |
| `instagram_content_publish not granted` | App needs App Review for this permission (submit in Developer Dashboard) |
| `Invalid image URL` | Temp hosting service blocked — pipeline will auto-fallback |
| `Gemini quota exceeded` | All API keys exhausted — add more keys or wait |
| `No Instagram Business account found` | Ensure IG is Business/Creator type and linked to a Facebook Page |
| Container stuck at `IN_PROGRESS` | Image too large or hosting URL expired — retry |

---

## Important Notes

- **Access Token Refresh**: Long-lived tokens expire in ~60 days. Set a reminder to refresh.
  Permanent page tokens (Option C) don't expire.
- **App Review**: For production use, submit your app for review to get `instagram_content_publish`
  and `instagram_manage_comments` approved. During development, you can test with your own accounts.
- **Rate Limits**: Instagram allows ~25 posts per 24-hour period per account.
- **Gemini Keys**: More keys = better resilience. The pipeline rotates through all keys on quota errors.
- **Never commit credentials.txt** — add it to `.gitignore`.
