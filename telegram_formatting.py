import html
import re

_BOLD_RE = re.compile(r"\*([^*\n]+)\*")


def telegram_html_from_markdown(message: str) -> str:
    """Convert the bot's simple Markdown-style bold labels to safe Telegram HTML.

    Telegram's legacy Markdown parser treats characters such as underscores in
    tickers, setup keys, model text, and URLs as formatting delimiters. Escaping
    the full message as HTML first keeps dynamic alert content literal, while the
    small bold conversion preserves the bot's existing alert emphasis.
    """
    escaped = html.escape(str(message), quote=False)
    return _BOLD_RE.sub(r"<b>\1</b>", escaped)


def html_payload(chat_id: str, message: str) -> dict:
    return {
        "chat_id": chat_id,
        "text": telegram_html_from_markdown(message),
        "parse_mode": "HTML",
    }
