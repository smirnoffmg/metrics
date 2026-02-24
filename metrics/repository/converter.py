"""Converter for transforming raw Jira API data into Issue entities."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from dateutil.parser import parse

from metrics.consts import DONE_STATUSES
from metrics.entity import Issue


class JiraDataConverter:
    """Converts raw Jira API dicts into Issue entities."""

    def convert_data_to_issue(self, data_item: dict) -> Issue:
        """Convert a raw Jira data dict into an Issue entity."""
        issue_created_at = parse(data_item["fields"]["created"])
        changelog = data_item["changelog"]
        changelog_data = self._parse_changelog_item(
            issue_created_at,
            changelog,
        )
        return Issue(
            key=data_item["key"],
            status=data_item["fields"]["status"]["name"],
            created_at=issue_created_at,
            doers_x_periods=changelog_data["doers_x_periods"],
            statuses_x_periods=changelog_data["statuses_x_periods"],
            first_status_change_at=changelog_data["first_status_changed_at"],
            last_finish_status_at=changelog_data["last_finish_status_at"],
            status_history=changelog_data["status_history"],
        )

    def _parse_changelog_item(
        self,
        issue_created_at: datetime,
        changelog: dict,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status_history": ["created"],
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

    def _parse_assignee_changes(
        self,
        item: dict,
        history_ts: datetime,
        data: dict[str, Any],
    ) -> None:
        data["doers_x_periods"][item["fromString"]] += (
            history_ts - data["last_assignee_changed_at"]
        )
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
        if item["toString"].lower() in DONE_STATUSES:
            data["last_finish_status_at"] = history_ts
