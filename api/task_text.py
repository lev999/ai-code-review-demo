"""Text helpers for the task-board API."""


def normalize_title(value: str) -> str:
    """Return a task title without leading or trailing whitespace."""
    return value.strip()
