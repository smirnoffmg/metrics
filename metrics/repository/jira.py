from collections import defaultdict
from datetime import datetime, timedelta

from dateutil.parser import parse
from jira import JIRA

from metrics.consts import DONE_STATUSES
from metrics.entity import Issue

from .base import BaseIssuesRepository
from .utils import get_issues


def parse_changelog_item(issue_created_at: datetime, changelog: dict) -> dict:
    first_assignee_changed_at = None
    first_status_changed_at = None
    last_status_changed_at = issue_created_at
    last_assignee_changed_at = issue_created_at
    last_finish_status_at = None

    status_history = ["created"]

    doers_x_periods = defaultdict(timedelta)
    statuses_x_periods = defaultdict(timedelta)

    for history_item in sorted(changelog["histories"], key=lambda x: x["created"]):
        for item in history_item["items"]:
            history_ts = parse(history_item["created"])

            if item["field"] == "assignee":
                doers_x_periods[item["fromString"]] += (
                    history_ts - last_assignee_changed_at
                )
                last_assignee_changed_at = history_ts

                if first_assignee_changed_at is None:
                    first_assignee_changed_at = history_ts
                else:
                    first_assignee_changed_at = min(
                        first_assignee_changed_at,
                        history_ts,
                    )

            elif item["field"] == "status":
                status_history.append(item["toString"])

                statuses_x_periods[item["fromString"]] += (
                    history_ts - last_status_changed_at
                )
                last_status_changed_at = history_ts

                if first_status_changed_at is None:
                    first_status_changed_at = history_ts
                else:
                    first_status_changed_at = min(first_status_changed_at, history_ts)

                if item["toString"].lower() in DONE_STATUSES:
                    last_finish_status_at = history_ts

    return {
        "status_history": status_history,
        "doers_x_periods": doers_x_periods,
        "statuses_x_periods": statuses_x_periods,
        "first_status_changed_at": first_status_changed_at,
        "last_status_changed_at": last_status_changed_at,
        "first_assignee_changed_at": first_assignee_changed_at,
        "last_assignee_changed_at": last_assignee_changed_at,
        "last_finish_status_at": last_finish_status_at,
    }


class JiraAPIRepository(BaseIssuesRepository):
    def __init__(self, jira: JIRA, jql: str) -> None:
        self.jira = jira
        self.jql = jql
        super().__init__()

    def convert_data_to_issue(self, data_item: dict) -> Issue:
        issue_created_at = parse(data_item["fields"]["created"])

        changelog = data_item["changelog"]

        changelog_data = parse_changelog_item(issue_created_at, changelog)
        doers_x_periods = changelog_data["doers_x_periods"]
        statuses_x_periods = changelog_data["statuses_x_periods"]
        last_finish_status_at = changelog_data["last_finish_status_at"]

        return Issue(
            key=data_item["key"],
            status=data_item["fields"]["status"]["name"],
            created_at=parse(data_item["fields"]["created"]),
            doers_x_periods=doers_x_periods,
            statuses_x_periods=statuses_x_periods,
            first_status_change_at=changelog_data["first_status_changed_at"],
            last_finish_status_at=last_finish_status_at,
            status_history=changelog_data["status_history"],
        )

    def get_raw_data(self) -> list[dict]:
        return get_issues(self.jira, self.jql)
