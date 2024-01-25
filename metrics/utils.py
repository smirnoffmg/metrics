from functools import cache

from jira import JIRA


@cache
def get_jira_client(server: str, token: str) -> JIRA:
    return JIRA(server=server, token_auth=token)
