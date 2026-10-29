"""FastAPI app: serves the single-page UI and streams the agent run over SSE."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .agent import CommonGroundAgent, Friend
from .config import get_settings
from .llm import Gemini
from .mock_qloo import MockQloo
from .qloo import LiveQloo, QlooClient

logging.basicConfig(level=logging.INFO)
STATIC = Path(__file__).parent / "static"

EXAMPLE = {
    "city": "New Delhi",
    "friends": [
        {"name": "Aanya", "picks": ["Prateek Kuhad", "Zindagi Na Milegi Dobara", "Panchayat"]},
        {"name": "Kabir", "picks": ["Ritviz", "Gully Boy", "Seedhe Maut"]},
        {"name": "Meher", "picks": ["Coldplay", "Interstellar", "The White Tiger"]},
        {"name": "Rohan", "picks": ["Arijit Singh", "3 Idiots", "Karim's"]},
    ],
}

app = FastAPI(title="Common Ground", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_qloo_backend: Any = None


def qloo_client() -> QlooClient:
    """One backend per process so the private in-memory cache is shared across requests."""
    global _qloo_backend
    s = get_settings()
    want = "mock" if s.mock_mode else "qloo"
    if _qloo_backend is None or _qloo_backend.name != want:
        _qloo_backend = MockQloo() if s.mock_mode else LiveQloo(s.qloo_api_key, s.qloo_base_url)
    return QlooClient(_qloo_backend, s.qloo_compare_path)


class FriendIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    picks: list[str] = Field(min_length=1, max_length=6)

    @field_validator("picks")
    @classmethod
    def clean(cls, v: list[str]) -> list[str]:
        out = [p.strip()[:80] for p in v if p and p.strip()]
        if not out:
            raise ValueError("each friend needs at least one pick")
        return out


class PlanIn(BaseModel):
    city: str = Field(default="New Delhi", min_length=2, max_length=80)
    friends: list[FriendIn] = Field(min_length=2, max_length=5)

    @field_validator("friends")
    @classmethod
    def unique(cls, v: list[FriendIn]) -> list[FriendIn]:
        names = [f.name.strip().lower() for f in v]
        if len(set(names)) != len(names):
            raise ValueError("friend names must be unique")
        return v


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health() -> dict:
    s = get_settings()
    return {"ok": True, "mode": "mock" if s.mock_mode else "live",
            "planner": "gemini" if s.llm_enabled else "scripted",
            "models": s.gemini_models if s.llm_enabled else []}


@app.get("/api/example")
async def example() -> dict:
    return EXAMPLE


async def _run(body: PlanIn, emit) -> dict:
    s = get_settings()
    llm = Gemini(s.gemini_api_key, s.gemini_models) if s.llm_enabled else None
    agent = CommonGroundAgent(s, qloo_client(), emit, llm)
    friends = [Friend(f.name.strip(), f.picks) for f in body.friends]
    return await agent.run(friends, body.city.strip())


@app.post("/api/plan")
async def plan(body: PlanIn) -> dict:
    """Non-streaming variant: returns the plan plus the full trace."""
    trace: list[dict] = []

    async def emit(ev: dict) -> None:
        trace.append(ev)

    result = await _run(body, emit)
    return {"plan": result, "trace": trace}


@app.post("/api/plan/stream")
async def plan_stream(body: PlanIn) -> StreamingResponse:
    """Server-sent events: one event per agent step, HTTP call, thought, then the plan."""
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(ev: dict) -> None:
        await queue.put(ev)

    async def worker() -> None:
        try:
            await _run(body, emit)
        except Exception as exc:  # noqa: BLE001
            logging.exception("agent run failed")
            await queue.put({"type": "error", "message": str(exc)[:300]})
        finally:
            await queue.put(None)

    async def events():
        task = asyncio.create_task(worker())
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    yield "event: done\ndata: {}\n\n"
                    break
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

