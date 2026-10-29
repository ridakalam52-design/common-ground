"""Mock Qloo backend. Answers the same paths and parameters as the live API with
responses shaped like Qloo's, computed from the hand-written demo catalog.

Switches on automatically when QLOO_API_KEY is missing. Scores are synthetic.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
from typing import Any

from .mock_data import CATALOG, CITY_ALIASES, CITY_DISAMBIGUATION, TAGS, mock_id

Json = dict[str, Any]


def _jitter(*parts: str) -> float:
    h = hashlib.sha1("|".join(parts).encode()).hexdigest()
    return int(h[:6], 16) / 0xFFFFFF  # 0..1, deterministic


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


class MockQloo:
    name = "mock"

    def __init__(self, latency: float = 0.05):
        self.latency = latency
        self.by_id = {e["entity_id"]: e for e in CATALOG}
        self.calls: list[tuple[str, Json]] = []

    async def get(self, path: str, params: dict[str, Any]) -> Json:
        self.calls.append((path, dict(params)))
        if self.latency:
            await asyncio.sleep(self.latency)
        if path == "/search":
            return self._search(params)
        if path == "/v2/tags":
            return self._tags(params)
        if path == "/v2/insights":
            return self._insights(params)
        if path.endswith("/compare"):
            return self._compare(params)
        return {"success": False, "error": f"mock has no route {path}"}

    # ------------------------------------------------------------- search
    def _search(self, p: Json) -> Json:
        q = _norm(str(p.get("query", "")))
        types = [t for t in str(p.get("types") or "").split(",") if t]
        take = int(p.get("take") or 3)
        scored = []
        for e in CATALOG:
            if types and e["subtype"] not in types:
                continue
            n = _norm(e["name"])
            if not q:
                continue
            if n == q:
                s = 1.0
            elif n.startswith(q) or q.startswith(n):
                s = 0.8
            elif q in n:
                s = 0.6
            else:
                continue
            scored.append((s + e["popularity"] * 0.01, e))
        scored.sort(key=lambda x: -x[0])
        results = [self._public(e) for _, e in scored[:take]]
        if not results and q:
            # Unknown name: invent a plausible stand-in so demos never dead-end.
            subtype = types[0] if types else "urn:entity:artist"
            name = str(p.get("query")).strip().title()
            results = [{
                "entity_id": mock_id(name), "name": name, "subtype": subtype, "types": [subtype],
                "popularity": 0.5, "tags": [], "properties": {},
            }]
        return {"success": True, "results": results, "duration": 0.02}

    # --------------------------------------------------------------- tags
    def _tags(self, p: Json) -> Json:
        q = str(p.get("filter.query", "")).lower()
        rows = [{"id": tid, "name": name, "type": tid.rsplit(":", 1)[0]}
                for tid, name in TAGS.values() if q and q in name.lower()]
        rows.sort(key=lambda t: len(t["name"]))
        return {"success": True, "results": {"tags": rows[: int(p.get("take") or 10)]}}

    # ----------------------------------------------------------- insights
    def _signal_entities(self, value: Any) -> list[Json]:
        ids = [i for i in str(value or "").split(",") if i]
        return [self.by_id[i] for i in ids if i in self.by_id]

    def _insights(self, p: Json) -> Json:
        ftype = p.get("filter.type")
        signals = self._signal_entities(p.get("signal.interests.entities"))
        exclude = set(str(p.get("filter.exclude.entities") or "").split(","))
        filter_tags = [t for t in str(p.get("filter.tags") or "").split(",") if t]
        take = int(p.get("take") or 20)
        resp: Json = {"success": True, "query": {}, "duration": 0.04}
        candidates = [e for e in CATALOG if e["subtype"] == ftype]
        if ftype == "urn:entity:place":
            loc = str(p.get("filter.location.query") or "").strip().lower()
            city = CITY_ALIASES.get(loc)
            if loc and not city:
                return {"success": False, "error": {"code": 400, "message": f"No localities found for '{loc}'"}}
            if city:
                candidates = [e for e in candidates if e.get("_city") == city]
                # Live API returns query.localities.filter as a list of matched localities.
                resp["query"]["localities"] = {"filter": [{
                    "entity_id": mock_id("locality " + city), "name": city.title(),
                    "subtype": "urn:entity:locality", "disambiguation": CITY_DISAMBIGUATION[city]}]}
        if filter_tags:
            # restaurant-genre filter keeps cafes/bars that serve food in the demo set
            candidates = [e for e in candidates
                          if any(t["id"].startswith(ft) or ft == TAGS["restaurant"][0] for ft in filter_tags for t in e["tags"])]
        signal_ids = {s["entity_id"] for s in signals}
        signal_tags: dict[str, list[str]] = {}
        for s in signals:
            for t in s["tags"]:
                signal_tags.setdefault(t["id"], []).append(s["entity_id"])
        rows = []
        for e in candidates:
            if e["entity_id"] in signal_ids or e["entity_id"] in exclude:
                continue
            matches = [t["id"] for t in e["tags"] if t["id"] in signal_tags]
            contributors: dict[str, float] = {}
            for tid in matches:
                for sid in signal_tags[tid]:
                    contributors[sid] = contributors.get(sid, 0) + 1
            raw = len(matches) * 0.11 + len(contributors) * 0.05 + e["popularity"] * 0.25 + _jitter(e["name"], ftype or "") * 0.06
            rows.append((raw, e, contributors))
        rows.sort(key=lambda r: -r[0])
        top = rows[:take]
        best = top[0][0] if top else 1
        entities = []
        for raw, e, contributors in top:
            out = self._public(e)
            affinity = round(min(0.97, 0.52 + 0.42 * (raw / best) - _jitter(e["name"], "aff") * 0.03), 3)
            total = sum(contributors.values()) or 1
            out["query"] = {
                "affinity": affinity,
                "explainability": {"signal.interests.entities": [
                    {"entity_id": sid, "score": round(c / total, 3)} for sid, c in
                    sorted(contributors.items(), key=lambda kv: -kv[1])]},
            }
            entities.append(out)
        resp["results"] = {"entities": entities}
        return resp

    # ------------------------------------------------------------ compare
    def _compare(self, p: Json) -> Json:
        a = self._signal_entities(p.get("a.signal.interests.entities"))
        b = self._signal_entities(p.get("b.signal.interests.entities"))
        take = int(p.get("take") or 20)

        def tagmap(group: list[Json]) -> dict[str, tuple[str, int]]:
            m: dict[str, tuple[str, int]] = {}
            for e in group:
                for t in e["tags"]:
                    name, n = m.get(t["id"], (t["name"], 0))
                    m[t["id"]] = (name, n + 1)
            return m

        ta, tb = tagmap(a), tagmap(b)
        shared = []
        for tid in set(ta) & set(tb):
            na, nb = ta[tid][1], tb[tid][1]
            score = round(min(0.99, 0.45 + 0.12 * (na + nb) + _jitter(tid) * 0.08), 3)
            shared.append({"tag_id": tid, "name": ta[tid][0], "subtype": tid.rsplit(":", 1)[0], "query": {"score": score}})
        shared.sort(key=lambda t: -t["query"]["score"])

        def only(src: dict, other: dict) -> list[Json]:
            return [{"tag_id": tid, "name": v[0], "subtype": tid.rsplit(":", 1)[0],
                     "query": {"score": round(0.4 + 0.1 * v[1], 3)}} for tid, v in src.items() if tid not in other][:take]

        return {"success": True, "results": {"tags": shared[:take], "a": only(ta, tb), "b": only(tb, ta)}}

    @staticmethod
    def _public(e: Json) -> Json:
        out = copy.deepcopy(e)
        out.pop("_city", None)
        return out
