"""Converter for transforming raw Jira API data into Issue entities."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from dateutil.parser import parse

from metrics.consts import (
    BACKLOG_STATUSES,
    DISCARDED_RESOLUTIONS,
    DISCARDED_STATUSES,
    DONE_STATUSES,
)
from metrics.entity import Issue
from metrics.entity.issues import StatusTransition


class JiraDataConverter:
    """Converts raw Jira API dicts into Issue entities."""

    def __init__(
        self,
        done_statuses: list[str] | None = None,
        discarded_statuses: list[str] | None = None,
        backlog_statuses: list[str] | None = None,
        discarded_resolutions: list[str] | None = None,
    ) -> None:
        """Initialize with the statuses that mean finished, dropped, or not started.

        Done and backlog lists given here override Jira's status categories;
        left out, a status's category decides, and the default names only
        cover statuses whose category is unknown.
        """
        self.done_explicit = bool(done_statuses)
        self.backlog_explicit = bool(backlog_statuses)
        self.done_statuses = _lowered(done_statuses or DONE_STATUSES)
        self.discarded_statuses = _lowered(discarded_statuses or DISCARDED_STATUSES)
        self.backlog_statuses = _lowered(backlog_statuses or BACKLOG_STATUSES)
        self.discarded_resolutions = _lowered(
            discarded_resolutions or DISCARDED_RESOLUTIONS,
        )

    def convert_data_to_issue(
        self,
        data_item: dict,
        status_categories: dict[str, str] | None = None,
    ) -> Issue:
        """Convert a raw Jira data dict into an Issue entity.

        status_categories maps a status id to its Jira category key:
        new, indeterminate or done.
        """
        issue_created_at = parse_timestamp(data_item["fields"]["created"])
        changelog = data_item["changelog"]
        changelog_data = self._parse_changelog_item(
            issue_created_at,
            changelog,
            status_categories or {},
        )
        self._credit_trailing_period(data_item, changelog_data)
        self._discard_by_resolution(data_item, changelog_data)
        return Issue(
            key=data_item["key"],
            status=data_item["fields"]["status"]["name"],
            created_at=issue_created_at,
            doers_x_periods=changelog_data["doers_x_periods"],
            statuses_x_periods=changelog_data["statuses_x_periods"],
            started_at=changelog_data["started_at"],
            last_finish_status_at=changelog_data["last_finish_status_at"],
            discarded=changelog_data["discarded"],
            status_history=changelog_data["status_history"],
            status_transitions=changelog_data["status_transitions"],
            handoffs=changelog_data["handoffs"],
        )

    def _parse_changelog_item(
        self,
        issue_created_at: datetime,
        changelog: dict,
        status_categories: dict[str, str],
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status_history": ["created"],
            "status_transitions": [],
            "handoffs": 0,
            "doers_x_periods": defaultdict(timedelta),
            "statuses_x_periods": defaultdict(timedelta),
            "started_at": None,
            "last_status_changed_at": issue_created_at,
            "first_assignee_changed_at": None,
            "last_assignee_changed_at": issue_created_at,
            "last_finish_status_at": None,
            "discarded": False,
        }
        for history_item in sorted(
            changelog["histories"],
            key=lambda x: x["created"],
        ):
            history_ts = parse_timestamp(history_item["created"])
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
                        status_categories,
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

    def _discard_by_resolution(self, data_item: dict, data: dict[str, Any]) -> None:
        """Treat a finished issue resolved as Won't Fix, Duplicate etc. as dropped.

        Many workflows close every issue through the same done status and record
        the outcome only in the resolution field.
        """
        resolution = (data_item["fields"].get("resolution") or {}).get("name")
        if not data["last_finish_status_at"] or not resolution:
            return
        if resolution.lower() in self.discarded_resolutions:
            data["last_finish_status_at"] = None
            data["discarded"] = True

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
        status_categories: dict[str, str],
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
        to_status = item["toString"].lower()
        category = status_categories.get(item.get("to") or "")
        is_done = self._is_done(to_status, category)
        is_discarded = not is_done and to_status in self.discarded_statuses
        # a reopened issue must stop counting as finished or discarded
        data["last_finish_status_at"] = history_ts if is_done else None
        data["discarded"] = is_discarded
        if (
            data["started_at"] is None
            and not is_done
            and not is_discarded
            and not self._is_backlog(to_status, category)
        ):
            data["started_at"] = history_ts

    def _is_done(self, status: str, category: str | None) -> bool:
        if self.done_explicit or category is None:
            return status in self.done_statuses
        # Jira files cancelled work under done too
        return category == "done" and status not in self.discarded_statuses

    def _is_backlog(self, status: str, category: str | None) -> bool:
        if self.backlog_explicit or category is None:
            return status in self.backlog_statuses
        return category == "new"


def parse_timestamp(stamp: str) -> datetime:
    """Parse a Jira timestamp, the ISO form Jira sends or anything dateutil reads.

    dateutil alone spends most of a large snapshot's conversion time here.
    """
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return parse(stamp)


def _lowered(statuses: list[str]) -> list[str]:
    return [status.lower() for status in statuses]
