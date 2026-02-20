"""Utility to discover Telegram group chat IDs.

Run this script, then send a message in each Telegram group where the bot
has been added. The script prints the chat ID for each group it sees.
Add those IDs to TELEGRAM_GROUP_IDS in your .env file.

Usage:
    python get_chat_ids.py
"""

import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN not set in .env")
    sys.exit(1)

API = f"https://api.telegram.org/bot{TOKEN}"
seen: set[int] = set()


def poll():
    offset = 0
    print("Listening for messages… Send a message in each Telegram group.")
    print("Press Ctrl+C to stop.\n")
    while True:
        try:
            resp = httpx.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            data = resp.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or update.get("channel_post")
                if not msg:
                    continue
                chat = msg["chat"]
                chat_id = chat["id"]
                if chat_id not in seen:
                    seen.add(chat_id)
                    title = chat.get("title", chat.get("username", "DM"))
                    print(f"  Chat ID: {chat_id}  →  {title}")
        except httpx.TimeoutException:
            continue
        except KeyboardInterrupt:
            break

    if seen:
        ids = ",".join(str(cid) for cid in sorted(seen))
        print(f"\nTELEGRAM_GROUP_IDS={ids}")
    print("Done.")


if __name__ == "__main__":
    poll()
