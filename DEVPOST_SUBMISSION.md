# Common Ground

*An agent that plans one evening a whole group of friends will enjoy, using Qloo's taste graph to find where their tastes actually overlap.*

**Live demo:** https://common-ground.onrender.com

## Inspiration

Every group chat has the same Friday-night thread: "what should we do?" One friend loves indie folk, another lives on Delhi hip-hop, a third only watches Nolan films, and someone always suggests the same restaurant. Recommendation engines are built for one person. We wanted something that takes several very different tastes and finds the honest common ground between them, and that shows its reasoning instead of asking the group to trust a black box.

## What it does

Each friend (2 to 5 of them) enters two or three things they love: artists, films, shows, books or restaurants. Common Ground then:

- resolves every name to a Qloo entity,
- compares every pair of friends to map the taste tags they share (Drama, Folk, Melodic, Indian…),
- asks Qloo for recommendations driven by everyone's picks combined, with dinner places restricted to the group's city,
- and returns an evening plan: **something to watch, a soundtrack artist, and a place for dinner**, each with two alternates.

Every pick carries a "why" grounded in real Qloo signals: its affinity score, the shared tags and which friends share them, and whose pick pulled it in. For the Delhi example group the live run suggests *Dil Bechara* to watch, *Atif Aslam* for the soundtrack and *The Roseate, New Delhi* for dinner, explaining for example that Dil Bechara scores 0.94 against the group and carries the "Drama" tag all four friends share. The UI streams the agent's work live: each tool step, each Qloo API call and each planner thought.

## How we built it

- **Backend:** Python, FastAPI, httpx, server-sent events for the live trace.
- **Qloo Insights API (hackathon environment):** `/search` to resolve picks, `/v2/analysis/compare` for every pair of friends, `/v2/tags` to find the real restaurant tag, and `/v2/insights` with `signal.interests.entities`, `feature.explainability`, `filter.location.query` and `filter.tags` for the recommendations.
- **Agent:** a tool-using agent with six tools (resolve picks, search entity, compare friends, find tags, get recommendations, finalize plan). Gemini (`gemini-3.1-flash-lite`, falling back to `gemini-flash-lite-latest` and `gemini-2.5-flash-lite`) plans the calls through function calling and writes the explanations. A scripted planner runs the same tools when Gemini is unavailable or exceeds a 20-second budget, so the app always returns a full plan.
- **Ranking:** a group score that blends Qloo affinity with shared-tag matches and how many friends' picks drove each result.
- **Grounding check:** every explanation must cite a real affinity score or shared tag, and may not contain numbers that are not in the evidence; anything that fails is replaced by a template built from the same signals.
- **Frontend:** vanilla HTML, CSS and JavaScript with no build step.
- **Quality:** a pytest suite that runs on a mock backend shaped like Qloo's responses (no keys, no network), and deployment as a Render blueprint.

## Challenges we ran into

- **Entity resolution is ambiguous.** Searching "Prateek Kuhad" returns the *person* before the *artist*, and only the artist carries music taste data. "Karim's" matched a Chandigarh branch first. We added type preferences and a city-scoped retry for restaurants.
- **Cross-domain overlap.** Compare returns few shared tags between, say, a film-only friend and a music-only friend, so the overlap map aggregates across all pairs and the ranking leans on combined-signal affinity when tags are thin.
- **Undocumented shapes.** Explainability and locality structures had to be verified against live responses (for example, `query.localities.filter` is a list), so the parsers are defensive and tested.
- **Keeping an LLM honest.** Models like to invent confident numbers. The grounding check made explanations trustworthy without giving up the warmth of generated text.
- **Latency.** A full plan takes over a dozen API calls; running independent calls in parallel keeps the live run around 7 seconds.

## Accomplishments that we're proud of

- Every recommendation is explainable down to the Qloo signal and the friend's pick that produced it.
- The app never dead-ends: no Gemini key, an exhausted quota or a slow model all still produce a complete, grounded plan.
- The live trace makes the agent's reasoning visible, which turns out to be half the fun for a group deciding together.

## What we learned

- Qloo's cross-domain taste graph is what makes group planning work: a friend's favourite film genuinely shifts which artist or restaurant gets recommended.
- Explainability data is the difference between a recommendation and a convincing one.
- A deterministic fallback path is worth building first; it made the LLM layer a pure upgrade instead of a single point of failure.

## What's next for Common Ground

- More slots (an activity, a book club pick, a weekend trip via destinations).
- Sharing a plan link with the group and letting friends vote on the alternates.
- Using Qloo audience and demographic signals to tune plans for the group's age range.
- Time- and budget-aware dinner picks using place hours and price level.

## Built with

Python · FastAPI · httpx · Pydantic · Uvicorn · Qloo Insights API · Google Gemini (google-genai) · JavaScript · HTML · CSS · Server-Sent Events · pytest · Render
