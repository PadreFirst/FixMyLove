import re
from utils.constants import CRISIS_KEYWORDS, DIARY_KEYWORDS, ADMIN_KEYWORDS, DIARY_SHOW_KEYWORDS


def clean_markdown(text: str) -> str:
    """Strip Markdown formatting that Telegram renders as raw characters."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    return text.strip()


def has_crisis_markers(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in CRISIS_KEYWORDS)


def is_diary_command(text: str) -> bool:
    lower = text.lower().strip()
    return any(kw in lower for kw in DIARY_KEYWORDS)


def is_diary_show_command(text: str) -> bool:
    lower = text.lower().strip()
    if lower.startswith("/diary show"):
        return True
    return any(kw in lower for kw in DIARY_SHOW_KEYWORDS)


def parse_diary_show_count(text: str) -> int:
    match = re.search(r"/diary\s+show\s+(\d+)", text.lower())
    if match:
        return min(int(match.group(1)), 50)
    return 10


def is_admin_command(text: str) -> bool:
    lower = text.lower().strip()
    if lower.startswith("/"):
        return any(kw in lower for kw in ADMIN_KEYWORDS)
    if len(lower) > 120:
        return False
    return any(kw in lower for kw in ADMIN_KEYWORDS)


def is_delete_data_command(text: str) -> bool:
    return text.strip().lower().startswith("/delete_data")


def count_sentences(text: str) -> int:
    sentences = re.split(r"[.!?]+", text.strip())
    return len([s for s in sentences if s.strip()])


def truncate_to_sentences(text: str, max_sentences: int) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) <= max_sentences:
        return text
    return " ".join(sentences[:max_sentences])


def soften_capslock(text: str) -> str:
    """Replace any run of 4+ UPPERCASE letters (Cyrillic or Latin) with lowercase.

    Telegram users perceive CAPSLOCK as shouting. Leaves short abbreviations
    (up to 3 letters) untouched.
    """
    if not text:
        return text

    def _repl(match):
        chunk = match.group(0)
        return chunk.lower()

    # Match runs of 4+ uppercase letters (allow spaces/punctuation inside phrase)
    return re.sub(r"[А-ЯA-Z]{4,}", _repl, text)


def split_long_message(text: str, max_len: int = 700) -> list[str]:
    """Split a long message into 1-3 chunks for Telegram readability.

    Prefers splitting on blank lines, falls back to sentence boundaries.
    Never produces more than 3 chunks — truncates if somehow bigger.
    """
    if not text:
        return []
    text = text.strip()
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining and len(chunks) < 2:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            remaining = ""
            break

        # prefer paragraph break near the middle of the allowed window
        target = max_len
        window = remaining[: int(max_len * 1.3)]
        split_at = window.rfind("\n\n", 0, target + 1)
        if split_at == -1 or split_at < max_len // 2:
            split_at = window.rfind("\n", 0, target + 1)
        if split_at == -1 or split_at < max_len // 2:
            # fall back to last sentence boundary within max_len
            m = list(re.finditer(r"[.!?]\s+", window[:target]))
            if m:
                split_at = m[-1].end()
            else:
                split_at = target

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    return [c for c in chunks if c]
