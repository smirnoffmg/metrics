"""Constants for metrics calculations."""

from typing import Final

ONE_HOUR: Final[int] = 60 * 60
ONE_DAY: Final[int] = ONE_HOUR * 24

TESTING_STATUSES: Final[list[str]] = ["testing"]
ACTIVE_STATUSES: Final[list[str]] = ["in progress"]

DONE_STATUSES: Final[list[str]] = [
    "done",
    "completed",
    "closed",
    "resolved",
]

DISCARDED_STATUSES: Final[list[str]] = ["cancelled", "canceled", "won't do"]

# Jira's own "not delivered" resolutions plus the ones public trackers such as
# Apache's add; an issue can sit in a done status with any of them.
DISCARDED_RESOLUTIONS: Final[list[str]] = [
    "won't do",
    "won't fix",
    "duplicate",
    "cannot reproduce",
    "invalid",
    "incomplete",
    "not a problem",
    "not a bug",
    "works for me",
    "abandoned",
]

BACKLOG_STATUSES: Final[list[str]] = ["open", "new", "backlog", "to do", "reopened"]
