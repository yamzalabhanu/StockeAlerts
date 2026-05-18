import os
import requests

from telegram_formatting import html_payload

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_MESSAGE_LIMIT = 4096
# Leave headroom for Telegram entity parsing and future alert prefixes while
# still keeping each send comfortably below the hard message length limit.
TELEGRAM_CHUNK_SIZE = 3900


def _split_telegram_message(message: str, limit: int = TELEGRAM_CHUNK_SIZE):
    """Split a Telegram message into chunks that fit the sendMessage limit."""
    text = str(message)
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, limit + 1)
        if split_at <= 0:
            split_at = limit

        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:limit]
            split_at = limit

        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def _post_telegram_message(url: str, message: str) -> bool:
    formatted_payload = html_payload(CHAT_ID, message)
    plain_payload = {"chat_id": CHAT_ID, "text": message}

    response = requests.post(url, data=formatted_payload, timeout=10)
    if response.ok:
        return True

    print(f"Telegram formatted send failed ({response.status_code}): {response.text}")
    fallback_response = requests.post(url, data=plain_payload, timeout=10)
    if fallback_response.ok:
        print("Telegram alert sent without formatting")
        return True

    print(
        "Telegram plain-text send failed "
        f"({fallback_response.status_code}): {fallback_response.text}"
    )
    return False


def send_telegram(message: str):
    if not TOKEN or not CHAT_ID:
        print("Telegram not configured")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    chunks = _split_telegram_message(message)

    try:
        for index, chunk in enumerate(chunks, start=1):
            if not _post_telegram_message(url, chunk):
                if len(chunks) > 1:
                    print(
                        "Telegram chunked send failed "
                        f"({index}/{len(chunks)}); alert not fully delivered"
                    )
                return False

        if len(chunks) > 1:
            print(f"Telegram alert sent in {len(chunks)} chunks")
        return True
    except requests.RequestException as e:
        print("Telegram error:", e)
        return False
