"""Issue entity representing a Jira ticket with timing data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime, timedelta


@dataclass(frozen=True)
class StatusTransition:
    """A single timestamped status change."""

    at: datetime
    from_status: str | None
    to_status: str


@dataclass
class Issue:
    """A Jira issue with status history and timing metadata."""

    key: str
    status: str

    created_at: datetime
    started_at: datetime | None = None
    last_finish_status_at: datetime | None = None
    discarded: bool = False

    status_history: list[str] = field(default_factory=list)
    status_transitions: list[StatusTransition] = field(default_factory=list)
    handoffs: int = 0

    doers_x_periods: dict[str | None, timedelta] = field(default_factory=dict)
    statuses_x_periods: dict[str, timedelta] = field(default_factory=dict)

    @property
    def was_done(self) -> bool:
        """Check if the issue's latest status transition was into a done status."""
        return self.last_finish_status_at is not None

    @property
    def is_open(self) -> bool:
        """Check if the issue is still pending: neither finished nor discarded."""
        return not self.was_done and not self.discarded

    @property
    def lead_time(self) -> timedelta | None:
        """Time from creation to completion, or None if not done."""
        if not self.last_finish_status_at:
            return None

        return self.last_finish_status_at - self.created_at

    @property
    def cycle_time(self) -> timedelta | None:
        """Time from leaving the backlog to completion, or None."""
        if self.started_at and self.last_finish_status_at:
            return self.last_finish_status_at - self.started_at
        return None
