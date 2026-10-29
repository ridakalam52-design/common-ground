import asyncio
import dataclasses

import pytest

from app.agent import CommonGroundAgent, Friend
from app.config import get_settings
from app.llm import LLMUnavailable
from app.mock_qloo import MockQloo
from app.qloo import QlooClient
from app.ranking import why_is_grounded

from .conftest import EXAMPLE


def run_agent(llm=None, **overrides):
    settings = dataclasses.replace(get_settings(), **overrides)
    backend = MockQloo(latency=0)
    events = []

    async def emit(ev):
        events.append(ev)

    agent = CommonGroundAgent(settings, QlooClient(backend), emit, llm)
    friends = [Friend(f["name"], f["picks"]) for f in EXAMPLE["friends"]]
    plan = asyncio.run(agent.run(friends, EXAMPLE["city"]))
    return plan, events, backend


@pytest.fixture(scope="module")
def scripted():
    return run_agent()


def test_scripted_plan_shape(scripted):
    plan, events, _ = scripted
    assert plan["mode"] == "mock" and plan["planner"] == "scripted"
    assert plan["friends"] == [f["name"] for f in EXAMPLE["friends"]]
    assert set(plan["slots"]) == {"watch", "soundtrack", "dinner"}
    for slot in plan["slots"].values():
        assert slot["pick"] is not None
        assert len(slot["alternates"]) == 2
    assert plan["summary"]
    assert plan["overlap"]["pairs"] and plan["overlap"]["tags"]
    assert events[0]["type"] == "start" and events[-1]["type"] == "plan"
    assert all(e["status"] in ("done", "running") for e in events if e["type"] == "step")


def test_every_why_is_grounded(scripted):
    plan, _, _ = scripted
    for slot in plan["slots"].values():
        for item in [slot["pick"], *slot["alternates"]]:
            assert item["why"] and why_is_grounded(item["why"], item)
            assert f"{item['affinity']:.2f}" in item["why"]


def test_place_location_filter_and_no_recs_endpoints(scripted):
    _, _, backend = scripted
    insights = [p for path, p in backend.calls if path == "/v2/insights"]
    places = [p for p in insights if p["filter.type"] == "urn:entity:place"]
    others = [p for p in insights if p["filter.type"] != "urn:entity:place"]
    assert places and all(p["filter.location.query"] == "New Delhi" for p in places)
    assert others and all("filter.location.query" not in p for p in others)
    paths = {path for path, _ in backend.calls}
    assert not any("recs" in p or "recommendations" in p for p in paths)
    assert {"/search", "/v2/tags", "/v2/insights", "/v2/analysis/compare"} <= paths


def test_dinner_is_in_city(scripted):
    plan, _, _ = scripted
    assert plan["locality"] == "New Delhi, Delhi, India"
    assert "Delhi" in (plan["slots"]["dinner"]["pick"]["address"] or plan["slots"]["dinner"]["pick"]["description"])


def test_friends_own_picks_not_recommended(scripted):
    plan, _, _ = scripted
    own = {p.lower() for f in EXAMPLE["friends"] for p in f["picks"]}
    for slot in plan["slots"].values():
        for item in [slot["pick"], *slot["alternates"]]:
            assert item["name"].lower() not in own


def test_ungrounded_why_rejected():
    c = {"signals": {"affinity": 0.91, "shared_tags": [{"name": "Drama", "score": 0.73}], "drivers": []}}
    assert why_is_grounded("Scores 0.91 with the group and leans into Drama.", c)
    assert not why_is_grounded("Scores 0.99 with everyone, a perfect fit.", c)
    assert not why_is_grounded("You will all love it, trust me on this one.", c)


class SlowLLM:
    active_model = "slow-model"

    async def generate(self, *a, **k):
        await asyncio.sleep(10)


class DeadLLM:
    active_model = None

    async def generate(self, *a, **k):
        raise LLMUnavailable("All Gemini models failed")


def test_gemini_timeout_falls_back_to_scripted():
    plan, events, _ = run_agent(llm=SlowLLM(), llm_timeout=0.3)
    assert plan["planner"] == "scripted"
    assert any(e["type"] == "note" and "longer than" in e["text"] for e in events)
    assert all(s["pick"] for s in plan["slots"].values())


def test_gemini_unavailable_falls_back_to_scripted():
    plan, events, _ = run_agent(llm=DeadLLM())
    assert plan["planner"] == "scripted"
    assert any(e["type"] == "note" and "unavailable" in e["text"] for e in events)


def test_default_models():
    s = get_settings()
    assert s.gemini_model == "gemini-3.1-flash-lite"
    assert s.gemini_models == ["gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]
    assert s.llm_timeout == 20.0 and s.mock_mode
