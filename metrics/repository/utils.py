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
        issues_response = j.search_issues(jql, maxResults=1, json_result=True)
    except JIRAError as err:
        logger.exception("Failed to fetch total issues from Jira")
        msg = f"Failed to fetch total issues from Jira: {err}"
        raise RuntimeError(msg) from err
    except Exception:
        logger.exception("Unexpected error in get_issues_total")
        raise
    else:
        logger.debug("Total %d issues...", issues_response["total"])
        return issues_response["total"]


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
            json_result=True,
        )
    except JIRAError as err:
        logger.exception("Failed to fetch issues slice from Jira")
        msg = f"Failed to fetch issues slice from Jira: {err}"
        raise RuntimeError(msg) from err
    except Exception:
        logger.exception("Unexpected error in get_issues_slice")
        raise
    else:
        return issues_response["issues"]


def get_issues_cloud(j: JIRA, jql: str) -> list[dict]:
    """Retrieve issues from Jira Cloud via token-based pagination.

    Jira Cloud removed the startAt-based search API; enhanced search
    paginates sequentially with nextPageToken, so no parallel fetching.

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
    next_page_token: str | None = None
    try:
        while True:
            response = j.enhanced_search_issues(
                jql,
                nextPageToken=next_page_token,
                maxResults=100,
                expand="changelog",
                json_result=True,
            )
            result.extend(response["issues"])
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
    except JIRAError as err:
        logger.exception("Failed to fetch issues from Jira Cloud")
        msg = f"Failed to fetch issues from Jira Cloud: {err}"
        raise RuntimeError(msg) from err
    return result


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

        with ThreadPoolExecutor(max_workers=min(8, len(offsets))) as pool:
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
