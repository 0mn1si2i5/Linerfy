import json
from pathlib import Path

from pydantic import TypeAdapter

from .models import ReviewDocument


class FixtureSourceAdapter:
    """Offline adapter used to verify source contracts without crawling a publication."""

    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    def fetch(self) -> list[ReviewDocument]:
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        return TypeAdapter(list[ReviewDocument]).validate_python(payload)
