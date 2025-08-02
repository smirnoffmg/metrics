from jira import JIRA

from .base import BaseIssuesRepository
from .converter import JiraDataConverter
from .utils import get_issues


class JiraAPIRepository:
    def __init__(self, jira: JIRA, jql: str) -> None:
        self.jira = jira
        self.jql = jql

    def get_raw_data(self) -> list[dict]:
        return get_issues(self.jira, self.jql)


class JiraIssuesRepository(BaseIssuesRepository):
    def __init__(
        self, api_repo: JiraAPIRepository, converter: JiraDataConverter,
    ) -> None:
        self.api_repo = api_repo
        self.converter = converter
        super().__init__()

    def get_raw_data(self) -> list[dict]:
        return self.api_repo.get_raw_data()

    def convert_data_to_issue(self, data_item: dict):
        return self.converter.convert_data_to_issue(data_item)
