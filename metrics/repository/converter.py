"""Converter for transforming raw Jira API data into Issue entities."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from dateutil.parser import parse

from metrics.consts import DONE_STATUSES
from metrics.entity import Issue
from metrics.entity.issues import StatusTransition


class JiraDataConverter:
    """Converts raw Jira API dicts into Issue entities."""

    def __init__(self, done_statuses: list[str] | None = None) -> None:
        """Initialize with the statuses that count as completion."""
        self.done_statuses = [
            status.lower() for status in (done_statuses or DONE_STATUSES)
        ]

    def convert_data_to_issue(self, data_item: dict) -> Issue:
        """Convert a raw Jira data dict into an Issue entity."""
        issue_created_at = parse(data_item["fields"]["created"])
        changelog = data_item["changelog"]
        changelog_data = self._parse_changelog_item(
            issue_created_at,
            changelog,
        )
        self._credit_trailing_period(data_item, changelog_data)
        return Issue(
            key=data_item["key"],
            status=data_item["fields"]["status"]["name"],
            created_at=issue_created_at,
            doers_x_periods=changelog_data["doers_x_periods"],
            statuses_x_periods=changelog_data["statuses_x_periods"],
            first_status_change_at=changelog_data["first_status_changed_at"],
            last_finish_status_at=changelog_data["last_finish_status_at"],
            status_history=changelog_data["status_history"],
            status_transitions=changelog_data["status_transitions"],
            handoffs=changelog_data["handoffs"],
        )

    def _parse_changelog_item(
        self,
        issue_created_at: datetime,
        changelog: dict,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status_history": ["created"],
            "status_transitions": [],
            "handoffs": 0,
            "doers_x_periods": defaultdict(timedelta),
            "statuses_x_periods": defaultdict(timedelta),
            "first_status_changed_at": None,
            "last_status_changed_at": issue_created_at,
            "first_assignee_changed_at": None,
            "last_assignee_changed_at": issue_created_at,
            "last_finish_status_at": None,
        }
        for history_item in sorted(
            changelog["histories"],
            key=lambda x: x["created"],
        ):
            history_ts = parse(history_item["created"])
            for item in history_item["items"]:
                if item["field"] == "assignee":
                    self._parse_assignee_changes(
                        item,
                        history_ts,
                        data,
                    )
                elif item["field"] == "status":
                    self._parse_status_changes(
                        item,
                        history_ts,
                        data,
                    )
        return data

    @staticmethod
    def _credit_trailing_period(data_item: dict, data: dict[str, Any]) -> None:
        """Attribute time after the last assignee change to the current assignee.

        The changelog only credits people when the assignee CHANGES, so
        without this the final (usually main) assignee gets nothing.
        """
        assignee = (data_item["fields"].get("assignee") or {}).get("displayName")
        if not assignee:
            return
        end = data["last_finish_status_at"] or max(
            data["last_status_changed_at"],
            data["last_assignee_changed_at"],
        )
        if end > data["last_assignee_changed_at"]:
            data["doers_x_periods"][assignee] += end - data["last_assignee_changed_at"]

    def _parse_assignee_changes(
        self,
        item: dict,
        history_ts: datetime,
        data: dict[str, Any],
    ) -> None:
        data["doers_x_periods"][item["fromString"]] += (
            history_ts - data["last_assignee_changed_at"]
        )
        data["handoffs"] += 1
        data["last_assignee_changed_at"] = history_ts
        if data["first_assignee_changed_at"] is None:
            data["first_assignee_changed_at"] = history_ts
        else:
            data["first_assignee_changed_at"] = min(
                data["first_assignee_changed_at"],
                history_ts,
            )

    def _parse_status_changes(
        self,
        item: dict,
        history_ts: datetime,
        data: dict[str, Any],
    ) -> None:
        data["status_history"].append(item["toString"])
        data["status_transitions"].append(
            StatusTransition(
                at=history_ts,
                from_status=item["fromString"],
                to_status=item["toString"],
            ),
        )
        data["statuses_x_periods"][item["fromString"]] += (
            history_ts - data["last_status_changed_at"]
        )
        data["last_status_changed_at"] = history_ts
        if data["first_status_changed_at"] is None:
            data["first_status_changed_at"] = history_ts
        else:
            data["first_status_changed_at"] = min(
                data["first_status_changed_at"],
                history_ts,
            )
        if item["toString"].lower() in self.done_statuses:
            data["last_finish_status_at"] = history_ts
