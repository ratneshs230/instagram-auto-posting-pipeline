"""
Pipeline Configuration
======================
Edit these values to customize the pipeline for your project/niche.
"""

# ============================================================
# PROJECT IDENTITY — Change these for each new project
# ============================================================
PROJECT_NAME = "Your Project Name"          # e.g. "World of Cats", "Daily Memes"
CREDENTIALS_FILE = "credentials.txt"        # Your credentials file
EXCEL_FILE = "content_tracker.xlsx"         # Excel file for prompt tracking
EXCEL_SHEET = "Posts"                       # Sheet name in Excel
OUTPUT_FOLDER = "output_images"             # Folder for generated images

# ============================================================
# INSTAGRAM / FACEBOOK GRAPH API
# ============================================================
GRAPH_API_BASE = "https://graph.facebook.com"
GRAPH_API_VERSION = "v21.0"

# ============================================================
# GEMINI AI MODELS
# ============================================================
PRIMARY_TEXT_MODEL = "gemini-2.0-flash-exp"
SECONDARY_TEXT_MODEL = "gemini-2.0-pro-exp"
IMAGE_GEN_MODEL = "gemini-2.5-flash-image-preview"
RESPONDER_MODEL = "gemini-1.5-flash"

# Safety settings (set to BLOCK_NONE for creative content)
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# ============================================================
# WEBHOOK AUTO-RESPONDER SETTINGS
# ============================================================
WEBHOOK_VERIFY_TOKEN = "your_verify_token_2025"  # Shared secret with Facebook
WEBHOOK_PORT = 5000
RESPONSE_DELAY_SECONDS = 3     # Delay between responses to appear human
MAX_CACHE_SIZE = 10000          # Max responded items to track

# ============================================================
# IMAGE UPLOAD SERVICES (fallback order)
# ============================================================
# The pipeline uploads generated images to a temporary hosting service
# so Instagram can fetch them via URL. These are tried in order.
UPLOAD_SERVICES = ["catbox.moe", "tmpfiles.org"]

# ============================================================
# CONTENT GENERATION — CUSTOMIZE FOR YOUR NICHE
# ============================================================

# The JSON schema that Gemini will generate for each post.
# Change the keys to match your content niche.
# Example below is generic — replace with your domain-specific fields.
PROMPT_JSON_SCHEMA = {
    "subject": "The main subject of the image",
    "activity": "What the subject is doing",
    "expression": "Mood or expression",
    "setting": "Background/location",
    "props": "Objects in the scene",
    "camera_style": "Camera angle (close-up, wide, aerial, etc.)",
    "lighting": "Lighting style (golden hour, studio, natural, etc.)",
}

# Caption generation style
CAPTION_STYLE = """You are an AI caption and hashtag generator for the Instagram page {project_name}.
Your role is to craft a fun, engaging caption.

Details:
{details}

Create a caption that:
1. Is 1-3 sentences max, humorous and engaging
2. Highlights the subject's activity or mood
3. Uses playful tone fitting the page's theme
4. Includes 8-15 hashtags — half related to the niche, half trending

Output only the caption and hashtags, ready to copy-paste."""

# Auto-responder personality prompt
RESPONDER_PERSONALITY = """You are managing the Instagram account "{project_name}".
Generate a SHORT, friendly, and engaging response.

RULES:
1. Keep it under 50 words
2. Be warm, friendly, and conversational
3. Use 1-2 emojis naturally
4. If they want pics, politely ask them to DM
5. For collaborations, show enthusiasm and ask them to DM
6. Sound human and genuine"""

# Response templates for common intents
RESPONSE_TEMPLATES = {
    "spam_pic_request": [
        "Hi {username}! Thanks for your interest! Please DM us for exclusive content!",
        "Hey {username}! Drop us a message and we'll share some amazing content!",
    ],
    "collaboration": [
        "Hi {username}! We'd love to collaborate! DM us and let's discuss!",
        "Hey {username}! Collaboration sounds amazing! Send us a DM!",
    ],
    "appreciation": [
        "Thank you so much {username}! Your support means the world to us!",
        "We appreciate you {username}! Thanks for being part of our community!",
    ],
}

# Intent detection keywords — customize for your niche
INTENT_KEYWORDS = {
    "spam_patterns": ["send pic", "pic send", "snd pic", "send me", "dm pic"],
    "collab_keywords": ["collab", "feature", "partnership", "work together", "shoutout", "s4s"],
    "appreciation_keywords": ["love", "amazing", "beautiful", "cute", "adorable", "awesome"],
}
