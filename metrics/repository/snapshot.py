"""Raw Jira data saved to a file, so a report can be rebuilt without Jira."""

from __future__ import annotations

import json
from dataclasses import dataclass
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


def save_snapshot(snapshot: Snapshot, path: str | Path) -> None:
    """Write a snapshot as JSON."""
    payload = {
        "version": FORMAT_VERSION,
        "server": snapshot.server,
        "jql": snapshot.jql,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "issues": snapshot.issues,
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
    )


class StaticSnapshotSource:
    """Serves a snapshot already loaded from a file."""

    def __init__(self, snapshot: Snapshot) -> None:
        """Initialize with the loaded snapshot."""
        self.snapshot = snapshot

    def get_snapshot(self) -> Snapshot:
        """Return the loaded snapshot."""
        return self.snapshot
