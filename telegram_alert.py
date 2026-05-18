import os
import requests

from telegram_formatting import html_payload, telegram_html_from_markdown

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_MESSAGE_LIMIT = 4096
# Leave headroom for Telegram entity parsing and future alert prefixes while
# still keeping each send comfortably below the hard message length limit.
TELEGRAM_CHUNK_SIZE = 3900


def _fits_telegram_chunk(message: str, limit: int) -> bool:
    """Return True when both raw and formatted payload text fit Telegram."""
    return (
        len(message) <= limit
        and len(telegram_html_from_markdown(message)) <= limit
    )


def _max_fitting_prefix_length(message: str, limit: int) -> int:
    """Find the longest prefix whose raw and HTML-rendered text fit the limit."""
    low = 0
    high = min(len(message), limit)
    while low < high:
        mid = (low + high + 1) // 2
        if _fits_telegram_chunk(message[:mid], limit):
            low = mid
        else:
            high = mid - 1
    return max(1, low)


def _split_telegram_message(message: str, limit: int = TELEGRAM_CHUNK_SIZE):
    """Split a Telegram message into chunks that fit the sendMessage limit.

    Telegram validates the final payload text after HTML escaping, so splitting
    only by the original Markdown-like alert can still produce an oversized
    formatted message when dynamic text contains many characters such as `&` or
    `<`.  Keep each chunk below the safety limit in both representations.
    """
    text = str(message)
    if _fits_telegram_chunk(text, limit):
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if _fits_telegram_chunk(remaining, limit):
            chunks.append(remaining)
            break

        max_prefix = _max_fitting_prefix_length(remaining, limit)
        split_at = remaining.rfind("\n", 0, max_prefix + 1)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, max_prefix + 1)
        if split_at <= 0:
            split_at = max_prefix

        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:max_prefix]
            split_at = max_prefix

        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    return chunks


def _post_telegram_message(url: str, chat_id: str, message: str) -> bool:
    formatted_payload = html_payload(chat_id, message)
    plain_payload = {"chat_id": chat_id, "text": message}

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


def send_telegram_message(message: str, token: str, chat_id: str):
    """Send a Telegram message, chunking long alerts before API delivery."""
    if not token or not chat_id:
        print("Telegram not configured")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = _split_telegram_message(message)

    try:
        for index, chunk in enumerate(chunks, start=1):
            if not _post_telegram_message(url, chat_id, chunk):
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


def send_telegram(message: str):
    return send_telegram_message(message, TOKEN, CHAT_ID)
