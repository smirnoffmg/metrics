from metrics.entity import Issue


class BaseIssuesRepository:
    issues: dict[str, Issue]

    def __init__(self) -> None:
        self.issues = {issue.key: issue for issue in self.get_issues()}

    def get(self, key: str) -> Issue | None:
        return self.issues.get(key)

    def all(self) -> list[Issue]:
        return list(self.issues.values())

    def convert_data_to_issue(self, data_item: dict) -> Issue:
        raise NotImplementedError

    def get_raw_data(self) -> list[dict]:
        raise NotImplementedError

    def get_issues(self) -> list[Issue]:
        return [
            self.convert_data_to_issue(data_item) for data_item in self.get_raw_data()
        ]
