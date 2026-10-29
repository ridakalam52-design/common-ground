# Common Ground

**Plan one evening that a whole group of friends will actually enjoy.**

Each friend types two or three things they love: an artist, a film, a show, a restaurant. Common Ground's agent resolves those names in the Qloo Taste AI graph, measures where the friends' tastes overlap, and builds an evening plan for the group's city: **something to watch, a soundtrack artist, and a place for dinner**, each with two alternates. Every pick comes with a "why" that cites the real Qloo signals behind it: the affinity score, the taste tags the friends share, and whose pick pulled it in.

Built for the **Qloo LLM Hackathon** (FastAPI + vanilla JS, Qloo Insights API, optional Gemini).

**Live demo:** https://common-ground-a1fi.onrender.com

---

## Quick start

```bash
git clone <this repo> && cd commonground
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add QLOO_API_KEY (and optionally GEMINI_API_KEY)
set -a; . ./.env; set +a
uvicorn app.main:app --reload
# open http://localhost:8000 and press "Load Delhi example", then "Plan our evening"
```

| Variable | Required | Purpose |
|---|---|---|
| `QLOO_API_KEY` | for live mode | Qloo hackathon key. Without it the app runs on a hand-written mock catalog, labelled "demo data" in the UI. |
| `GEMINI_API_KEY` | no | Lets Gemini plan the tool calls and write the explanations. Without it a scripted planner runs the same tools. |
| `GEMINI_MODEL` | no | Default `gemini-3.1-flash-lite`; fallbacks `gemini-flash-lite-latest`, `gemini-2.5-flash-lite` (`GEMINI_FALLBACK_MODELS`). |
| `GEMINI_TIMEOUT` | no | Seconds before the Gemini phase is abandoned for the scripted planner (default 20). |
| `QLOO_MOCK=1` | no | Force mock mode even when a key is set. |

API: `POST /api/plan` returns the plan plus the full trace; `POST /api/plan/stream` streams the same run as server-sent events; `GET /api/example` returns the Delhi demo group; `GET /api/health` reports mode and planner.

Tests run entirely on the mock backend, with no keys and no network:

```bash
pytest -q
```

Deploy: `render.yaml` is a Render blueprint (Python web service, free plan). Set `QLOO_API_KEY` and `GEMINI_API_KEY` in the Render dashboard.

---

## How it uses Qloo

All calls go to `https://hackathon.api.qloo.com` with the key in the `X-Api-Key` header. Responses are cached in process memory only and are never written to disk.

| Endpoint | Parameters | How its signals drive the picks |
|---|---|---|
| `GET /search` | `query`, `types`, `take` | Resolves every free-text pick to a Qloo entity. When a musician comes back as both `person` and `artist`, the artist is preferred because that is where the music taste data lives. A restaurant whose best match is in another city is searched again scoped to the group's city (e.g. "Karim's" resolves to the New Delhi branch, not Chandigarh). |
| `GET /v2/analysis/compare` | `a.signal.interests.entities`, `b.signal.interests.entities` | Run for every pair of friends. The shared tags and their `query.score` become the group's **overlap map**: which tags (Drama, Folk, Melodic, Indian…) are shared, by whom, and how strongly. Picks carrying those tags rank higher and the "why" names them. |
| `GET /v2/tags` | `filter.query=restaurant` | Finds the real restaurant tag ID (`urn:tag:genre:place:restaurant`) so dinner suggestions are places to eat rather than any venue. |
| `GET /v2/insights` | `filter.type` (movie, tv_show, artist, place), `signal.interests.entities` (everyone's picks combined), `filter.exclude.entities`, `feature.explainability=true`, and for places `filter.location.query` + `filter.tags` | The core recommendation call. `query.affinity` is the main ranking signal; `query.explainability` tells us which friend's pick pulled each result in, so the plan can say "strongest pull comes from Kabir's pick Gully Boy". `query.localities` confirms the matched city. |

No `/recs` or `/recommendations` endpoints are used; a test enforces this.

### Group score

For each candidate: `0.7 × affinity + 0.06 × (shared tags matched, up to 3) + 0.12 × (share of friends whose picks drove it)`. Affinity dominates, shared tags and coverage break ties toward options that serve the whole group rather than one person.

### Grounded explanations

Every "why" must cite at least one real signal (the affinity score or a shared tag name) and may not quote any number that is not in the evidence. Gemini-written explanations that fail this check are replaced with a template built from the same signals, so no pick ships without a grounded reason.

---

## Architecture

```
app/
  main.py        FastAPI: UI, /api/plan, /api/plan/stream (SSE), validation
  agent.py       CommonGroundAgent: tools, Gemini loop, scripted planner, plan builder
  qloo.py        Qloo client (live backend + parsers for search, tags, insights, compare)
  ranking.py     overlap map, group score, template whys, grounding check
  llm.py         Gemini wrapper (google-genai) with model fallback
  mock_qloo.py   mock backend answering the same paths with Qloo-shaped responses
  mock_data.py   hand-written demo catalog (not Qloo data)
  config.py      settings from environment variables
  static/        index.html, app.js, styles.css (vanilla JS, no build step)
tests/           pytest suite, mock mode only
```

The browser posts the group to `/api/plan/stream`; the server runs the agent and streams each tool step, each Qloo HTTP call and each planner thought, so the UI shows the agent working live, then renders the plan, the overlap map and the evidence for each pick.

## The agent loop

1. **Resolve** – `resolve_picks` per friend (parallel `/search` calls); `search_entity` retries a name that did not resolve.
2. **Compare** – `compare_friends` for every pair, building the overlap map.
3. **Find tags** – `find_tags("restaurant")` for a real tag ID.
4. **Recommend** – `get_recommendations` for movie, artist and place (place filtered to the city and the restaurant tag; falls back to no tag if empty; adds TV shows if films are thin). Friends' own picks are never recommended back.
5. **Finalize** – `finalize_plan`: one pick plus two alternates per slot, a two-sentence summary, and a grounded "why" for each.

With `GEMINI_API_KEY` set, Gemini chooses and orders these tool calls through function calling and writes the explanations. The whole Gemini phase has a hard ~20 s timeout; on timeout, quota or model errors the scripted planner runs the same tools in the same order and finishes the plan, filling in any step Gemini skipped. The full live run for the Delhi example takes about 7 seconds.

## License

MIT © 2026 Rida Kalam
