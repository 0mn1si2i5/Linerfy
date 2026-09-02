import json
from pathlib import Path

from .models import IngestedContext


class FixtureSourceAdapter:
    """Offline adapter used to verify source contracts without crawling a publication."""

    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    def fetch(self) -> IngestedContext:
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        return IngestedContext.model_validate(payload)
