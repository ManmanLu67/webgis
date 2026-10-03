"""插件目录内的小工具。目录核心不引用这里。"""

from datetime import UTC, datetime


def require_explicit_fetch(filters) -> bool:
    return bool(filters and filters.get("fetch"))


def parse_time(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
