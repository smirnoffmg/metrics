"""Utilities for fetching issues from the Jira API."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from typing import TYPE_CHECKING

from jira.exceptions import JIRAError

if TYPE_CHECKING:
    from jira import JIRA

logger = logging.getLogger(__name__)


def get_issues_total(j: JIRA, jql: str) -> int:
    """Get the total number of issues matching the given JQL query.

    Args:
    ----
        j: An instance of the JIRA client.
        jql: The JQL query to search for issues.

    Returns:
    -------
        The total number of issues matching the JQL query.

    Raises:
    ------
        RuntimeError: If the Jira API call fails.

    """
    try:
        issues_response = j.search_issues(jql, maxResults=0)
    except JIRAError as err:
        logger.exception("Failed to fetch total issues from Jira")
        msg = f"Failed to fetch total issues from Jira: {err}"
        raise RuntimeError(msg) from err
    except Exception:
        logger.exception("Unexpected error in get_issues_total")
        raise
    else:
        if isinstance(issues_response, dict):
            logger.debug(
                "Total %d issues...",
                issues_response["total"],
            )
            return issues_response["total"]
        logger.debug("Total %d issues...", issues_response.total)
        return issues_response.total


def get_issues_slice(
    j: JIRA,
    jql: str,
    offset: int = 0,
    limit: int = 50,
) -> list[dict]:
    """Get a slice of issues from JIRA based on the provided JQL query.

    Args:
    ----
        j: An instance of the JIRA client.
        jql: The JQL query to filter the issues.
        offset: The starting index of the slice. Defaults to 0.
        limit: The maximum number of issues to retrieve.

    Returns:
    -------
        A list of dictionaries representing the retrieved issues.

    Raises:
    ------
        RuntimeError: If the Jira API call fails.

    """
    try:
        logger.debug(
            "Getting issues slices from %d to %d...",
            offset,
            offset + limit,
        )
        issues_response = j.search_issues(
            jql,
            startAt=offset,
            maxResults=limit,
            expand="changelog",
        )
    except JIRAError as err:
        logger.exception("Failed to fetch issues slice from Jira")
        msg = f"Failed to fetch issues slice from Jira: {err}"
        raise RuntimeError(msg) from err
    except Exception:
        logger.exception("Unexpected error in get_issues_slice")
        raise
    else:
        if isinstance(issues_response, dict):
            return issues_response["issues"]
        return list(issues_response)


def get_issues(j: JIRA, jql: str) -> list[dict]:
    """Retrieve issues from JIRA in parallel using a thread pool.

    Args:
    ----
        j: An instance of the JIRA client.
        jql: The JQL query to filter the issues.

    Returns:
    -------
        A list of dictionaries representing the retrieved issues.

    Raises:
    ------
        RuntimeError: If the Jira API call fails.

    """
    result: list[dict] = []
    per_page = 50
    try:
        issues_total = get_issues_total(j, jql)
        offsets = [p * per_page for p in range(issues_total // per_page + 1)]

        with ThreadPoolExecutor(max_workers=len(offsets)) as pool:
            for result_chunk in pool.map(
                get_issues_slice,
                repeat(j),
                repeat(jql),
                offsets,
                repeat(per_page),
            ):
                result.extend(result_chunk)
    except Exception as err:
        logger.exception("Failed to fetch issues from Jira")
        msg = f"Failed to fetch issues from Jira: {err}"
        raise RuntimeError(msg) from err
    return result
