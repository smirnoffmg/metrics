from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Issue:
    key: str
    status: str

    created_at: datetime
    first_status_change_at: datetime | None = None
    last_finish_status_at: datetime | None = None

    doers_x_periods: dict[str, timedelta] | None = None
    statuses_x_periods: dict[str, timedelta] | None = None

    @property
    def was_done(self) -> bool:
        """
        Checks if the issue was in a done status at some point.

        Returns:
            bool: True if the issue was done, False otherwise.
        """
        return self.last_finish_status_at is not None

    @property
    def lead_time(self) -> timedelta | None:
        if not self.last_finish_status_at:
            return None

        return self.last_finish_status_at - self.created_at

    @property
    def cycle_time(self) -> timedelta | None:
        if self.first_status_change_at and self.last_finish_status_at:
            return self.last_finish_status_at - self.first_status_change_at
        return None
