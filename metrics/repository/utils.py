import logging
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat

from jira import JIRA

logger = logging.getLogger(__name__)


def get_issues_total(j: JIRA, jql: str) -> int:
    issues_response = j.search_issues(jql, maxResults=0, json_result=True)
    logger.debug(f'Total {issues_response["total"]} issues...')
    return issues_response["total"]


def get_issues_slice(j: JIRA, jql: str, offset: int = 0, limit: int = 50) -> list[dict]:
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
