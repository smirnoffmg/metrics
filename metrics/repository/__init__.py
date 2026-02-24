"""Repository layer for issue data retrieval."""

from .base import BaseIssuesRepository
from .jira import JiraAPIRepository

__all__ = ["BaseIssuesRepository", "JiraAPIRepository"]
