import os
import tempfile
from datetime import datetime, timedelta

import pytest

from metrics.entity.issues import Issue


@pytest.fixture
def dummy_issue():
    return Issue(
        key="ISSUE-1",
        status="Done",
        created_at=datetime(2024, 1, 1, 0, 0, 0),
        first_status_change_at=datetime(2024, 1, 1, 1, 0, 0),
        last_finish_status_at=datetime(2024, 1, 1, 2, 0, 0),
        statuses_x_periods={"Done": timedelta(hours=1)},
    )


@pytest.fixture
def dummy_repo(dummy_issue):
    class DummyRepo:
        def all(self):
            return [dummy_issue]

    return DummyRepo()


@pytest.fixture
def temp_png_file():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        filename = tmp.name
    yield filename
    if os.path.exists(filename):
        os.remove(filename)
