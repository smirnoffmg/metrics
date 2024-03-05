from functools import cache

from jira import JIRA


@cache
def get_jira_client(server: str, token: str) -> JIRA:
    """
    Create and return a JIRA client object.

    `@cache` is used to memoize the result of this function, so that the same
    client object is returned every time this function is called with the same
    arguments.

    Args:
        server (str): The URL of the JIRA server.
        token (str): The authentication token for the JIRA server.

    Returns:
        JIRA: A JIRA client object.

    """
    return JIRA(server=server, token_auth=token)
