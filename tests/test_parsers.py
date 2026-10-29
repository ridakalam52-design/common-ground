"""Parser tests against hand-written payloads shaped like live Qloo responses.

The payloads below are invented (fake IDs and names); no real Qloo data is stored.
"""
import asyncio

from app.qloo import (QlooClient, best_match, in_city, matched_locality, parse_compare,
                      parse_entity, parse_explainability)

INSIGHT_ROW = {
    "name": "Film One", "entity_id": "E-FILM-1", "type": "urn:entity", "subtype": "urn:entity:movie",
    "popularity": 0.9,
    "properties": {"release_year": 2019, "short_descriptions": [{"value": "Un film", "languages": ["fr"]},
                                                               {"value": "A film", "languages": ["en"]}],
                   "image": {"url": "https://example.com/a.jpg"}},
    "tags": [{"id": "urn:tag:genre:media:drama", "name": "Drama", "type": "urn:tag:genre:media"}],
    "query": {"affinity": 0.944, "measurements": {"audience_growth": 0},
              "explainability": {"signal.interests.entities": [
                  {"entity_id": "SIG-A", "score": 0.35}, {"entity_id": "SIG-B", "score": 0.31}]}},
}

SEARCH_ROWS = [
    {"name": "Singer X", "entity_id": "P-1", "types": ["urn:entity:person"], "properties": {}},
    {"name": "Singer X", "entity_id": "A-1", "types": ["urn:entity:artist"], "properties": {}},
    {"name": "Singer X Lane", "entity_id": "L-1", "types": ["urn:entity:locality"], "properties": {}},
]


def test_parse_insight_entity():
    e = parse_entity(INSIGHT_ROW)
    assert e["id"] == "E-FILM-1" and e["type"] == "urn:entity:movie"
    assert abs(e["affinity"] - 0.944) < 1e-9
    assert e["year"] == 2019 and e["image"] == "https://example.com/a.jpg"
    assert e["description"] == "A film"
    assert e["tags"][0]["name"] == "Drama"
    assert e["explain"][0] == {"entity_id": "SIG-A", "score": 0.35}


def test_parse_search_entity_uses_types_list():
    e = parse_entity(SEARCH_ROWS[1])
    assert e["type"] == "urn:entity:artist" and e["affinity"] is None


def test_explainability_handles_missing():
    assert parse_explainability({}) == []
    assert parse_explainability({"explainability": None}) == []


def test_parse_compare_shared_and_one_sided():
    data = {"duration": 50, "results": {
        "tags": [{"tag_id": "urn:tag:genre:media:drama", "name": "Drama", "subtype": "urn:tag:genre:media",
                  "query": {"score": 0.731, "a.signal.interests.entities": [], "b.signal.interests.entities": []}}],
        "a": [{"tag_id": "urn:tag:x", "name": "Only A", "subtype": "urn:tag:x", "query": {"count": "2"}}],
        "b": [{"tag_id": "urn:tag:y", "name": "Only B", "query": {"count": "1"}}],
        "matchEntities": []}}
    out = parse_compare(data)
    assert out["shared"] == [{"id": "urn:tag:genre:media:drama", "name": "Drama", "type": "urn:tag:genre:media", "score": 0.731}]
    assert out["only_a"][0]["name"] == "Only A" and out["only_a"][0]["score"] is None
    assert out["only_b"][0]["name"] == "Only B"


def test_matched_locality_list_and_dict():
    live = {"query": {"localities": {"filter": [{"name": "New Delhi", "disambiguation": "New Delhi, Delhi, India"}]}}}
    assert matched_locality(live) == "New Delhi, Delhi, India"
    assert matched_locality({"query": {"localities": {"filter": {"name": "Pune"}}}}) == "Pune"
    assert matched_locality({}) is None


def test_best_match_prefers_artist_over_person():
    rows = [parse_entity(r) for r in SEARCH_ROWS]
    assert best_match(rows, "Singer X")["id"] == "A-1"
    assert best_match([parse_entity(SEARCH_ROWS[2])], "x") is None  # locality is not usable


def test_in_city():
    assert in_city({"address": "12 Some Road, New Delhi, Delhi 110001 India"}, "New Delhi")
    assert in_city({"address": "Green Park, Delhi 110016"}, "New Delhi")
    assert not in_city({"address": "Sector 7, Chandigarh 160019 India"}, "New Delhi")


class FakeBackend:
    name = "fake"

    def __init__(self, payload):
        self.payload, self.calls = payload, []

    async def get(self, path, params):
        self.calls.append((path, params))
        return self.payload


def test_find_tags_parses_results_tags():
    be = FakeBackend({"success": True, "results": {"tags": [
        {"id": "urn:tag:genre:place:restaurant", "name": "Restaurant", "type": "urn:tag:genre:place"}]}})
    tags = asyncio.run(QlooClient(be).find_tags("restaurant"))
    assert tags == [{"id": "urn:tag:genre:place:restaurant", "name": "Restaurant", "type": "urn:tag:genre:place"}]
    assert be.calls[0] == ("/v2/tags", {"filter.query": "restaurant", "take": 10})


def test_insights_location_only_for_places_and_compare_params():
    be = FakeBackend({"results": {"entities": []}})
    c = QlooClient(be)
    asyncio.run(c.insights("urn:entity:movie", ["A"], location="New Delhi"))
    asyncio.run(c.insights("urn:entity:place", ["A"], location="New Delhi", tags=["urn:tag:genre:place:restaurant"]))
    asyncio.run(c.compare(["A", "B"], ["C"]))
    movie, place, cmp_ = (p for _, p in be.calls)
    assert "filter.location.query" not in movie
    assert place["filter.location.query"] == "New Delhi" and place["filter.tags"] == "urn:tag:genre:place:restaurant"
    assert place["feature.explainability"] == "true"
    assert be.calls[2][0] == "/v2/analysis/compare"
    assert cmp_["a.signal.interests.entities"] == "A,B" and cmp_["b.signal.interests.entities"] == "C"
