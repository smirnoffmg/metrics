"""Tests for DORA delivery metrics computed from GitLab tags."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from metrics.services.delivery import (
    agent_comparison,
    change_failure_rate,
    change_lead_times,
    deployment_frequency,
    deploys_from_raw,
    recovery_times,
)


def _commit(sha, day, title="Change", author="alice"):
    return {
        "id": sha,
        "title": title,
        "author_name": author,
        "author_email": f"{author}@example.com",
        "committed_date": f"2026-09-{day:02d}T10:00:00.000Z",
    }


def _tag(name, sha, day):
    return {
        "name": name,
        "target": sha,
        "created_at": f"2026-09-{day:02d}T12:00:00.000Z",
        "commit": _commit(sha, day),
    }


def _mr(sha, author="alice", labels=(), branch="feature"):
    return {
        "iid": int(sha.strip("c") or 0),
        "sha": sha,
        "merge_commit_sha": None,
        "squash_commit_sha": None,
        "labels": list(labels),
        "source_branch": branch,
        "author": {"username": author},
    }


def _raw(**overrides):
    raw = {
        "tags": [
            _tag("v1.0.0", "c1", 1),
            _tag("v1.1.0", "c3", 8),
            _tag("v1.1.1", "c4", 9),
            _tag("v1.2.0", "c6", 15),
        ],
        "releases": [{"tag_name": "v1.1.0", "released_at": "2026-09-08T18:00:00.000Z"}],
        "compares": {
            "v1.1.0": [_commit("c2", 3), _commit("c3", 7, author="srv_agent")],
            "v1.1.1": [_commit("c4", 9, title="Fix crash")],
            "v1.2.0": [_commit("c5", 12), _commit("c6", 14)],
        },
        "merge_requests": [
            _mr("c3", author="srv_agent"),
            _mr("c4", labels=["Hotfix"]),
        ],
    }
    raw.update(overrides)
    return raw


def _deploys(raw=None):
    return deploys_from_raw(
        raw or _raw(),
        agent_authors=["srv_agent"],
        hotfix_labels=["hotfix"],
    )


def test_deploys_are_ordered_and_timed_by_release_then_tag():
    deploys = _deploys()
    assert [d.name for d in deploys] == ["v1.0.0", "v1.1.0", "v1.1.1", "v1.2.0"]
    assert deploys[1].at == datetime(2026, 9, 8, 18, tzinfo=UTC)
    assert deploys[2].at == datetime(2026, 9, 9, 12, tzinfo=UTC)
    assert deploys[0].changes == ()


def test_a_hotfix_mr_marks_its_deploy_as_fixing_the_previous_one():
    deploys = _deploys()
    assert [d.fixes_previous for d in deploys] == [False, False, True, False]


def test_a_revert_commit_marks_a_fix():
    raw = _raw()
    raw["compares"]["v1.2.0"] = [_commit("c6", 14, title='Revert "Add cache"')]
    assert _deploys(raw)[3].fixes_previous


def test_retagging_an_earlier_commit_is_a_rollback():
    raw = _raw()
    raw["tags"].append(_tag("v1.2.1", "c4", 16))
    raw["compares"]["v1.2.1"] = []
    deploys = _deploys(raw)
    assert deploys[-1].fixes_previous
    # the same commit tagged twice in a row is a re-release, not a rollback
    raw["tags"].append(_tag("v1.2.2", "c4", 17))
    raw["compares"]["v1.2.2"] = []
    assert not _deploys(raw)[-1].fixes_previous


def test_change_lead_time_runs_from_commit_to_the_deploy_that_shipped_it():
    df = change_lead_times(_deploys())
    rows = {row.sha: row for row in df.itertuples()}
    assert rows["c2"].lead_time_days == pytest.approx(5 + 8 / 24)
    assert rows["c3"].by_agent
    assert not rows["c2"].by_agent
    assert set(rows) == {"c2", "c3", "c4", "c5", "c6"}


def test_change_failure_rate_leaves_out_the_latest_deploy():
    # v1.1.0 failed (v1.1.1 fixed it); v1.2.0 is too recent to judge
    assert change_failure_rate(_deploys()) == pytest.approx(1 / 3)
    assert change_failure_rate(_deploys()[:1]) is None


def test_recovery_time_is_the_gap_to_the_fixing_deploy():
    assert recovery_times(_deploys()) == [pytest.approx(18 / 24)]


def test_deployment_frequency_counts_finished_weeks():
    weekly = deployment_frequency(_deploys(), now=datetime(2026, 9, 16, tzinfo=UTC))
    # 2026-09-14 starts the current week, so v1.2.0 is not counted yet
    assert weekly == {"2026W36": 1, "2026W37": 2}


def test_agent_comparison_splits_changes_lead_time_and_failures():
    df = agent_comparison(_deploys())
    agents = df.loc["agents"]
    people = df.loc["people"]
    assert agents["changes"] == 1
    assert people["changes"] == 4  # noqa: PLR2004
    # the only judged deploy with agent changes, v1.1.0, failed
    assert agents["change_failure_rate"] == 1.0
    # people's changes shipped in v1.1.0 (failed) and v1.1.1 (not failed)
    assert people["change_failure_rate"] == pytest.approx(0.5)
