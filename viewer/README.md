# 3D Viewer

React + react-three-fiber dollhouse viewer, opened from ASI:One cards. Owner: Aditya.

Deep link: `/s/{space_id}?mode={elder|baby|interior|claim}&o={overlay_set_id}` (add `&snapshot=1` for card renders).

## Layout

| Path | What it is |
|---|---|
| `src/routes/SpaceView.tsx` | The `/s/:spaceId` page: loads data, top bar, object side card |
| `src/scene/` | `Dollhouse` (lights, controls), `RoomShell` (floor + cut-away walls), `ObjectMesh` (one object) |
| `src/overlays/` | One file per overlay type; `OverlayLayer` dispatches. `Pin` done, others stubbed |
| `src/modes/presets.ts` | Accent colour + camera per mode, theme colours |
| `src/lib/` | `types` (contracts), `api` (Space Service calls), `defaults` (fallback sizes/colours) |
| `vercel.json` | SPA rewrite so deep links work on Vercel |

## Run

```bash
cd viewer
npm install
cp .env.example .env     # VITE_SPACE_SERVICE_URL=http://localhost:8000
npm run dev              # http://localhost:5173/s/demo_home_01
```
