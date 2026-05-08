import os
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message: str):
    if not TOKEN or not CHAT_ID:
        print("Telegram not configured")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    markdown_payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    plain_payload = {"chat_id": CHAT_ID, "text": message}

    try:
        response = requests.post(url, data=markdown_payload, timeout=10)
        if response.ok:
            return True

        print(f"Telegram Markdown send failed ({response.status_code}): {response.text}")
        fallback_response = requests.post(url, data=plain_payload, timeout=10)
        if fallback_response.ok:
            print("Telegram alert sent without Markdown formatting")
            return True

        print(
            "Telegram plain-text send failed "
            f"({fallback_response.status_code}): {fallback_response.text}"
        )
        return False
    except requests.RequestException as e:
        print("Telegram error:", e)
        return False
