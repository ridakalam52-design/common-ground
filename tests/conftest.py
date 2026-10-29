import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """All tests run in mock mode with no keys and no network."""
    for k in ("QLOO_API_KEY", "GEMINI_API_KEY", "QLOO_MOCK", "GEMINI_MODEL", "GEMINI_FALLBACK_MODELS"):
        monkeypatch.delenv(k, raising=False)
    yield


EXAMPLE = {
    "city": "New Delhi",
    "friends": [
        {"name": "Aanya", "picks": ["Prateek Kuhad", "Zindagi Na Milegi Dobara", "Panchayat"]},
        {"name": "Kabir", "picks": ["Ritviz", "Gully Boy", "Seedhe Maut"]},
        {"name": "Meher", "picks": ["Coldplay", "Interstellar", "The White Tiger"]},
        {"name": "Rohan", "picks": ["Arijit Singh", "3 Idiots", "Karim's"]},
    ],
}
