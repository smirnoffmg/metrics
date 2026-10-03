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
# Apache's and Atlassian's add, triage closures among them: an issue can sit in
# a done status with any of them, and a bulk triage would read as delivery.
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
    "low engagement",
    "timed out",
    "obsolete",
    "tracked elsewhere",
    "handled by support",
    "feedback received",
    "information provided",
    "later",
]

BACKLOG_STATUSES: Final[list[str]] = ["open", "new", "backlog", "to do", "reopened"]
