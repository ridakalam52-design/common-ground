"""The Common Ground agent.

Gemini plans the tool calls (function calling) and writes the "why" for every
pick. The server executes each tool against Qloo and streams every step to the
UI. If Gemini is not configured or every model fails, a scripted planner runs
the same tools in the same order and explanations come from templates built on
the same Qloo signals, so the app always returns a grounded plan.
"""
from __future__ import annotations

import asyncio
import contextvars
import itertools
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .config import Settings
from .llm import Gemini, LLMUnavailable
from .qloo import QlooClient, _norm, best_match, in_city
from .ranking import build_overlap_map, fmt_aff, rank, template_why, why_is_grounded

Json = dict[str, Any]
Emit = Callable[[Json], Awaitable[None]]

SLOTS = {
    "watch": {"label": "Movie or show", "types": ["urn:entity:movie", "urn:entity:tv_show"]},
    "soundtrack": {"label": "Soundtrack artist", "types": ["urn:entity:artist"]},
    "dinner": {"label": "Dinner place", "types": ["urn:entity:place"]},
}
TYPE_TO_SLOT = {"movie": "watch", "tv_show": "watch", "artist": "soundtrack", "place": "dinner"}
_current_step: contextvars.ContextVar[str | None] = contextvars.ContextVar("step", default=None)


@dataclass
class Friend:
    name: str
    picks: list[str]


@dataclass
class AgentState:
    friends: list[Friend]
    city: str
    resolved: dict[str, list[Json]] = field(default_factory=dict)
    unresolved: dict[str, list[str]] = field(default_factory=dict)
    candidates: dict[str, list[Json]] = field(default_factory=lambda: {k: [] for k in SLOTS})
    pairs: dict[tuple[str, str], Json] = field(default_factory=dict)
    restaurant_tag: str | None = None
    tag_lookup_done: bool = False
    locality: str | None = None

    @property
    def names(self) -> list[str]:
        return [f.name for f in self.friends]

    def friend(self, name: str) -> Friend | None:
        low = (name or "").strip().lower()
        return next((f for f in self.friends if f.name.lower() == low), None)

    def all_ids(self) -> list[str]:
        seen: list[str] = []
        for f in self.friends:
            for e in self.resolved.get(f.name, []):
                if e["id"] not in seen:
                    seen.append(e["id"])
        return seen

    def pick_owner(self) -> dict[str, tuple[str, str]]:
        out: dict[str, tuple[str, str]] = {}
        for f in self.friends:
            for e in self.resolved.get(f.name, []):
                out.setdefault(e["id"], (f.name, e["name"]))
        return out

    def overlap(self) -> Json:
        prs = [{"a": a, "b": b, **v} for (a, b), v in self.pairs.items()]
        return build_overlap_map(self.names, prs)


class RecordingBackend:
    """Wraps a Qloo backend so every HTTP call shows up in the live trace."""

    def __init__(self, inner, emit: Emit):
        self.inner = inner
        self.name = inner.name
        self.emit = emit

    async def get(self, path: str, params: dict[str, Any]) -> Json:
        shown = {k: (v if len(str(v)) <= 90 else str(v)[:87] + "...") for k, v in params.items() if v not in (None, "")}
        await self.emit({"type": "http", "step": _current_step.get(), "method": "GET", "path": path, "params": shown})
        return await self.inner.get(path, params)


TOOLS: list[Json] = [
    {"name": "resolve_picks",
     "description": "Resolve every name one friend entered into Qloo entities using GET /search. Call once per friend.",
     "parameters": {"type": "object", "properties": {"friend": {"type": "string"}}, "required": ["friend"]}},
    {"name": "search_entity",
     "description": "Look up a single name with GET /search, optionally restricted to a type. Use to retry a name that did not resolve.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"}, "friend": {"type": "string"},
         "type": {"type": "string", "enum": ["urn:entity:artist", "urn:entity:movie", "urn:entity:tv_show", "urn:entity:book", "urn:entity:place", "urn:entity:person"]}},
         "required": ["query", "friend"]}},
    {"name": "compare_friends",
     "description": "GET /v2/analysis/compare between two friends' resolved picks. Returns the taste tags they share with scores.",
     "parameters": {"type": "object", "properties": {"friend_a": {"type": "string"}, "friend_b": {"type": "string"}}, "required": ["friend_a", "friend_b"]}},
    {"name": "find_tags",
     "description": "Search real Qloo tag IDs with GET /v2/tags (for example 'restaurant' to restrict dinner places).",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_recommendations",
     "description": "GET /v2/insights for one entity type using everyone's combined picks as signal.interests.entities. Places are limited to the group's city via filter.location.query. Results include affinity scores and which friends' picks drove each result.",
     "parameters": {"type": "object", "properties": {
         "entity_type": {"type": "string", "enum": ["movie", "tv_show", "artist", "place"]},
         "use_restaurant_tag": {"type": "boolean", "description": "Places only: apply the restaurant tag found with find_tags."}},
         "required": ["entity_type"]}},
    {"name": "finalize_plan",
     "description": "Submit the evening plan. Pick IDs must come from get_recommendations results. Every why must cite the Qloo affinity score and/or shared tags exactly as returned.",
     "parameters": {"type": "object", "properties": {
         "summary": {"type": "string", "description": "Two sentences on what this group has in common, citing shared tags."},
         **{slot: {"type": "object", "properties": {
             "pick_id": {"type": "string"},
             "why": {"type": "string"},
             "alternates": {"type": "array", "items": {"type": "object", "properties": {
                 "id": {"type": "string"}, "why": {"type": "string"}}, "required": ["id", "why"]}}},
             "required": ["pick_id", "why", "alternates"]} for slot in SLOTS}},
         "required": ["summary", *SLOTS.keys()]}},
]

SYSTEM_PROMPT = """You are Common Ground, an agent that plans one evening out for a group of 2-5 friends using the Qloo taste API.

Work through tools, not memory. A good run:
1. resolve_picks for every friend (you may call several tools in one turn).
2. compare_friends for each pair of friends to find shared taste tags.
3. find_tags with "restaurant" to get a real tag ID for dinner places.
4. get_recommendations for movie, artist and place (place with use_restaurant_tag=true when a tag was found). Add tv_show if movie results are thin.
5. finalize_plan: one pick plus exactly 2 alternates for watch (movie or show), soundtrack (artist) and dinner (place).

Rules for finalize_plan:
- Only use IDs returned by get_recommendations. Prefer results with high group_score, shared tags, and drivers from several friends.
- Every why is 1-2 sentences, warm and specific, and MUST cite Qloo signals copied exactly from tool results: the affinity score (two decimals, e.g. 0.93), shared tag names with the friends who share them, and/or the friend pick that drove it. Never invent numbers or facts not in the tool results.
- The summary names the strongest shared tags and who shares them.
"""


class CommonGroundAgent:
    def __init__(self, settings: Settings, qloo: QlooClient, emit: Emit, llm: Gemini | None = None):
        self.settings = settings
        self.emit = emit
        self.qloo = QlooClient(RecordingBackend(qloo.backend, emit), qloo.compare_path)
        self.llm = llm
        self._ids = itertools.count(1)
        self.state: AgentState | None = None

    # ------------------------------------------------------------ helpers
    async def _step(self, tool: str, args: Json, fn: Callable[[], Awaitable[Json]], by: str) -> Json:
        sid = f"s{next(self._ids)}"
        token = _current_step.set(sid)
        t0 = time.perf_counter()
        await self.emit({"type": "step", "id": sid, "tool": tool, "args": args, "status": "running", "by": by})
        try:
            result = await fn()
            ok, summary = True, result.pop("_summary", "done")
        except Exception as exc:  # noqa: BLE001 - surface any tool failure in the trace
            result, ok, summary = {"error": str(exc)}, False, str(exc)[:160]
        finally:
            _current_step.reset(token)
        await self.emit({"type": "step", "id": sid, "tool": tool, "status": "done" if ok else "error",
                         "summary": summary, "ms": round((time.perf_counter() - t0) * 1000), "by": by})
        return result

    # -------------------------------------------------------------- tools
    async def tool_resolve_picks(self, friend: str) -> Json:
        st = self.state
        f = st.friend(friend)
        if not f:
            raise ValueError(f"Unknown friend {friend!r}. Friends: {', '.join(st.names)}")

        async def one(name: str) -> tuple[str, Json | None]:
            results = await self.qloo.search(name, take=5)
            best = best_match(results, name)
            if best and best["type"] == "urn:entity:place" and not in_city(best, st.city):
                # A restaurant name matches branches everywhere; retry scoped to the group's city.
                local = await self.qloo.search(f"{name} {st.city}", types="urn:entity:place", take=5)
                best = next((r for r in local if in_city(r, st.city)), best)
            return name, best

        pairs = await asyncio.gather(*(one(p) for p in f.picks))
        st.resolved[f.name] = [e for _, e in pairs if e]
        st.unresolved[f.name] = [n for n, e in pairs if not e]
        lines = [f"{n} → {e['name']} ({e['type'].split(':')[-1]})" for n, e in pairs if e]
        return {
            "friend": f.name,
            "resolved": [{"input": n, "id": e["id"], "name": e["name"], "type": e["type"]} for n, e in pairs if e],
            "unresolved": st.unresolved[f.name],
            "_summary": f"{f.name}: " + ("; ".join(lines) or "nothing resolved")
                        + (f" · not found: {', '.join(st.unresolved[f.name])}" if st.unresolved[f.name] else ""),
        }

    async def tool_search_entity(self, query: str, friend: str, type: str | None = None) -> Json:
        st = self.state
        f = st.friend(friend)
        if not f:
            raise ValueError(f"Unknown friend {friend!r}")
        results = await self.qloo.search(query, types=type, take=5)
        best = best_match(results, query)
        if best and best["id"] not in {e["id"] for e in st.resolved.setdefault(f.name, [])}:
            st.resolved[f.name].append(best)
            if query in st.unresolved.get(f.name, []):
                st.unresolved[f.name].remove(query)
        return {"results": [{"id": r["id"], "name": r["name"], "type": r["type"]} for r in results],
                "_summary": f"{query} → {best['name'] if best else 'no match'}"}

    async def tool_compare_friends(self, friend_a: str, friend_b: str) -> Json:
        st = self.state
        fa, fb = st.friend(friend_a), st.friend(friend_b)
        if not fa or not fb or fa is fb:
            raise ValueError("compare_friends needs two different known friends")
        ida = [e["id"] for e in st.resolved.get(fa.name, [])]
        idb = [e["id"] for e in st.resolved.get(fb.name, [])]
        if not ida or not idb:
            raise ValueError(f"Resolve picks for {fa.name} and {fb.name} first")
        res = await self.qloo.compare(ida, idb)
        key = tuple(sorted([fa.name, fb.name], key=st.names.index))
        st.pairs[key] = res
        top = res["shared"][:6]
        return {
            "friends": list(key),
            "shared_tags": [{"name": t["name"], "score": t["score"]} for t in top],
            "_summary": f"{key[0]} × {key[1]}: " + (", ".join(f"{t['name']} ({fmt_aff(t['score'])})" for t in top[:4]) or "no shared tags"),
        }

    async def tool_find_tags(self, query: str) -> Json:
        st = self.state
        tags = await self.qloo.find_tags(query, take=10)
        st.tag_lookup_done = True
        if "restaurant" in query.lower():
            exact = [t for t in tags if t["id"].endswith(":place:restaurant")]
            place_tags = exact or [t for t in tags if ":place" in t["id"] and "restaurant" in t["name"].lower()]
            if place_tags:
                st.restaurant_tag = place_tags[0]["id"]
        return {"tags": tags[:8], "restaurant_tag": st.restaurant_tag,
                "_summary": f"{len(tags)} tags for '{query}'" + (f" · using {st.restaurant_tag}" if st.restaurant_tag else "")}

    async def tool_get_recommendations(self, entity_type: str, use_restaurant_tag: bool = True) -> Json:
        st = self.state
        if entity_type not in TYPE_TO_SLOT:
            raise ValueError("entity_type must be movie, tv_show, artist or place")
        ids = st.all_ids()
        if not ids:
            raise ValueError("No resolved picks yet; call resolve_picks first")
        ftype = f"urn:entity:{entity_type}"
        tags = [st.restaurant_tag] if (entity_type == "place" and use_restaurant_tag and st.restaurant_tag) else None
        entities, meta = await self.qloo.insights(ftype, ids, location=st.city if entity_type == "place" else None,
                                                  tags=tags, exclude_ids=ids, take=12)
        if entity_type == "place" and not entities and tags:
            entities, meta = await self.qloo.insights(ftype, ids, location=st.city, exclude_ids=ids, take=12)
        if meta.get("locality"):
            st.locality = meta["locality"]
        # Never recommend something a friend already named (search may have resolved it as another type).
        own = {_norm(e["name"]) for v in st.resolved.values() for e in v} | {_norm(p) for f in st.friends for p in f.picks}
        entities = [e for e in entities if _norm(e["name"]) not in own]
        if entity_type == "place":
            entities = [e for e in entities if _is_dinner_spot(e)] or entities
        slot = TYPE_TO_SLOT[entity_type]
        known = {c["id"] for c in st.candidates[slot]}
        st.candidates[slot].extend(e for e in entities if e["id"] not in known)
        ranked = rank(entities, st.overlap(), st.pick_owner(), len(st.friends))
        compact = [{
            "id": c["id"], "name": c["name"], "affinity": c["affinity"], "group_score": c["group_score"],
            "shared_tags": [{"name": t["name"], "score": t["score"], "friends": t["friends"]} for t in c["signals"]["shared_tags"]],
            "drivers": c["signals"]["drivers"][:3], "tags": [t["name"] for t in c["tags"][:5]],
            "description": c.get("description"),
        } for c in ranked[:8]]
        where = f" in {st.locality or st.city}" if entity_type == "place" else ""
        return {"entity_type": entity_type, "locality": st.locality, "results": compact,
                "_summary": f"{len(entities)} {entity_type.replace('_', ' ')} results{where}"
                            + (f" · top: {compact[0]['name']} ({fmt_aff(compact[0]['affinity'])})" if compact else "")}

    async def run_tool(self, name: str, args: Json, by: str) -> Json:
        fn = {
            "resolve_picks": self.tool_resolve_picks,
            "search_entity": self.tool_search_entity,
            "compare_friends": self.tool_compare_friends,
            "find_tags": self.tool_find_tags,
            "get_recommendations": self.tool_get_recommendations,
        }.get(name)
        if not fn:
            return {"error": f"unknown tool {name}"}
        return await self._step(name, args, lambda: fn(**args), by)

    # ------------------------------------------------------- run / plans
    async def run(self, friends: list[Friend], city: str) -> Json:
        self.state = AgentState(friends=friends, city=city)
        await self.emit({"type": "start", "mode": "mock" if self.qloo.is_mock else "live",
                         "planner": "gemini" if self.llm else "scripted", "friends": self.state.names, "city": city})
        choice = None
        if self.llm:
            try:
                choice = await asyncio.wait_for(self._gemini_loop(), timeout=self.settings.llm_timeout)
            except asyncio.TimeoutError:
                await self.emit({"type": "note", "text": f"Gemini took longer than {self.settings.llm_timeout:.0f}s, finishing with the scripted planner"})
            except LLMUnavailable as exc:
                await self.emit({"type": "note", "text": f"Gemini unavailable, finishing with the scripted planner ({str(exc)[:120]})"})
            except Exception as exc:  # noqa: BLE001 - any LLM-side failure falls back, never breaks the plan
                await self.emit({"type": "note", "text": f"Gemini error, finishing with the scripted planner ({type(exc).__name__})"})
        await self._ensure_required()
        plan = self.build_plan(choice)
        await self.emit({"type": "plan", "plan": plan})
        return plan

    async def _ensure_required(self) -> None:
        """Scripted planner. Also fills any step the LLM skipped."""
        st = self.state
        todo = [self.run_tool("resolve_picks", {"friend": f.name}, "scripted") for f in st.friends if f.name not in st.resolved]
        if todo:
            await asyncio.gather(*todo)
        jobs = []
        if not st.tag_lookup_done:
            jobs.append(self.run_tool("find_tags", {"query": "restaurant"}, "scripted"))
        have = [f.name for f in st.friends if st.resolved.get(f.name)]
        for a, b in itertools.combinations(have, 2):
            if (a, b) not in st.pairs and len(st.pairs) + len(jobs) < 12:
                jobs.append(self.run_tool("compare_friends", {"friend_a": a, "friend_b": b}, "scripted"))
        if jobs:
            await asyncio.gather(*jobs)
        recs = [self.run_tool("get_recommendations", {"entity_type": t}, "scripted")
                for t, slot in (("movie", "watch"), ("artist", "soundtrack"), ("place", "dinner")) if not st.candidates[slot]]
        if recs:
            await asyncio.gather(*recs)
        if len(st.candidates["watch"]) < 3:
            await self.run_tool("get_recommendations", {"entity_type": "tv_show"}, "scripted")

    def _missing(self) -> list[str]:
        st = self.state
        miss = [f"resolve_picks({f.name})" for f in st.friends if f.name not in st.resolved]
        if not st.pairs and len([f for f in st.friends if st.resolved.get(f.name)]) >= 2:
            miss.append("compare_friends")
        miss += [f"get_recommendations({t})" for t, s in (("movie", "watch"), ("artist", "soundtrack"), ("place", "dinner")) if not st.candidates[s]]
        return miss

    async def _gemini_loop(self) -> Json | None:
        st = self.state
        brief = {"city": st.city, "friends": [{"name": f.name, "loves": f.picks} for f in st.friends]}
        contents: list[Any] = [Gemini.user("Plan our evening.\n" + json.dumps(brief, ensure_ascii=False))]
        nudged = False
        for _ in range(self.settings.max_agent_steps):
            resp = await self.llm.generate(contents, SYSTEM_PROMPT, TOOLS)
            calls = list(resp.function_calls or [])
            text = (resp.text or "").strip() if not calls else ""
            if resp.candidates and resp.candidates[0].content:
                contents.append(resp.candidates[0].content)
            if not calls:
                if text:
                    await self.emit({"type": "thought", "text": text[:400], "model": self.llm.active_model})
                if nudged:
                    return None
                nudged = True
                contents.append(Gemini.user("Continue with tool calls and finish with finalize_plan."))
                continue
            await self.emit({"type": "thought", "model": self.llm.active_model,
                             "text": "Planning: " + ", ".join(f"{c.name}({', '.join(f'{k}={v}' for k, v in (c.args or {}).items() if k not in SLOTS and k != 'summary')})" for c in calls)})
            final = next((c for c in calls if c.name == "finalize_plan"), None)
            others = [c for c in calls if c.name != "finalize_plan"]
            results = await asyncio.gather(*(self.run_tool(c.name, dict(c.args or {}), "gemini") for c in others))
            responses = [(c.name, r) for c, r in zip(others, results)]
            if final:
                missing = self._missing()
                if missing and not others:
                    responses.append(("finalize_plan", {"error": "Missing data, call these first: " + ", ".join(missing)}))
                elif not missing:
                    await self.emit({"type": "step", "id": f"s{next(self._ids)}", "tool": "finalize_plan", "args": {},
                                     "status": "done", "summary": "Gemini wrote the plan and its explanations", "ms": 0, "by": "gemini"})
                    return dict(final.args or {})
                else:
                    responses.append(("finalize_plan", {"error": "Wait for these results, then call finalize_plan again."}))
            contents.append(Gemini.function_responses(responses))
        return None

    def build_plan(self, choice: Json | None = None) -> Json:
        st = self.state
        overlap = st.overlap()
        owner = st.pick_owner()
        slots_out: Json = {}
        sources = set()
        for slot, meta in SLOTS.items():
            ranked = rank(st.candidates[slot], overlap, owner, len(st.friends))
            by_id = {c["id"]: c for c in ranked}
            chosen: list[tuple[Json, str | None]] = []
            c_slot = (choice or {}).get(slot) if isinstance(choice, dict) else None
            if isinstance(c_slot, dict) and c_slot.get("pick_id") in by_id:
                chosen.append((by_id[c_slot["pick_id"]], c_slot.get("why")))
                for alt in c_slot.get("alternates") or []:
                    if isinstance(alt, dict) and alt.get("id") in by_id and all(alt["id"] != c["id"] for c, _ in chosen):
                        chosen.append((by_id[alt["id"]], alt.get("why")))
            for c in ranked:
                if len(chosen) >= 3:
                    break
                if all(c["id"] != x["id"] for x, _ in chosen):
                    chosen.append((c, None))
            items = []
            for c, why in chosen[:3]:
                grounded = bool(why) and why_is_grounded(why, c)
                src = "gemini" if grounded else "template"
                sources.add(src)
                items.append({
                    "id": c["id"], "name": c["name"], "type": c["type"], "description": c.get("description"),
                    "image": c.get("image"), "address": c.get("address"), "year": c.get("year"),
                    "price_level": c.get("price_level"), "affinity": c.get("affinity"),
                    "group_score": c["group_score"], "signals": c["signals"],
                    "why": why if grounded else template_why(slot, c), "why_source": src,
                })
            slots_out[slot] = {"label": meta["label"], "pick": items[0] if items else None, "alternates": items[1:]}
        summary = (choice or {}).get("summary") if isinstance(choice, dict) else None
        if not summary or not any(t["name"].lower() in summary.lower() for t in overlap["tags"][:8]):
            summary = self._template_summary(overlap)
        return {
            "city": st.city, "locality": st.locality, "friends": st.names,
            "resolved": {k: [{"name": e["name"], "type": e["type"]} for e in v] for k, v in st.resolved.items()},
            "unresolved": {k: v for k, v in st.unresolved.items() if v},
            "summary": summary, "slots": slots_out, "overlap": overlap,
            "mode": "mock" if self.qloo.is_mock else "live",
            "planner": "gemini" if choice else "scripted",
            "model": self.llm.active_model if (self.llm and choice) else None,
            "why_sources": sorted(sources),
        }

    @staticmethod
    def _template_summary(overlap: Json) -> str:
        tags = overlap.get("tags") or []
        if not tags:
            return "Qloo found few shared tags between these picks, so the plan leans on the combined-taste affinity scores."
        top = tags[0]
        rest = ", ".join(t["name"] for t in tags[1:3])
        return (f"The strongest common ground is \"{top['name']}\", shared by {', '.join(top['friends'])}"
                f" (compare score {fmt_aff(top['score'])})." + (f" Other shared threads: {rest}." if rest else ""))


_NOT_DINNER = ("place:hotel", "shopping_mall", "place:airport", "serviced_accommodation", "place:resort", "place:lodging", "chocolate_shop", "donut_shop")


def _is_dinner_spot(e: dict) -> bool:
    """Qloo's restaurant tag also matches hotels, malls and dessert counters; keep real dinner places."""
    ids = " ".join(i or "" for i in (e.get("tag_ids") or [t.get("id") for t in e.get("tags", [])]))
    name = (e.get("name") or "").lower()
    if any(k in ids for k in _NOT_DINNER):
        return False
    return not any(w in name for w in (" hotel", "mall,", " mall", "airport"))
