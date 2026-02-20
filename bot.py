"""Slack → Telegram broadcast forwarder.

Listens for messages in a single Slack channel (via Socket Mode) and
forwards them to all configured Telegram groups.
"""

import logging
import os
import sys

import httpx
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from formatting import blocks_to_telegram_html, slack_mrkdwn_to_telegram_html

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_GROUP_IDS = [
    s.strip()
    for s in os.getenv("TELEGRAM_GROUP_IDS", "").split(",")
    if s.strip()
]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TELEGRAM_MAX_LENGTH = 4096

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validate config
# ---------------------------------------------------------------------------
_missing = []
if not SLACK_BOT_TOKEN:
    _missing.append("SLACK_BOT_TOKEN")
if not SLACK_APP_TOKEN:
    _missing.append("SLACK_APP_TOKEN")
if not SLACK_CHANNEL_ID:
    _missing.append("SLACK_CHANNEL_ID")
if not TELEGRAM_BOT_TOKEN:
    _missing.append("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_GROUP_IDS:
    _missing.append("TELEGRAM_GROUP_IDS")
if _missing:
    log.error("Missing required config: %s — check your .env file", ", ".join(_missing))
    sys.exit(1)

# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------
http = httpx.Client(timeout=15)


def split_message(text: str) -> list[str]:
    """Split text into chunks that fit Telegram's 4096-char limit.

    Splits at paragraph boundaries (double newline) when possible,
    falling back to single newlines, then hard-cutting as a last resort.
    """
    if len(text) <= TELEGRAM_MAX_LENGTH:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= TELEGRAM_MAX_LENGTH:
            chunks.append(text)
            break

        # Try to split at a paragraph boundary
        cut = text.rfind("\n\n", 0, TELEGRAM_MAX_LENGTH)
        if cut == -1:
            cut = text.rfind("\n", 0, TELEGRAM_MAX_LENGTH)
        if cut == -1:
            cut = TELEGRAM_MAX_LENGTH

        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")

    return chunks


def send_telegram_html(chat_id: str, html_text: str):
    """Send pre-formatted HTML to a Telegram chat, splitting if too long."""
    chunks = split_message(html_text)

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = http.post(f"{TELEGRAM_API}/sendMessage", json=payload)

        if not resp.json().get("ok"):
            # Fall back to plain text if HTML parsing failed
            log.warning(
                "HTML send failed for chat %s, retrying as plain text: %s",
                chat_id,
                resp.text,
            )
            fallback = {
                "chat_id": chat_id,
                "text": chunk,
            }
            http.post(f"{TELEGRAM_API}/sendMessage", json=fallback)


def extract_message_html(event: dict) -> str:
    """Extract Telegram HTML from a Slack event.

    Prefers Block Kit blocks (used by Thena campaigns) over plain text.
    """
    blocks = event.get("blocks")
    if blocks:
        html_text = blocks_to_telegram_html(blocks)
        if html_text.strip():
            return html_text

    # Fallback to plain text field
    text = event.get("text", "")
    if text:
        return slack_mrkdwn_to_telegram_html(text)

    return ""


# ---------------------------------------------------------------------------
# Slack app
# ---------------------------------------------------------------------------
app = App(token=SLACK_BOT_TOKEN)


@app.event("message")
def handle_message(event: dict, say):
    # Only process messages from the target channel
    if event.get("channel") != SLACK_CHANNEL_ID:
        return

    # Only forward Thena campaign messages
    metadata = event.get("metadata", {})
    event_type = metadata.get("event_type", "")
    if not event_type.startswith("MARKETING_CAMPAIGN"):
        log.info(
            "Skipping non-campaign message (event_type=%s, ts=%s)",
            event_type or "none",
            event.get("ts"),
        )
        return

    html_text = extract_message_html(event)
    if not html_text:
        log.info("Skipping message with no content (ts=%s)", event.get("ts"))
        return

    log.info("Forwarding message to %d Telegram group(s)", len(TELEGRAM_GROUP_IDS))

    for chat_id in TELEGRAM_GROUP_IDS:
        try:
            send_telegram_html(chat_id, html_text)
            log.info("  ✓ Sent to %s", chat_id)
        except Exception:
            log.exception("  ✗ Failed to send to %s", chat_id)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("Starting Slack → Telegram forwarder…")
    log.info("Monitoring channel: %s", SLACK_CHANNEL_ID)
    log.info("Forwarding to %d Telegram group(s): %s", len(TELEGRAM_GROUP_IDS), TELEGRAM_GROUP_IDS)
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
