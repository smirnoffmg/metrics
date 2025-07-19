import logging
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat

from jira import JIRA
from jira.exceptions import JIRAError

logger = logging.getLogger(__name__)


def get_issues_total(j: JIRA, jql: str) -> int:
    """Get the total number of issues matching the given JQL query.

    Args:
    ----
        j (JIRA): An instance of the JIRA client.
        jql (str): The JQL query to search for issues.

    Returns:
    -------
        int: The total number of issues matching the JQL query.

    Raises:
    ------
        RuntimeError: If the Jira API call fails.

    """
    try:
        issues_response = j.search_issues(jql, maxResults=0)
        if isinstance(issues_response, dict):
            logger.debug(f"Total {issues_response['total']} issues...")
            return issues_response["total"]
        logger.debug(f"Total {issues_response.total} issues...")
        return issues_response.total
    except JIRAError as err:
        logger.exception("Failed to fetch total issues from Jira")
        msg = f"Failed to fetch total issues from Jira: {err}"
        raise RuntimeError(msg) from err
    except Exception:
        logger.exception("Unexpected error in get_issues_total")
        raise


def get_issues_slice(j: JIRA, jql: str, offset: int = 0, limit: int = 50) -> list[dict]:
    """Get a slice of issues from JIRA based on the provided JQL query.

    Args:
    ----
        j (JIRA): An instance of the JIRA client.
        jql (str): The JQL query to filter the issues.
        offset (int, optional): The starting index of the slice. Defaults to 0.
        limit (int, optional): The maximum number of issues to retrieve. Defaults to 50.

    Returns:
    -------
        list[dict]: A list of dictionaries representing the retrieved issues.

    Raises:
    ------
        RuntimeError: If the Jira API call fails.

    """
    try:
        logger.debug(f"Getting issues slices from {offset} to {offset + limit}...")
        issues_response = j.search_issues(
            jql,
            startAt=offset,
            maxResults=limit,
            expand="changelog",
        )
        if isinstance(issues_response, dict):
            return issues_response["issues"]
        return list(issues_response)
    except JIRAError as err:
        logger.exception("Failed to fetch issues slice from Jira")
        msg = f"Failed to fetch issues slice from Jira: {err}"
        raise RuntimeError(msg) from err
    except Exception:
        logger.exception("Unexpected error in get_issues_slice")
        raise


def get_issues(j: JIRA, jql: str) -> list[dict]:
    """Retrieve a list of issues from JIRA based on the provided JQL query.
    Uses a thread pool to retrieve the issues in parallel.

    Args:
    ----
        j (JIRA): An instance of the JIRA client.
        jql (str): The JQL query to filter the issues.

    Returns:
    -------
        list[dict]: A list of dictionaries representing the retrieved issues.

    Raises:
    ------
        RuntimeError: If the Jira API call fails.

    """
    result = []
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
