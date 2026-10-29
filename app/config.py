"""Runtime configuration, read from environment variables.

Nothing here is ever written to disk. Keys stay in the environment.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_GEMINI_FALLBACKS = "gemini-flash-lite-latest,gemini-2.5-flash-lite"


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    qloo_api_key: str | None
    qloo_base_url: str
    qloo_compare_path: str
    force_mock: bool
    gemini_api_key: str | None
    gemini_model: str
    gemini_fallback_models: list[str] = field(default_factory=list)
    max_agent_steps: int = 16
    llm_timeout: float = 20.0

    @property
    def mock_mode(self) -> bool:
        """Mock mode switches on automatically when QLOO_API_KEY is missing."""
        return self.force_mock or not self.qloo_api_key

    @property
    def llm_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def gemini_models(self) -> list[str]:
        seen: list[str] = []
        for m in [self.gemini_model, *self.gemini_fallback_models]:
            if m and m not in seen:
                seen.append(m)
        return seen


def get_settings() -> Settings:
    return Settings(
        qloo_api_key=os.getenv("QLOO_API_KEY") or None,
        qloo_base_url=os.getenv("QLOO_BASE_URL", "https://hackathon.api.qloo.com").rstrip("/"),
        # Documented path is /v2/analysis/compare (docs.qloo.com/reference/analysis-compare).
        qloo_compare_path=os.getenv("QLOO_COMPARE_PATH", "/v2/analysis/compare"),
        force_mock=os.getenv("QLOO_MOCK", "").lower() in {"1", "true", "yes"},
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
        gemini_fallback_models=_split(os.getenv("GEMINI_FALLBACK_MODELS", DEFAULT_GEMINI_FALLBACKS)),
        max_agent_steps=int(os.getenv("AGENT_MAX_STEPS", "16")),
        # Hard cap on the whole Gemini planning phase; after it the scripted planner finishes the plan.
        llm_timeout=float(os.getenv("GEMINI_TIMEOUT", "20")),
    )
