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
    def is_done(self) -> bool:
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
