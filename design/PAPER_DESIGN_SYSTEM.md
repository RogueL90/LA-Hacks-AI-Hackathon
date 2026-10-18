# What lives in Paper (design system) vs in code

Paper file: **Last Mile Home — Design System** — https://app.paper.design/file/01M56HRH23KSG71YDGWR4RE25P

| Page | Status |
|---|---|
| Foundations | done — 53 tokens + board (accents, neutrals, status, severity, type, spacing, radius) |
| Viewer UI | done — top bar, mode chips, floor switcher, pin / object / tag / ghost labels, side card, walker path |
| Data Model | done — Space / Room / Door / SpaceObject (new: level, floor_material, Door.kind), 96-type catalog, attributes + which mode reads them |
| 3D Style | done — floor materials (real textures), door kinds, floors, object states, placement rules, material palette (§2) |
| ASI:One Cards | done — space ready, hazard carousel, fix plan, paid + handoff, claim package, recovery notice (§4) |

Rule of thumb: **Paper owns how things look. Code owns what data they get.**
JSON schemas stay in `shared/models.py`, `space_service/schemas.py`, `viewer/src/lib/types.ts`.
Paper tokens are exported (`get_tokens` → CSS) into `viewer/src/styles.css` and `viewer/src/modes/presets.ts`.

## 1. Foundations (Paper tokens)

| Group | Tokens |
|---|---|
| Neutrals | background (warm off-white), surface/card, text (soft charcoal), text-muted, border |
| Mode accents | elder amber `#E8A33D`, baby mint `#5BC8A8`, interior terracotta `#C9714F`, claim blue `#2F5D9B` (+ a soft tint of each for backgrounds) |
| Status | hazard/critical, warning, ok/pass, info — never colour alone: always icon + text |
| Severity scale | 1–5 colour ramp for hazard pins and carousel badges |
| Typography | font family, sizes (label 13 → display 32), weights, line heights |
| Spacing | 4 / 8 / 12 / 16 / 24 / 32 / 48 |
| Radius | chip (999), small (8), card (16) |
| Elevation | card shadow, floating label shadow |

## 2. 3D scene style (Paper page "3D Style", tokens + reference frames)

| Item | What Paper holds |
|---|---|
| Room shell | floor colour, wall colour, wall cut-away height, wall thickness |
| Material palette | wood, fabric, ceramic, metal, glass, plant swatches; rule for softening the extracted real colour toward the warm neutral |
| Object states | default · hovered · selected · hazard (pulse in accent) · ghost fix (≈40% opacity) · reachable-by-toddler glow · claim "ash" state |
| Lighting moods | day (hero), elder night, baby, interior, claim — reference screenshot + light values |
| Object icons | one 2D icon per catalog type (96, see Data Model page) — still todo for cards, legends, claim inventory |

Stays in code: glTF models (`viewer/public/models/`), type → model/default-size catalog (`lib/defaults.ts`).

## 3. Viewer UI components (frames, each labelled with the schema fields it shows)

| Component | Schema source |
|---|---|
| Top bar (brand, mode chip, room/item counts) | `Space` |
| Mode chip ×4 | `Mode` |
| Object label (hover) | `SpaceObject.label` |
| Object side card (label, type, size in inches, evidence frame) | `SpaceObject`, `Evidence` |
| Pin label (severity badge + title) | `Overlay pin` |
| Path legend (walker width, blocked segment) | `Overlay path` |
| Ghost object label (label + price) | `Overlay ghost_object` |
| Value tag (amount + badge "Receipt ✓" / "Measured ±2 in") | `Overlay tag` |
| Before / after toggle, running total counter (claim) | `ModeResult` |
| Loading / error / empty states | — |

## 4. ASI:One cards (Shresth builds; same tokens)

| Card | Schema source |
|---|---|
| Space ready: snapshot + "Open 3D view" + 4 mode buttons | `Space` |
| Intake form per mode (age, mobility aid, child age, style, budget, policy) | `Profile` |
| Hazard carousel item (frame, title, measurement pass/fail, fix) | `Finding`, `Measurement`, `Evidence` |
| Fix plan + prices + budget check | `CartResult`, `ProductQuote` |
| Payment request / receipt + checkout handoff (labelled "handoff, not an order") | `CartResult` |
| Claim package (total, item count, downloads) | `ClaimPackage` |
| Recovery notice (recovered / fallback / failed + trace link) | `RecoveryNotice` |

## 5. Snapshot images (1200×800 for cards)

Hero framing, per-mode overlay treatment, and the placeholder used while rendering.
