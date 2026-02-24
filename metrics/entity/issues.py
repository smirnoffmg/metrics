"""Issue entity representing a Jira ticket with timing data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime, timedelta


@dataclass
class Issue:
    """A Jira issue with status history and timing metadata."""

    key: str
    status: str

    created_at: datetime
    first_status_change_at: datetime | None = None
    last_finish_status_at: datetime | None = None

    status_history: list[str] | None = None

    doers_x_periods: dict[str, timedelta] | None = None
    statuses_x_periods: dict[str, timedelta] | None = None

    @property
    def was_done(self) -> bool:
        """Check if the issue reached a done status at some point."""
        return self.last_finish_status_at is not None

    @property
    def lead_time(self) -> timedelta | None:
        """Time from creation to completion, or None if not done."""
        if not self.last_finish_status_at:
            return None

        return self.last_finish_status_at - self.created_at

    @property
    def cycle_time(self) -> timedelta | None:
        """Time from first status change to completion, or None."""
        if self.first_status_change_at and self.last_finish_status_at:
            return self.last_finish_status_at - self.first_status_change_at
        return None
