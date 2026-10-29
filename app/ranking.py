"""Group scoring, the overlap map, and evidence-backed explanations.

Everything here works only from what Qloo returned: insight affinity scores,
explainability contributions, and shared tags from the compare endpoint.
"""
from __future__ import annotations

import re
from typing import Any

Json = dict[str, Any]


def build_overlap_map(friends: list[str], pair_results: list[Json]) -> Json:
    """pair_results: [{a, b, shared: [{id,name,score}], ...}] -> aggregated map."""
    agg: dict[str, Json] = {}
    pairs = []
    for pr in pair_results:
        shared = pr.get("shared") or []
        scores = [t["score"] for t in shared if t.get("score") is not None]
        pairs.append({
            "a": pr["a"], "b": pr["b"],
            "shared": shared[:8],
            "strength": round(sum(scores[:5]) / len(scores[:5]), 3) if scores else 0.0,
        })
        for t in shared:
            # Key by name: Qloo can return the same label under two tag IDs (e.g. two "Drama" tags).
            key = t["name"].strip().lower()
            node = agg.setdefault(key, {"id": t.get("id"), "name": t["name"], "scores": [], "friends": set(), "pairs": 0})
            if t.get("score") is not None:
                node["scores"].append(t["score"])
            node["friends"].update([pr["a"], pr["b"]])
            node["pairs"] += 1
    tags = []
    for node in agg.values():
        avg = round(sum(node["scores"]) / len(node["scores"]), 3) if node["scores"] else None
        tags.append({"id": node["id"], "name": node["name"], "score": avg, "pairs": node["pairs"],
                     "friends": sorted(node["friends"], key=friends.index)})
    tags.sort(key=lambda t: (-len(t["friends"]), -(t["score"] or 0)))
    return {"friends": friends, "pairs": pairs, "tags": tags[:24]}


def _tag_index(overlap: Json) -> dict[str, Json]:
    idx: dict[str, Json] = {}
    for t in overlap.get("tags", []):
        if t.get("id"):
            idx[t["id"].lower()] = t
        idx[t["name"].lower()] = t
    return idx


def score_candidate(c: Json, overlap: Json, pick_owner: dict[str, tuple[str, str]], n_friends: int) -> Json:
    """Return the candidate with a `signals` block and a `group_score`."""
    idx = _tag_index(overlap)
    matched, seen = [], set()
    for t in c.get("tags") or []:
        hit = idx.get((t.get("id") or "").lower()) or idx.get(t["name"].lower())
        if hit and hit["name"] not in seen:
            seen.add(hit["name"])
            matched.append({"name": hit["name"], "score": hit.get("score"), "friends": hit["friends"]})
    matched.sort(key=lambda t: (-len(t["friends"]), -(t["score"] or 0)))
    drivers = []
    for ex in c.get("explain") or []:
        owner = pick_owner.get(ex["entity_id"])
        if owner:
            drivers.append({"friend": owner[0], "pick": owner[1], "score": ex["score"]})
    covered = {d["friend"] for d in drivers}
    affinity = c.get("affinity") if c.get("affinity") is not None else 0.5
    coverage = len(covered) / n_friends if n_friends else 0
    group_score = round(affinity * 0.7 + min(len(matched), 3) * 0.06 + coverage * 0.12, 4)
    out = dict(c)
    out["signals"] = {
        "affinity": c.get("affinity"),
        "shared_tags": matched[:4],
        "drivers": drivers[:4],
        "friends_covered": sorted(covered),
        "group_score": group_score,
    }
    out["group_score"] = group_score
    return out


def rank(candidates: list[Json], overlap: Json, pick_owner: dict, n_friends: int) -> list[Json]:
    scored = [score_candidate(c, overlap, pick_owner, n_friends) for c in candidates]
    scored.sort(key=lambda c: -c["group_score"])
    return scored


def fmt_aff(v: float | None) -> str:
    return f"{v:.2f}" if isinstance(v, (int, float)) else "n/a"


def template_why(slot: str, c: Json) -> str:
    s = c.get("signals") or {}
    parts = [f"Qloo gives {c['name']} an affinity of {fmt_aff(s.get('affinity'))} against the group's combined picks"]
    tags = s.get("shared_tags") or []
    if tags:
        t = tags[0]
        fr = t["friends"]
        who = fr[0] if len(fr) == 1 else ", ".join(fr[:-1]) + " & " + fr[-1]
        extra = f" (plus {', '.join(x['name'] for x in tags[1:3])})" if len(tags) > 1 else ""
        parts.append(f"it carries the shared tag \"{t['name']}\" ({who}, compare score {fmt_aff(t.get('score'))}){extra}")
    drivers = s.get("drivers") or []
    if drivers:
        d = drivers[0]
        parts.append(f"strongest pull comes from {d['friend']}'s pick {d['pick']} ({fmt_aff(d['score'])})")
    return "; ".join(parts) + "."


_NUM = re.compile(r"\b0?\.\d{2}\b|\b1\.00\b")


def why_is_grounded(why: str, c: Json) -> bool:
    """A 'why' must cite at least one real Qloo signal: the affinity score or a shared tag,
    and must not quote numbers that are not in the evidence."""
    if not why or len(why) < 20:
        return False
    s = c.get("signals") or {}
    allowed = set()
    if isinstance(s.get("affinity"), (int, float)):
        allowed.add(fmt_aff(s["affinity"]))
    for t in s.get("shared_tags") or []:
        if t.get("score") is not None:
            allowed.add(fmt_aff(t["score"]))
    for d in s.get("drivers") or []:
        allowed.add(fmt_aff(d["score"]))
    cited_numbers = {m.lstrip("0") if m.startswith("0") else m for m in _NUM.findall(why)}
    allowed_norm = {a.lstrip("0") if a.startswith("0") else a for a in allowed}
    if cited_numbers - allowed_norm:
        return False
    low = why.lower()
    cites_tag = any(t["name"].lower() in low for t in s.get("shared_tags") or [])
    cites_aff = bool(cited_numbers & allowed_norm)
    return cites_tag or cites_aff
