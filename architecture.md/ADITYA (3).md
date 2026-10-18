# ADITYA.md — Space Service + 3D Viewer

> You own everything from "user uploaded a video/photos" to "a beautiful, interactive 3D dollhouse that agents can draw on". Read `MASTER.md` Sections 4, 5, 8 first. Your outputs must match the `Space`, `SpaceObject`, `Room`, `Door`, `Overlay` contracts exactly.

---

## 1. What you deliver

1. **Space Service** (`/space_service`, FastAPI, Python 3.11) — turns media into `Space` JSON, stores spaces and overlay sets, renders snapshot PNGs for cards.
2. **3D Viewer** (`/viewer`, React + react-three-fiber) — loads a Space + overlay set from a URL and renders the dollhouse with the mode's camera and effects.
3. **A prebuilt demo Space** for our demo home (hand-checked), used as the stage fallback.

You do **not** write any Fetch agent. Shresth wraps your service in the Space Builder agent.

---

## 2. Space Service API (exact)

| Method | Path                                           | Body / params                                           | Returns                                         |
| ------ | ---------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------- |
| POST   | `/spaces/build`                                | `{"job_id", "media_urls": [...], "trace": {...}}`       | `SpaceBuildResult` JSON (see MASTER §5)         |
| GET    | `/spaces/{space_id}`                           | —                                                       | `Space` JSON                                    |
| POST   | `/spaces/{space_id}/overlays`                  | `{"mode": "elder", "overlays": [Overlay...], "job_id"}` | `{"overlay_set_id": "ov_..."}`                  |
| GET    | `/spaces/{space_id}/overlays/{overlay_set_id}` | —                                                       | `{"mode", "overlays": [...]}`                   |
| GET    | `/spaces/{space_id}/snapshot.png`              | `?mode=elder&o={overlay_set_id}&view=hero`              | PNG (1200×800) for cards                        |
| POST   | `/media/upload`                                | multipart file                                          | `{"url": "..."}` (for our fallback upload page) |
| GET    | `/health`                                      | —                                                       | `{"ok": true}` (Kenil adds an uptime monitor)   |

Storage: SQLite or a JSON folder is fine (`/data/spaces/{id}.json`, `/data/overlays/{id}.json`). Media files to local disk or a bucket; return public URLs.

**Viewer deep link format:** `https://<viewer-host>/s/{space_id}?mode={mode}&o={overlay_set_id}`

---

## 3. Build pipeline (video/photos → Space)

1. **Frames:** video → 1 frame per second with `ffmpeg` (max ~30 frames). Keep each frame as a public image (these become `Evidence.frame_url`). Photos: use as-is.
2. **Gemini extraction (structured output):** send frames (or the video file via the Files API — wait until the file is ACTIVE) with a strict JSON schema:
   - rooms (name, rough floor polygon in meters, ceiling height)
   - doors (position, width), windows
   - objects: `type` (from the catalog below), label, room, approximate position and size in meters, color hex, material, `attributes` (brand/model guess, `height_from_floor`, `is_loose` for rugs, `has_cover` for outlets, `sharp_corners`, etc.), confidence, and **which frame + timestamp** it was seen in.
   - Prompt Gemini to use reference objects for scale: standard interior door ≈ 2.03 m tall × 0.81 m wide, kitchen counter ≈ 0.91 m high, outlet cover ≈ 0.11 m tall.
     can also use anthropic or openai api key whatever suits best.

3. **Scale fix:** compute a scale factor from detected doors/counters; if no references, mark `scale_method="estimate"` and lower `scale_confidence`. Optional upgrade: Apple **Depth Pro** (metric depth from one image) on 2–3 key frames.
4. **Layout solver (deterministic, no LLM):** snap objects against the nearest wall, put floor objects on y=0, push overlapping boxes apart, clamp everything inside the room polygon.
5. **Assign stable ids:** `obj_{type}_{nn}`, `room_{name}`, `door_{nn}`.
6. Save, render snapshot, return `SpaceBuildResult`.

Target: **≤ 120 s** per build. Kenil will profile this — expect him to ask where the time goes.

### Object catalog (map each to a 3D model)

Source of truth: `space_service/pipeline/catalog.py` (96 types, with layout rules). `door` is returned as a Door, never an object.

- **living room:** sofa, sectional_sofa, armchair, recliner, ottoman, coffee_table, side_table, console_table, tv, tv_stand, bookshelf, shelf, cabinet, bench, fireplace, piano
- **bedroom:** bed, crib, nightstand, dresser, wardrobe, vanity, changing_table, toy_box, toys
- **dining and office:** dining_table, chair, high_chair, stool, desk, office_chair
- **kitchen:** counter, kitchen_island, refrigerator, stove, oven, microwave, dishwasher, sink, range_hood, small_appliance, trash_can
- **laundry and utility:** washer, dryer, water_heater, laundry_basket, ironing_board
- **bathroom:** toilet, bathtub, shower, bath_mat, towel_rack, grab_bar, shower_seat
- **lighting:** light, lamp_floor, lamp_table
- **decor:** rug, plant, painting, mirror, curtain, clock, decor
- **electronics:** laptop, monitor, computer, game_console, speaker, printer, router, fan, space_heater, air_conditioner
- **building:** window, stairs, step, handrail, radiator, outlet, light_switch, thermostat, smoke_detector
- **safety and mobility:** stair_gate, walker, wheelchair
- **storage and misc:** box, shoe_rack, coat_rack, pet_bed, bicycle, exercise_equipment, cord, clutter, other

Attributes the extractor sets (names match what the specialists read): `is_loose`, `covered`, `anchored`, `grab_bar`, `sharp_corners`, `night_light`, `is_movable`, `shape`, `height_from_floor`, plus `seat_height_m`, `toilet_shape` and `model_guess` when known.

Use free CC0/CC-BY glTF packs (Kenney Furniture Kit, Poly Pizza; Sketchfab only if license allows). Scale each model to the object's `size`, tint with `color`.

---

## 4. Viewer (react-three-fiber): all the design are suggestion not to be taken as concerete you may suggest better way to implment and ask for approval

**Look (aim for "best design"):**

- "Dollhouse" cut-away: walls at ~70% height or fade walls facing the camera.
- Warm off-white base, soft charcoal text, **one accent per mode** (elder amber `#E8A33D`, baby mint `#5BC8A8`, interior terracotta `#C9714F`, claim deep blue `#2F5D9B`).
- Soft light: one warm directional light + environment light + **ambient occlusion** (`@react-three/postprocessing` N8AO) + contact shadows. This is what makes it look premium.
- Big readable labels anchored to objects (drei `Html`), max ~6 words each.
- Motion only to show something (camera glides hazard → hazard, before → after). No decorative spinning.
- Accessible: high contrast, large hit areas, never color alone (icon + text).

**Overlay types you must render (`Overlay.data`):**

| type           | data fields                                                                                 | renders as                                                               |
| -------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `pin`          | `object_id`, `severity` 1–5, `title`, `finding_id`, `frame_url`                             | glowing pin above the object; click → side card with the video frame     |
| `path`         | `points` [[x,y,z]...], `width_m`, `blocked_at` [[x,y,z]...], `label`                        | ribbon on the floor (walker footprint width); red segments where blocked |
| `ghost_object` | `type`, `position`, `size`, `rotation_y`, `label`, `price_usd`                              | semi-transparent new object (a fix or a design suggestion)               |
| `tag`          | `object_id`, `text`, `badge` ("Receipt ✓", "Measured ±2 in")                                | floating price/value tag (claim mode)                                    |
| `highlight`    | `object_ids`, `color`                                                                       | outline / glow on objects                                                |
| `camera`       | `preset` ("hero", "first_person", "toddler", "orbit", "flythrough"), `eye_height_m`, `path` | camera behavior for the mode                                             |

**Mode presets:**

- **elder:** first person at `eye_height_m` (~1.55), lights dim to "night", walker ribbon glides along `path`, flashes red at `blocked_at`. Toggle: before / after (ghost fixes on).
- **baby:** crawling camera ~0.75 m, everything reachable below 0.9 m gets a soft glow; hazards pulse.
- **interior:** orbit from above; ghost objects show the new layout; style switcher swaps ghost sets.
- **claim:** slow flythrough; tags float up from each item; running total counter in the corner; before/after slider that dims the room to "ash".

**Snapshots for cards:** render with headless Chromium (Playwright) opening the deep link with `?snapshot=1&view=hero`, screenshot at 1200×800, cache the PNG. Cards cannot run 3D, so these images matter a lot.

**Sentry in the viewer (Kenil helps):** `@sentry/react` with browser tracing + **Session Replay**. Tag `space_id`, `mode`.

---

## 5. Handoff to Shresth

- Push to GitHub (`aditya/*` branches → PR).
- Give Shresth: Space Service base URL, viewer base URL, and the prebuilt demo `space_id`.
- `space_service/README.md`: how to run (`uvicorn ...`), env vars (`GEMINI_API_KEY`, `GEMINI_MODEL`, `PUBLIC_BASE_URL`, `SENTRY_DSN`), example curl for each endpoint.
- `space_service/test_local.py`: builds a Space from `samples/demo_room.mp4` and prints object counts.

---

## 6. Your checkpoints

| Time          | Done                                                                                                                                        |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Sat 9 PM**  | `/health`, `/spaces/build` returns a **stub** Space (hard-coded) that validates against `Space`; viewer renders a stub room                 |
| **Sun 12 AM** | Real Gemini extraction on the demo video; scale from doors; viewer renders real dollhouse; `pin` + `path` overlays work; snapshot PNG works |
| **Sun 4 AM**  | All overlay types + all 4 mode presets; prebuilt demo Space hand-checked; build ≤ 120 s                                                     |
| **Sun 8 AM**  | Design polish only; Session Replay on                                                                                                       |

---

## 7. Gotchas

- Gemini positions will be rough. The layout solver and wall snapping are what make it look "visually correct". Spend time there.
- Never let the viewer crash on a missing field — default sizes per type.
- Keep the demo video short, well lit, slow pan. Film the demo home tonight and build the prebuilt Space from it.
- Big glTF files kill load time: use Draco/meshopt compression, < 15 MB total.
