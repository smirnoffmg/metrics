"""DORA delivery metrics from GitLab release tags.

A deploy is a release tag. The raw data is what the GitLab API returns:
``tags`` and ``releases`` as listed, ``compares`` mapping each tag to the
commits between the tag before it and itself, and merged ``merge_requests``.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from statistics import median
from typing import TYPE_CHECKING

import pandas as pd
from dateutil.parser import parse

from metrics.consts import ONE_DAY

from .calculator import weekly_counts

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime


@dataclass(frozen=True)
class Change:
    """A commit, as first shipped by a deploy."""

    sha: str
    committed_at: datetime
    by_agent: bool


@dataclass(frozen=True)
class Deploy:
    """A release tag and the changes it shipped since the tag before it."""

    name: str
    at: datetime
    sha: str
    changes: tuple[Change, ...]
    # a hotfix or a rollback: the deploy before it failed
    fixes_previous: bool


def deploy_time(tag: dict, released_at: dict[str, str]) -> datetime:
    """When a tag reached production: its release, else the tag, else its commit."""
    stamp = (
        released_at.get(tag["name"])
        or tag.get("created_at")
        or tag["commit"]["committed_date"]
    )
    return parse(stamp)


def ordered_tags(raw_tags: Sequence[dict], raw_releases: Sequence[dict]) -> list[dict]:
    """Tags in the order they were deployed."""
    released_at = released_at_by_tag(raw_releases)
    return sorted(raw_tags, key=lambda tag: deploy_time(tag, released_at))


def deploys_from_raw(
    raw: dict,
    *,
    agent_authors: Iterable[str],
    hotfix_labels: Iterable[str],
) -> list[Deploy]:
    """Turn raw GitLab tags, compares and merge requests into ordered deploys."""
    agents = {author.lower() for author in agent_authors}
    hotfix = {label.lower() for label in hotfix_labels}
    mr_by_sha = _merge_requests_by_sha(raw.get("merge_requests", []))
    released_at = released_at_by_tag(raw.get("releases", []))

    deploys: list[Deploy] = []
    for tag in ordered_tags(raw["tags"], raw.get("releases", [])):
        commits = raw.get("compares", {}).get(tag["name"], [])
        mrs = [mr_by_sha[c["id"]] for c in commits if c["id"] in mr_by_sha]
        sha = tag["target"]
        earlier = {d.sha for d in deploys[:-1]}
        is_rollback = bool(deploys) and sha != deploys[-1].sha and sha in earlier
        is_hotfix = any(_is_hotfix_mr(mr, hotfix) for mr in mrs) or any(
            c["title"].startswith('Revert "') for c in commits
        )
        deploys.append(
            Deploy(
                name=tag["name"],
                at=deploy_time(tag, released_at),
                sha=sha,
                changes=tuple(
                    Change(
                        sha=c["id"],
                        committed_at=parse(c.get("committed_date") or c["created_at"]),
                        by_agent=_by_agent(c, mr_by_sha.get(c["id"]), agents),
                    )
                    for c in commits
                ),
                fixes_previous=is_rollback or is_hotfix,
            ),
        )
    return deploys


def deployment_frequency(
    deploys: Sequence[Deploy],
    now: datetime | None = None,
) -> dict[str, int]:
    """Deploys per finished ISO week, idle weeks counted as zero."""
    return weekly_counts([deploy.at.date() for deploy in deploys], now)


def change_lead_times(deploys: Sequence[Deploy]) -> pd.DataFrame:
    """Days from each commit to the deploy that first shipped it."""
    rows = [
        (
            deploy.name,
            change.sha,
            (deploy.at - change.committed_at).total_seconds() / ONE_DAY,
            change.by_agent,
        )
        for deploy in deploys
        for change in deploy.changes
    ]
    return pd.DataFrame(rows, columns=["deploy", "sha", "lead_time_days", "by_agent"])


def change_failure_rate(deploys: Sequence[Deploy]) -> float | None:
    """Share of deploys the next deploy had to fix; None before there are two.

    The latest deploy is left out: nothing has come after it yet to show
    whether it failed.
    """
    judged = _judged(deploys)
    if not judged:
        return None
    return sum(failed for _, failed in judged) / len(judged)


def recovery_times(deploys: Sequence[Deploy]) -> list[float]:
    """Days from each failed deploy to the deploy that fixed it."""
    return [
        (fix.at - failed.at).total_seconds() / ONE_DAY
        for failed, fix in pairwise(deploys)
        if fix.fixes_previous
    ]


def agent_comparison(deploys: Sequence[Deploy]) -> pd.DataFrame:
    """Compare agents' changes with people's: count, lead time, failure rate."""
    lead_times = change_lead_times(deploys)
    judged = _judged(deploys)
    rows = {}
    for group, by_agent in (("agents", True), ("people", False)):
        group_lead = lead_times.loc[
            lead_times["by_agent"] == by_agent, "lead_time_days"
        ]
        with_group = [
            failed
            for deploy, failed in judged
            if any(change.by_agent == by_agent for change in deploy.changes)
        ]
        rows[group] = {
            "changes": len(group_lead),
            "lead_time_p50_days": median(group_lead) if len(group_lead) else None,
            "change_failure_rate": (
                sum(with_group) / len(with_group) if with_group else None
            ),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def _judged(deploys: Sequence[Deploy]) -> list[tuple[Deploy, bool]]:
    return [
        (deploy, following.fixes_previous) for deploy, following in pairwise(deploys)
    ]


def released_at_by_tag(raw_releases: Iterable[dict]) -> dict[str, str]:
    """Map each tag with a dated release to when it was released."""
    return {
        release["tag_name"]: release["released_at"]
        for release in raw_releases
        if release.get("released_at")
    }


def _merge_requests_by_sha(raw_mrs: Iterable[dict]) -> dict[str, dict]:
    # a merge request lands as a merge commit, a squash commit or its own head
    by_sha = {}
    for mr in raw_mrs:
        for key in ("sha", "squash_commit_sha", "merge_commit_sha"):
            if mr.get(key):
                by_sha[mr[key]] = mr
    return by_sha


def _is_hotfix_mr(mr: dict, hotfix_labels: set[str]) -> bool:
    labels = {label.lower() for label in mr.get("labels", [])}
    return bool(labels & hotfix_labels) or mr.get("source_branch", "").startswith(
        "hotfix",
    )


def _by_agent(commit: dict, mr: dict | None, agents: set[str]) -> bool:
    authors = {
        (commit.get("author_name") or "").lower(),
        (commit.get("author_email") or "").lower(),
    }
    if mr:
        authors.add(((mr.get("author") or {}).get("username") or "").lower())
    return bool(authors & agents)
