"""Raw Jira data saved to a file, so a report can be rebuilt without Jira."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

FORMAT_VERSION: Final[int] = 1


@dataclass(frozen=True)
class Snapshot:
    """Issues as Jira returned them, with where and when they were fetched."""

    server: str
    jql: str
    fetched_at: datetime
    issues: list[dict]
    # status id -> Jira status category key (new, indeterminate, done)
    statuses: dict[str, str] = field(default_factory=dict)
    # a second query naming the issues to forecast, such as an epic or release
    forecast_jql: str = ""
    forecast_issues: list[dict] = field(default_factory=list)


def save_snapshot(snapshot: Snapshot, path: str | Path) -> None:
    """Write a snapshot as JSON."""
    payload = {
        "version": FORMAT_VERSION,
        "server": snapshot.server,
        "jql": snapshot.jql,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "issues": snapshot.issues,
        "statuses": snapshot.statuses,
        "forecast_jql": snapshot.forecast_jql,
        "forecast_issues": snapshot.forecast_issues,
    }
    Path(path).write_text(json.dumps(payload))


def load_snapshot(path: str | Path) -> Snapshot:
    """Read a snapshot written by save_snapshot."""
    payload = json.loads(Path(path).read_text())
    version = payload.get("version")
    if version != FORMAT_VERSION:
        msg = f"Unsupported snapshot version {version!r} in {path}"
        raise ValueError(msg)
    return Snapshot(
        server=payload["server"],
        jql=payload["jql"],
        fetched_at=datetime.fromisoformat(payload["fetched_at"]),
        issues=payload["issues"],
        statuses=payload.get("statuses", {}),
        forecast_jql=payload.get("forecast_jql", ""),
        forecast_issues=payload.get("forecast_issues", []),
    )


def current_status_categories(issues: list[dict]) -> dict[str, str]:
    """Categories of the statuses issues sit in now, as their fields report them.

    Jira's status list can leave statuses out (anonymous access to Hibernate's
    Cloud lists 11, fewer than its issues move through), while each issue's
    own status always carries its category.
    """
    categories = {}
    for issue in issues:
        status = issue["fields"].get("status") or {}
        category = (status.get("statusCategory") or {}).get("key")
        if status.get("id") and category:
            categories[status["id"]] = category
    return categories


class StaticSnapshotSource:
    """Serves a snapshot already loaded from a file."""

    def __init__(self, snapshot: Snapshot) -> None:
        """Initialize with the loaded snapshot."""
        self.snapshot = snapshot

    def get_snapshot(self) -> Snapshot:
        """Return the loaded snapshot."""
        return self.snapshot
