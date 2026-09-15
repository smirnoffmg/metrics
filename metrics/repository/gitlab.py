"""Delivery data from GitLab: release tags, the commits between them, merge requests."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta
from itertools import pairwise
from typing import TYPE_CHECKING, Final

from metrics.services.delivery import deploy_time, ordered_tags, released_at_by_tag

if TYPE_CHECKING:
    from gitlab.v4.objects import Project

    from .jira import SnapshotSource
    from .snapshot import Snapshot

DEFAULT_GITLAB_URL: Final[str] = "https://gitlab.com"
DEFAULT_TAG_PATTERN: Final[str] = r"^v?\d+\.\d+\.\d+$"
DEFAULT_HOTFIX_LABELS: Final[list[str]] = ["hotfix"]
DEFAULT_DELIVERY_DAYS: Final[int] = 90


def fetch_delivery(project: Project, *, tag_pattern: str, since: datetime) -> dict:
    """Fetch release tags deployed since a date, with what each one shipped.

    The tag deployed just before the window is kept too: without it the
    first deploy in the window has nothing to compare against.
    """
    pattern = re.compile(tag_pattern)
    tags = [tag.attributes for tag in project.tags.list(get_all=True)]
    releases = [release.attributes for release in project.releases.list(get_all=True)]
    ordered = ordered_tags(
        [tag for tag in tags if pattern.search(tag["name"])], releases
    )
    released_at = released_at_by_tag(releases)
    first = next(
        (i for i, tag in enumerate(ordered) if deploy_time(tag, released_at) >= since),
        len(ordered),
    )
    window = ordered[max(first - 1, 0) :] if first < len(ordered) else []
    compares = {
        tag["name"]: project.repository_compare(previous["name"], tag["name"])[
            "commits"
        ]
        for previous, tag in pairwise(window)
    }
    merge_requests = []
    if window:
        # anything shipped after the oldest kept tag was merged, so updated, after it
        merge_requests = [
            mr.attributes
            for mr in project.mergerequests.list(
                state="merged",
                updated_after=window[0]["commit"]["committed_date"],
                get_all=True,
            )
        ]
    names = {tag["name"] for tag in window}
    return {
        "tags": window,
        "releases": [release for release in releases if release["tag_name"] in names],
        "compares": compares,
        "merge_requests": merge_requests,
    }


class GitLabDeliverySource:
    """Fetches delivery data for one GitLab project, or nothing without one."""

    def __init__(
        self,
        url: str,
        token: str | None,
        project: str,
        tag_pattern: str = DEFAULT_TAG_PATTERN,
        days: int = DEFAULT_DELIVERY_DAYS,
    ) -> None:
        """Initialize with the GitLab instance, the project path and the window."""
        self.url = url
        self.token = token
        self.project = project
        self.tag_pattern = tag_pattern
        self.days = days

    def fetch(self, now: datetime) -> dict | None:
        """Fetch the project's deploys in the window ending now."""
        if not self.project:
            return None
        import gitlab  # noqa: PLC0415 - only runs that read GitLab need the client

        client = gitlab.Gitlab(self.url, private_token=self.token or None)
        project = client.projects.get(self.project, lazy=True)
        raw = fetch_delivery(
            project,
            tag_pattern=self.tag_pattern,
            since=now - timedelta(days=self.days),
        )
        return {"project": self.project, "days": self.days, **raw}


class SnapshotWithDelivery:
    """A snapshot source that adds GitLab delivery data to Jira's snapshot."""

    def __init__(self, source: SnapshotSource, delivery: GitLabDeliverySource) -> None:
        """Initialize with the Jira snapshot source and the GitLab source."""
        self.source = source
        self.delivery = delivery

    def get_snapshot(self) -> Snapshot:
        """Take Jira's snapshot and fetch delivery data as of the same moment."""
        snapshot = self.source.get_snapshot()
        return replace(snapshot, delivery=self.delivery.fetch(snapshot.fetched_at))
