"""Gemini wrapper (google-genai SDK) with model fallback.

Model order: GEMINI_MODEL (default gemini-3.1-flash-lite), then the
comma-separated GEMINI_FALLBACK_MODELS. A model that errors (404 unknown model,
429 quota, 5xx) is skipped for the rest of the run.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("commonground.llm")


class LLMUnavailable(RuntimeError):
    pass


class Gemini:
    def __init__(self, api_key: str, models: list[str]):
        from google import genai  # imported lazily so mock/test runs need no key

        self._genai = genai
        self.client = genai.Client(api_key=api_key)
        self.models = list(models)
        self.active_model: str | None = None
        self.errors: list[str] = []

    async def generate(self, contents: list[Any], system: str, tools: list[dict] | None = None,
                       temperature: float = 0.4) -> Any:
        from google.genai import types

        cfg_kwargs: dict[str, Any] = {"system_instruction": system, "temperature": temperature}
        if tools:
            cfg_kwargs["tools"] = [types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t["name"], description=t["description"],
                                          parameters_json_schema=t["parameters"]) for t in tools])]
            cfg_kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
        config = types.GenerateContentConfig(**cfg_kwargs)
        candidates = [self.active_model] if self.active_model else []
        candidates += [m for m in self.models if m not in candidates]
        for model in candidates:
            try:
                resp = await self.client.aio.models.generate_content(model=model, contents=contents, config=config)
                self.active_model = model
                return resp
            except Exception as exc:  # noqa: BLE001 - any provider error means try the next model
                msg = f"{model}: {type(exc).__name__}: {str(exc)[:160]}"
                log.warning("Gemini call failed, trying next model. %s", msg)
                self.errors.append(msg)
                if model in self.models:
                    self.models.remove(model)
                if self.active_model == model:
                    self.active_model = None
        raise LLMUnavailable("All Gemini models failed: " + " | ".join(self.errors[-3:]))

    @staticmethod
    def user(text: str) -> Any:
        from google.genai import types
        return types.Content(role="user", parts=[types.Part.from_text(text=text)])

    @staticmethod
    def function_responses(items: list[tuple[str, dict]]) -> Any:
        from google.genai import types
        return types.Content(role="user", parts=[
            types.Part.from_function_response(name=name, response=payload) for name, payload in items])
