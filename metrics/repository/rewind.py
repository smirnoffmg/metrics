"""Raw Jira issues as they stood at an earlier moment, rebuilt from changelogs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .converter import parse_timestamp

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime


def _status(item: dict) -> dict | None:
    return {"id": item["from"], "name": item["fromString"]}


def _named(key: str) -> Callable[[dict], dict | None]:
    def value(item: dict) -> dict | None:
        return {key: item["fromString"]} if item["fromString"] else None

    return value


_REWOUND_FIELDS: dict[str, Callable[[dict], dict | None]] = {
    "status": _status,
    "resolution": _named("name"),
    "assignee": _named("displayName"),
}


def rewind_issue(raw: dict, at: datetime) -> dict | None:
    """Return the issue as Jira showed it at a moment; None if not created yet.

    History after the moment is dropped, and each field it changed goes back
    to the value its first later change moved away from.
    """
    if parse_timestamp(raw["fields"]["created"]) > at:
        return None
    kept: list[dict] = []
    later: list[dict] = []
    for history in sorted(raw["changelog"]["histories"], key=lambda h: h["created"]):
        (kept if parse_timestamp(history["created"]) <= at else later).append(history)
    if not later:
        return raw
    fields = dict(raw["fields"])
    undone = set()
    for history in later:
        for item in history["items"]:
            field = item["field"]
            if field in _REWOUND_FIELDS and field not in undone:
                fields[field] = _REWOUND_FIELDS[field](item)
                undone.add(field)
    return {
        **raw,
        "fields": fields,
        "changelog": {**raw["changelog"], "histories": kept},
    }
