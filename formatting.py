"""Convert Slack messages to Telegram HTML.

Handles both plain mrkdwn text and Block Kit rich_text blocks.
"""

import html
import re


# ---------------------------------------------------------------------------
# Block Kit rich_text → Telegram HTML
# ---------------------------------------------------------------------------

EMOJI_MAP = {
    "loudspeaker": "\U0001F4E2",
    "mega": "\U0001F4E3",
    "warning": "\u26A0\uFE0F",
    "rocket": "\U0001F680",
    "white_check_mark": "\u2705",
    "x": "\u274C",
    "point_right": "\U0001F449",
    "bulb": "\U0001F4A1",
    "link": "\U0001F517",
    "star": "\u2B50",
    "fire": "\U0001F525",
    "tada": "\U0001F389",
    "eyes": "\U0001F440",
    "heavy_check_mark": "\u2714\uFE0F",
}


def _render_element(el: dict) -> str:
    """Render a single rich_text element to Telegram HTML."""
    t = el.get("type")

    if t == "text":
        text = html.escape(el.get("text", ""), quote=False)
        style = el.get("style", {})
        if style.get("code"):
            return f"<code>{text}</code>"
        if style.get("bold"):
            text = f"<b>{text}</b>"
        if style.get("italic"):
            text = f"<i>{text}</i>"
        if style.get("strike"):
            text = f"<s>{text}</s>"
        return text

    if t == "link":
        url = el.get("url", "")
        label = html.escape(el.get("text", url), quote=False)
        style = el.get("style", {})
        link = f'<a href="{url}">{label}</a>'
        if style.get("bold"):
            link = f"<b>{link}</b>"
        if style.get("italic"):
            link = f"<i>{link}</i>"
        return link

    if t == "emoji":
        name = el.get("name", "")
        return EMOJI_MAP.get(name, f":{name}:")

    if t == "user":
        return f"@{el.get('user_id', 'user')}"

    if t == "channel":
        return f"#{el.get('channel_id', 'channel')}"

    return html.escape(el.get("text", ""), quote=False)


def _render_section(section: dict) -> str:
    """Render a rich_text block element (section, list, quote, preformatted)."""
    t = section.get("type")

    if t == "rich_text_section":
        raw = "".join(_render_element(el) for el in section.get("elements", []))
        # Clean up trailing spaces on each line (Slack pads with " " elements)
        lines = [line.rstrip() for line in raw.split("\n")]
        return "\n".join(lines)

    if t == "rich_text_list":
        style = section.get("style", "bullet")
        items = []
        for i, item in enumerate(section.get("elements", []), 1):
            content = _render_section(item).strip()
            if style == "ordered":
                items.append(f"{i}. {content}")
            else:
                items.append(f"\u2022 {content}")
        return "\n\n".join(items)

    if t == "rich_text_quote":
        inner = "".join(_render_element(el) for el in section.get("elements", []))
        lines = inner.split("\n")
        return "\n".join(f"\u275D {line}" for line in lines)

    if t == "rich_text_preformatted":
        inner = "".join(
            html.escape(el.get("text", ""), quote=False)
            for el in section.get("elements", [])
        )
        return f"<pre>{inner}</pre>"

    return ""


def blocks_to_telegram_html(blocks: list[dict]) -> str:
    """Convert Slack Block Kit blocks to Telegram HTML."""
    parts: list[str] = []

    for block in blocks:
        btype = block.get("type")

        if btype == "header":
            text = block.get("text", {}).get("text", "")
            # Convert :emoji: shortcodes in headers
            text = _replace_emoji_shortcodes(text)
            parts.append(f"<b>{html.escape(text, quote=False)}</b>")

        elif btype == "rich_text":
            sections = []
            for section in block.get("elements", []):
                rendered = _render_section(section).strip()
                if rendered:
                    sections.append(rendered)
            parts.append("\n\n".join(sections))

        elif btype == "section":
            text = block.get("text", {}).get("text", "")
            if text:
                parts.append(slack_mrkdwn_to_telegram_html(text))

        elif btype == "divider":
            parts.append("\u2500" * 20)

        # Skip context blocks (Thena branding etc.)

    result = "\n\n".join(p for p in parts if p.strip())
    # Collapse runs of 3+ newlines into 2 (one blank line max)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _replace_emoji_shortcodes(text: str) -> str:
    """Replace :emoji_name: shortcodes with unicode equivalents."""
    def _repl(m: re.Match) -> str:
        name = m.group(1)
        return EMOJI_MAP.get(name, m.group(0))
    return re.sub(r":([a-z0-9_]+):", _repl, text)


# ---------------------------------------------------------------------------
# Plain mrkdwn → Telegram HTML (fallback for non-block messages)
# ---------------------------------------------------------------------------

def slack_mrkdwn_to_telegram_html(text: str) -> str:
    """Convert Slack mrkdwn formatted text to Telegram-compatible HTML."""
    text = html.unescape(text)
    text = html.escape(text, quote=False)

    # Code blocks (``` ... ```) — must come before inline code
    text = re.sub(
        r"```\n?(.*?)```",
        lambda m: f"<pre>{m.group(1)}</pre>",
        text,
        flags=re.DOTALL,
    )

    # Inline code (`...`)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Bold (*...*)
    text = re.sub(r"(?<![\\*\w])\*(.+?)\*(?![\\*\w])", r"<b>\1</b>", text)

    # Italic (_..._)
    text = re.sub(r"(?<![\\\_\w])_(.+?)_(?![\\\_\w])", r"<i>\1</i>", text)

    # Strikethrough (~...~)
    text = re.sub(r"(?<![\\\~\w])~(.+?)~(?![\\\~\w])", r"<s>\1</s>", text)

    # Slack links: <url|label> → <a href="url">label</a>
    def _convert_link(m: re.Match) -> str:
        content = m.group(1)
        if "|" in content:
            url, label = content.split("|", 1)
            return f'<a href="{url}">{label}</a>'
        return f'<a href="{content}">{content}</a>'

    text = text.replace("&lt;", "\x00").replace("&gt;", "\x01")
    text = re.sub(r"\x00((?:https?://|mailto:)[^\x01]+)\x01", _convert_link, text)
    text = re.sub(r"\x00@([A-Z0-9]+)\x01", r"@\1", text)
    text = re.sub(r"\x00#([A-Z0-9]+)\|([^\x01]+)\x01", r"#\2", text)
    text = re.sub(r"\x00#([A-Z0-9]+)\x01", r"#\1", text)
    text = text.replace("\x00", "&lt;").replace("\x01", "&gt;")

    # Blockquotes
    text = re.sub(r"(?m)^&gt;\s?(.*)$", r"\1", text)

    return text.strip()
