"""Tests for fetching delivery data from GitLab."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from metrics.repository.gitlab import (
    GitLabDeliverySource,
    SnapshotWithDelivery,
    fetch_delivery,
)
from metrics.repository.snapshot import Snapshot


def _tag(name, sha, day):
    return SimpleNamespace(
        name=name,
        attributes={
            "name": name,
            "target": sha,
            "created_at": f"2026-{day}T12:00:00.000Z",
            "commit": {"id": sha, "committed_date": f"2026-{day}T10:00:00.000Z"},
        },
    )


class _Listing:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return self.items


class FakeProject:
    def __init__(self):
        self.tags = _Listing(
            [
                _tag("v1.3.0", "c4", "09-10"),
                _tag("nightly", "c9", "09-11"),
                _tag("v1.0.0", "c1", "05-01"),
                _tag("v1.1.0", "c2", "07-01"),
                _tag("v1.2.0", "c3", "08-20"),
            ],
        )
        self.releases = _Listing(
            [SimpleNamespace(attributes={"tag_name": "v1.2.0", "released_at": None})],
        )
        self.mergerequests = _Listing(
            [SimpleNamespace(attributes={"iid": 7, "sha": "c3"})],
        )
        self.compared = []

    def repository_compare(self, from_, to):
        self.compared.append((from_, to))
        return {"commits": [{"id": f"{from_}..{to}"}], "diffs": ["large"]}


def test_fetch_delivery_keeps_release_tags_in_the_window_and_the_one_before():
    project = FakeProject()
    raw = fetch_delivery(
        project,
        tag_pattern=r"^v\d+\.\d+\.\d+$",
        since=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert [tag["name"] for tag in raw["tags"]] == ["v1.1.0", "v1.2.0", "v1.3.0"]
    assert project.compared == [("v1.1.0", "v1.2.0"), ("v1.2.0", "v1.3.0")]
    assert raw["compares"] == {
        "v1.2.0": [{"id": "v1.1.0..v1.2.0"}],
        "v1.3.0": [{"id": "v1.2.0..v1.3.0"}],
    }
    assert raw["merge_requests"] == [{"iid": 7, "sha": "c3"}]
    mr_query = project.mergerequests.calls[0]
    assert mr_query["state"] == "merged"
    assert mr_query["updated_after"] == "2026-07-01T10:00:00.000Z"


def test_fetch_delivery_without_release_tags_returns_no_deploys():
    project = FakeProject()
    raw = fetch_delivery(
        project,
        tag_pattern=r"^release-",
        since=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert raw["tags"] == []
    assert raw["compares"] == {}


def test_snapshot_with_delivery_adds_gitlab_data_to_the_jira_snapshot():
    jira_snapshot = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 15, tzinfo=UTC),
        issues=[],
    )
    jira = SimpleNamespace(get_snapshot=lambda: jira_snapshot)
    fetched = []

    class Delivery:
        def fetch(self, now):
            fetched.append(now)
            return {"tags": []}

    snapshot = SnapshotWithDelivery(jira, Delivery()).get_snapshot()
    assert snapshot.delivery == {"tags": []}
    assert snapshot.issues == []
    assert fetched == [datetime(2026, 9, 15, tzinfo=UTC)]


def test_delivery_source_without_a_project_fetches_nothing():
    source = GitLabDeliverySource(url="https://gitlab.example", token=None, project="")
    assert source.fetch(datetime(2026, 9, 15, tzinfo=UTC)) is None
