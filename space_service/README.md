# Space Service

Turns a home video/photos into `Space` JSON, stores spaces + overlay sets, and serves snapshot PNGs for ASI:One cards. Owner: Aditya. Contracts: `MASTER.md` §5 (mirrored in `schemas.py`).

## Layout

| Path | What it is |
|---|---|
| `main.py` | FastAPI app and every route |
| `schemas.py` | Pydantic copies of the shared contracts (`Space`, `Overlay`, ...) |
| `config.py` | Env vars and paths |
| `storage.py` | JSON-folder storage under `data/` |
| `pipeline/` | Build steps: `frames` → `extract` (Claude Sonnet) → `scale` → `layout` → `ids` |
| `snapshots.py` | 1200×800 card images (placeholder until Playwright is wired up) |
| `prebuilt/demo_space.json` | Hand-made demo home `demo_home_01` (stage fallback) |
| `test_local.py` | Smoke test of every endpoint |
| `test_page.html` | Latency test bench served at `/test` |
| `data/` | Runtime storage (git-ignored) |

## Run

Python 3.11+ (built on 3.13; the code avoids 3.12+-only syntax so it runs on the 3.11 VM).

```bash
cd space_service
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
cp .env.example .env
.venv/Scripts/python test_local.py                         # prints ALL OK
.venv/Scripts/python -m uvicorn main:app --reload --port 8000
```

With `USE_PREBUILT=1` (default), `/spaces/build` returns the prebuilt demo space.

**Latency test:** open http://localhost:8000/test, upload a video, and pick max frames and effort. It always runs the real pipeline (via `POST /debug/build`) and shows per-step timings, token usage and estimated cost.

## Env vars

`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default `claude-opus-5-5`), `ANTHROPIC_EFFORT` (`low`/`medium`/`high`), `SENTRY_DSN`, `PUBLIC_BASE_URL` (this service), `VIEWER_BASE_URL` (the viewer), `CORS_ORIGINS`, `USE_PREBUILT`.

## Endpoints

```bash
curl localhost:8000/health
curl -X POST localhost:8000/spaces/build -H 'content-type: application/json' \
  -d '{"job_id":"job_1","media_urls":["https://.../home.mp4"]}'
curl localhost:8000/spaces/demo_home_01
curl -X POST localhost:8000/spaces/demo_home_01/overlays -H 'content-type: application/json' \
  -d '{"mode":"elder","job_id":"job_1","overlays":[{"type":"pin","data":{"object_id":"obj_rug_02","severity":4,"title":"Loose hallway runner"}}]}'
curl localhost:8000/spaces/demo_home_01/overlays/ov_xxxxxxxxxx
curl -o snap.png "localhost:8000/spaces/demo_home_01/snapshot.png?mode=elder&o=ov_xxxxxxxxxx&view=hero"
curl -F file=@frame.jpg localhost:8000/media/upload        # -> {"url": ".../files/media/<name>"}
```
