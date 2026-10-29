"""Qloo API client (hackathon environment) and response parsers.

Every call is a GET with query parameters and the key in the X-Api-Key header,
against https://hackathon.api.qloo.com. Only documented parameters are used,
because Qloo silently ignores unknown ones.

Endpoints used:
  GET /search                 query, types, take
  GET /v2/tags                filter.query, take
  GET /v2/insights            filter.type, signal.interests.entities, filter.location.query,
                              filter.tags, feature.explainability, take
  GET /v2/analysis/compare    a.signal.interests.entities, b.signal.interests.entities, take

Responses are cached in process memory only (Qloo allows private server-side
caching) and are never written to disk or committed.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

import httpx

SUPPORTED_INSIGHT_TYPES = {
    "urn:entity:artist", "urn:entity:book", "urn:entity:brand", "urn:entity:destination",
    "urn:entity:movie", "urn:entity:person", "urn:entity:place", "urn:entity:podcast",
    "urn:entity:tv_show", "urn:entity:video_game",
}
LOCATION_TYPES = {"urn:entity:place", "urn:entity:destination"}

Json = dict[str, Any]


class QlooError(RuntimeError):
    pass


class QlooBackend(Protocol):
    name: str

    async def get(self, path: str, params: dict[str, Any]) -> Json: ...


class LiveQloo:
    """Thin async HTTP backend for the real API."""

    name = "qloo"

    def __init__(self, api_key: str, base_url: str, timeout: float = 20.0):
        self._key = api_key
        self._base = base_url
        self._client = httpx.AsyncClient(timeout=timeout)
        self._cache: dict[str, Json] = {}

    async def get(self, path: str, params: dict[str, Any]) -> Json:
        clean = {k: v for k, v in params.items() if v not in (None, "", [])}
        cache_key = path + "?" + json.dumps(clean, sort_keys=True)
        if cache_key in self._cache:
            return self._cache[cache_key]
        headers = {"X-Api-Key": self._key, "Accept": "application/json"}
        resp = None
        for attempt in range(3):
            resp = await self._client.get(self._base + path, params=clean, headers=headers)
            if resp.status_code == 429 or resp.status_code >= 500:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            break
        assert resp is not None
        if resp.status_code >= 400:
            raise QlooError(f"Qloo {resp.status_code} on {path}: {resp.text[:200]}")
        data = resp.json()
        self._cache[cache_key] = data
        return data


class QlooClient:
    """High-level calls the agent's tools use. Works with LiveQloo or MockQloo."""

    def __init__(self, backend: QlooBackend, compare_path: str = "/v2/analysis/compare"):
        self.backend = backend
        self.compare_path = compare_path

    @property
    def is_mock(self) -> bool:
        return self.backend.name == "mock"

    async def search(self, query: str, types: str | None = None, take: int = 3) -> list[Json]:
        params = {"query": query, "types": types, "take": take}
        data = await self.backend.get("/search", params)
        return [parse_entity(r) for r in (data.get("results") or [])]

    async def find_tags(self, query: str, take: int = 10) -> list[Json]:
        data = await self.backend.get("/v2/tags", {"filter.query": query, "take": take})
        results = data.get("results") or {}
        rows = results.get("tags") if isinstance(results, dict) else results
        out = []
        for t in rows or []:
            tid = t.get("id") or t.get("tag_id")
            if tid:
                out.append({"id": tid, "name": t.get("name") or tid, "type": t.get("type") or t.get("subtype")})
        return out

    async def insights(
        self,
        filter_type: str,
        entity_ids: list[str],
        location: str | None = None,
        tags: list[str] | None = None,
        exclude_ids: list[str] | None = None,
        take: int = 10,
    ) -> tuple[list[Json], Json]:
        if filter_type not in SUPPORTED_INSIGHT_TYPES:
            raise QlooError(f"Unsupported filter.type {filter_type}")
        params: dict[str, Any] = {
            "filter.type": filter_type,
            "signal.interests.entities": ",".join(entity_ids),
            "feature.explainability": "true",
            "take": take,
        }
        if location and filter_type in LOCATION_TYPES:
            params["filter.location.query"] = location
        if tags:
            params["filter.tags"] = ",".join(tags)
        if exclude_ids:
            params["filter.exclude.entities"] = ",".join(exclude_ids)
        data = await self.backend.get("/v2/insights", params)
        results = data.get("results") or {}
        entities = [parse_entity(r) for r in (results.get("entities") or [])]
        meta = {"locality": matched_locality(data)}
        return entities, meta

    async def compare(self, a_ids: list[str], b_ids: list[str], take: int = 20) -> Json:
        data = await self.backend.get(self.compare_path, {
            "a.signal.interests.entities": ",".join(a_ids),
            "b.signal.interests.entities": ",".join(b_ids),
            "take": take,
        })
        return parse_compare(data)


# ---------------------------------------------------------------- parsers

def _english(rows: Any) -> str | None:
    if not isinstance(rows, list) or not rows:
        return None
    for r in rows:
        if isinstance(r, dict) and "en" in (r.get("languages") or []):
            return r.get("value")
    first = rows[0]
    return first.get("value") if isinstance(first, dict) else None


def parse_explainability(q: Json) -> list[Json]:
    """Pull (entity_id, score) pairs out of query.explainability, whatever its nesting.

    The docs describe per-result explainability with normalized 0-1 scores for the
    input entities but publish no schema, so this walks the structure defensively.
    """
    found: dict[str, float] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            eid = node.get("entity_id") or node.get("id")
            score = node.get("score", node.get("weight"))
            if isinstance(eid, str) and isinstance(score, (int, float)):
                found[eid] = max(found.get(eid, 0.0), float(score))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(q.get("explainability") if isinstance(q, dict) else None)
    return [{"entity_id": k, "score": round(v, 3)} for k, v in sorted(found.items(), key=lambda kv: -kv[1])]


def parse_entity(r: Json) -> Json:
    props = r.get("properties") or {}
    q = r.get("query") or {}
    tags = []
    for t in (r.get("tags") or [])[:12]:
        name = t.get("name")
        if name:
            tags.append({"id": t.get("id") or t.get("tag_id"), "name": name, "type": t.get("type")})
    types = r.get("types") or []
    desc = r.get("disambiguation") if r.get("disambiguation") not in (None, r.get("name")) else None
    desc = desc or _english(props.get("short_descriptions")) or props.get("description")
    image = (props.get("image") or {}).get("url") if isinstance(props.get("image"), dict) else None
    return {
        "id": r.get("entity_id") or r.get("id") or "",
        "name": r.get("name") or "Unknown",
        "type": r.get("subtype") or (types[0] if types else r.get("type") or ""),
        "affinity": q.get("affinity") if isinstance(q.get("affinity"), (int, float)) else None,
        "popularity": r.get("popularity") if isinstance(r.get("popularity"), (int, float)) else None,
        "tags": tags,
        "description": (desc or "")[:180] or None,
        "image": image,
        "address": props.get("address"),
        "year": props.get("release_year"),
        "price_level": props.get("price_level"),
        "business_rating": props.get("business_rating"),
        "explain": parse_explainability(q),
    }


def parse_compare(data: Json) -> Json:
    """results.tags = shared tags (sorted by query.score); results.a / results.b = one-sided."""
    results = data.get("results") if isinstance(data.get("results"), dict) else data

    def rows(key: str) -> list[Json]:
        out = []
        for t in (results.get(key) or []):
            if not isinstance(t, dict):
                continue
            q = t.get("query") or {}
            score = q.get("score", q.get("affinity", t.get("score")))
            name = t.get("name")
            if name:
                out.append({
                    "id": t.get("tag_id") or t.get("id"),
                    "name": name,
                    "type": t.get("subtype") or t.get("type"),
                    "score": round(float(score), 3) if isinstance(score, (int, float)) else None,
                })
        return out

    return {"shared": rows("tags"), "only_a": rows("a"), "only_b": rows("b")}


def matched_locality(data: Json) -> str | None:
    """query.localities.filter is a list of matched locality entities in live responses."""
    q = data.get("query") or {}
    loc = q.get("localities") or q.get("locality") or {}
    for key in ("filter", "signal"):
        node = loc.get(key) if isinstance(loc, dict) else None
        if isinstance(node, list):
            node = next((n for n in node if isinstance(n, dict)), None)
        if isinstance(node, dict):
            return node.get("disambiguation") or node.get("name")
    return None


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


# When /search returns the same name as several types, prefer the one Qloo has
# taste data for in our slots. Live search often lists a musician as
# urn:entity:person first and urn:entity:artist second.
TYPE_PREFERENCE = ["urn:entity:artist", "urn:entity:movie", "urn:entity:tv_show", "urn:entity:place",
                   "urn:entity:book", "urn:entity:podcast", "urn:entity:video_game", "urn:entity:brand",
                   "urn:entity:destination", "urn:entity:person"]


def best_match(results: list[Json], query: str) -> Json | None:
    usable = [r for r in results if r.get("type") in SUPPORTED_INSIGHT_TYPES]
    if not usable:
        return None
    q = _norm(query)
    exact = [r for r in usable if _norm(r["name"]) == q]
    pool = exact or usable
    top = pool[0]
    if top["type"] == "urn:entity:person":
        same = [r for r in pool if _norm(r["name"]) == _norm(top["name"]) and r["type"] != "urn:entity:person"]
        if same:
            return min(same, key=lambda r: TYPE_PREFERENCE.index(r["type"]))
    return top


def in_city(entity: Json, city: str) -> bool:
    """True when a place's address or disambiguation mentions the city (e.g. 'Delhi' for 'New Delhi')."""
    text = f"{entity.get('address') or ''} {entity.get('description') or ''}".lower()
    words = [w for w in city.lower().replace(",", " ").split() if len(w) > 3 and w not in {"city", "new"}]
    return city.lower() in text or (bool(words) and any(w in text for w in words))
