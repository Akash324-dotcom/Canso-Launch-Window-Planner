# Canso Launch Window Planner

[![tests](https://github.com/Akash324-dotcom/Canso-Launch-Window-Planner/actions/workflows/tests.yml/badge.svg)](https://github.com/Akash324-dotcom/Canso-Launch-Window-Planner/actions/workflows/tests.yml)

A launch-window decision tool for Spaceport Nova Scotia (Canso, 45.3 N, 61.0 W), built for the MDA Mission Accepted Space Hackathon (Halifax, October 2026). Given a target orbit, it works out when a launch can reach it, how likely the weather is to allow it, and what a delay costs, and shows the answer in a five-screen web app with a launch countdown.

[Demo video](https://drive.google.com/drive/folders/1mn3HQBs3uSoDM56nq-s1oIFmS-eHEmhs?usp=share_link)

## How it works

Four parts, each with its own tests, joined by a frozen `/v1` API contract (`docs/00_INTEGRATION_CONTRACT.md`):

| Part | What it does |
|---|---|
| **Engine** (`backend/engine`) | Orbital mechanics: reachability from the pad, secular J2 nodal drift, the window equation (opportunity versus period), the injection-consistent fixed point, sun-synchronous orbit constraints, range and conjunction screens, and the expected-delay cost layer |
| **Weather** (`backend/weather`) | Launch-weather probability, climatology and a hindcast check of the forecast skill |
| **API** (`backend/api`) | FastAPI service exposing the engine and weather as `/v1` endpoints, plus a public Python client (`backend/client`) |
| **Frontend** (`frontend`) | Plain ES-module web app with an offline fallback, so the demo still works with no network |

Every constant carries its source, and every assumption is labelled as an assumption, so a reader can tell what is verified from what is modelled.

## My contribution

A four-person team built this. I built the engine and contributed to the API, weather and frontend parts.

## Run it

```bash
pip install -e ".[dev]"
uvicorn backend.api.app:app --port 8000      # the API
python -m http.server 8001                    # the frontend, in a second terminal
```

Open `http://localhost:8001/frontend/`. The app calls the API at the address set in `frontend/src/config.js` (`API_BASE`, port 8000 by default, so keep the API on 8000). With no API running, the app switches to its offline fixtures and says so in a banner. More detail is in `frontend/README.md`.

## Test it

```bash
pytest                       # backend: 1,421 tests
cd frontend && npm ci && npm test    # frontend: 176 tests
```

Both run on every push through GitHub Actions (`.github/workflows/tests.yml`).

## Reproducibility notes

- The hindcast and skill-fixture tests regenerate the committed results and compare them to the files in the repo. Floats are compared to a relative 1e-9, because the last digits of a float differ between library versions and CPUs.
- The shipped fixtures contain launch windows on 5 to 7 October 2026, so the frontend tests freeze the clock just before them (`frontend/tests/setup-clock.js`). Without that, the countdown tests fail once those dates pass.
