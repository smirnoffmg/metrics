"""Utility functions for Jira client creation."""

from __future__ import annotations

from functools import cache

from jira import JIRA
from jira.exceptions import JIRAError


@cache
def get_jira_client(
    server: str,
    token: str | None,
    email: str | None = None,
    anonymous: bool = False,  # noqa: FBT001, FBT002 - wired positionally by the DI container
) -> JIRA:
    """Create and return a cached JIRA client.

    Uses @cache to memoize the result so the same client object is
    returned for identical arguments.

    Args:
    ----
        server: The URL of the JIRA server.
        token: The authentication token for the JIRA server.
        email: Account email for Jira Cloud basic auth. When omitted,
            the token is used as a Server/Data Center PAT.
        anonymous: True to connect without credentials (public instances).

    Returns:
    -------
        A JIRA client object.

    Raises:
    ------
        RuntimeError: If authentication or connection to Jira fails.

    """
    try:
        if anonymous:
            return JIRA(server=server)
        if email and token:
            return JIRA(server=server, basic_auth=(email, token))
        return JIRA(server=server, token_auth=token)
    except JIRAError as err:
        msg = f"Failed to authenticate or connect to Jira: {err}"
        raise RuntimeError(msg) from err
