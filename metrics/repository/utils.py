import logging
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat

from jira import JIRA

logger = logging.getLogger(__name__)


def get_issues_total(j: JIRA, jql: str) -> int:
    """
    Get the total number of issues matching the given JQL query.

    Args:
        j (JIRA): An instance of the JIRA client.
        jql (str): The JQL query to search for issues.

    Returns:
        int: The total number of issues matching the JQL query.
    """
    issues_response = j.search_issues(jql, maxResults=0, json_result=True)
    logger.debug(f'Total {issues_response["total"]} issues...')
    return issues_response["total"]


def get_issues_slice(j: JIRA, jql: str, offset: int = 0, limit: int = 50) -> list[dict]:
    """Get a slice of issues from JIRA based on the provided JQL query.

    Args:
        j (JIRA): An instance of the JIRA client.
        jql (str): The JQL query to filter the issues.
        offset (int, default is 0): The starting index of the slice.
        limit (int, default is 50): The maximum number of issues to retrieve.

    Returns:
        list[dict]: A list of dictionaries representing the retrieved issues.
    """
    logger.debug(f"Getting issues slices from {offset} to {offset+limit}...")
    issues_response = j.search_issues(
        jql,
        startAt=offset,
        maxResults=limit,
        expand="changelog",
        json_result=True,
    )
    return issues_response["issues"]


def get_issues(j: JIRA, jql: str) -> list[dict]:
    """
    Retrieve a list of issues from JIRA based on the provided JQL query.

    Use a thread pool to retrieve the issues in parallel.

    Args:
        j (JIRA): An instance of the JIRA client.
        jql (str): The JQL query to filter the issues.

    Returns:
        list[dict]: A list of dictionaries representing the retrieved issues.
    """
    result = []
    per_page = 50

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

    return result
