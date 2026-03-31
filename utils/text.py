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
