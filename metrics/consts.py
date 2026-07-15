"""Constants for metrics calculations."""

from typing import Final

ONE_HOUR: Final[int] = 60 * 60
ONE_DAY: Final[int] = ONE_HOUR * 24
CALC_LIMIT: Final[int] = 30

TESTING_STATUSES: Final[list[str]] = ["testing"]
ACTIVE_STATUSES: Final[list[str]] = ["in progress"]

DONE_STATUSES: Final[list[str]] = [
    "done",
    "completed",
    "cancelled",
    "closed",
    "resolved",
]
