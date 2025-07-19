import logging
from functools import cache

from jira import JIRA
from jira.exceptions import JIRAError

logger = logging.getLogger(__name__)


@cache
def get_jira_client(server: str, token: str) -> JIRA:
    """Create and return a JIRA client object.

    Uses @cache to memoize the result of this function, so that the same
    client object is returned every time this function is called with the same
    arguments.

    Args:
    ----
        server (str): The URL of the JIRA server.
        token (str): The authentication token for the JIRA server.

    Returns:
    -------
        JIRA: A JIRA client object.

    Raises:
    ------
        RuntimeError: If authentication or connection to Jira fails.

    """
    try:
        return JIRA(server=server, token_auth=token)
    except JIRAError as err:
        logger.exception("Failed to authenticate or connect to Jira")
        msg = f"Failed to authenticate or connect to Jira: {err}"
        raise RuntimeError(msg) from err
    except Exception:
        logger.exception("Unexpected error in get_jira_client")
        raise
