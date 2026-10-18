// /s/:spaceId?mode=elder&o=ov_123&level=1 — loads a Space (+ overlay set) and renders one floor
// of the dollhouse (the lowest by default; a switcher appears when there are several).
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { fetchOverlaySet, fetchSpace } from "../lib/api";
import { objectSize } from "../lib/defaults";
import type { OverlaySet, Space } from "../lib/types";
import { Dollhouse, spaceBounds } from "../scene/Dollhouse";
import { MODE_PRESETS, THEME, isMode } from "../modes/presets";
import type { WalkCmd, WalkEntry, WalkInput } from "../scene/WalkControls";

const KEY_CMDS: Record<string, WalkCmd> = {
  ArrowUp: "forward", w: "forward", W: "forward",
  ArrowDown: "back", s: "back", S: "back",
  ArrowLeft: "left", a: "left", A: "left",
  ArrowRight: "right", d: "right", D: "right",
};

/** One walk button: a tap takes one step, holding keeps walking. */
function WalkButton({ cmd, label, glyph, input }: { cmd: WalkCmd; label: string; glyph: string; input: React.MutableRefObject<WalkInput> }) {
  const release = () => {
    if (input.current.held === cmd) input.current.held = null;
  };
  return (
    <button
      className={`walk-btn walk-${cmd}`}
      aria-label={label}
      title={label}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        input.current.queue.push(cmd);
        input.current.held = cmd;
      }}
      onPointerUp={release}
      onPointerCancel={release}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") input.current.queue.push(cmd);
      }}
    >
      {glyph}
    </button>
  );
}

const LEVEL_NAMES: Record<number, string> = { [-1]: "Basement", 0: "Main floor", 1: "Upper floor" };
const levelName = (level: number) => LEVEL_NAMES[level] ?? `Floor ${level + 1}`;

/** The part of a space on one floor. Doors are filtered too, or an upstairs doorway at the same
 *  x/z would cut a hole in a downstairs wall. */
function onLevel(space: Space, level: number): Space {
  const rooms = space.rooms.filter((r) => (r.level ?? 0) === level);
  const ids = new Set(rooms.map((r) => r.id));
  return {
    ...space,
    rooms,
    objects: space.objects.filter((o) => ids.has(o.room_id)),
    doors: (space.doors ?? []).filter((d) => ids.has(d.room_id)),
  };
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; space: Space; overlaySet: OverlaySet | null };

export function SpaceView() {
  const { spaceId = "" } = useParams();
  const [params] = useSearchParams();
  const modeParam = params.get("mode");
  const overlaySetId = params.get("o");
  const isSnapshot = params.get("snapshot") === "1";
  const preset = isMode(modeParam) ? MODE_PRESETS[modeParam] : null;

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [levelChoice, setLevelChoice] = useState<number | null>(null);
  const [walk, setWalk] = useState<WalkEntry | null>(null);
  const [walkRoom, setWalkRoom] = useState<string | null>(null);
  const walkInput = useRef<WalkInput>({ queue: [], held: null });

  // Arrow keys / WASD walk, Escape leaves the tour.
  useEffect(() => {
    if (!walk) return;
    const down = (e: KeyboardEvent) => {
      if (e.key === "Escape") return setWalk(null);
      const cmd = KEY_CMDS[e.key];
      if (!cmd) return;
      e.preventDefault();
      if (!e.repeat) walkInput.current.queue.push(cmd);
      walkInput.current.held = cmd;
    };
    const up = (e: KeyboardEvent) => {
      if (KEY_CMDS[e.key] === walkInput.current.held) walkInput.current.held = null;
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      walkInput.current = { queue: [], held: null };
    };
  }, [walk !== null]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    Promise.all([fetchSpace(spaceId), overlaySetId ? fetchOverlaySet(spaceId, overlaySetId) : Promise.resolve(null)])
      .then(([space, overlaySet]) => !cancelled && setState({ status: "ready", space, overlaySet }))
      .catch((err: Error) => !cancelled && setState({ status: "error", message: err.message }));
    return () => {
      cancelled = true;
    };
  }, [spaceId, overlaySetId]);

  const levels = useMemo(
    () => (state.status === "ready" ? [...new Set(state.space.rooms.map((r) => r.level ?? 0))].sort((a, b) => a - b) : []),
    [state],
  );
  const paramLevel = params.get("level") === null ? NaN : Number(params.get("level"));
  // With findings, open on the floor that has the most of them (the night path is often upstairs).
  const pinnedLevel = useMemo(() => {
    if (state.status !== "ready" || !state.overlaySet) return null;
    const roomLevel = new Map(state.space.rooms.map((r) => [r.id, r.level ?? 0]));
    const objectLevel = new Map(state.space.objects.map((o) => [o.id, roomLevel.get(o.room_id) ?? 0]));
    const counts = new Map<number, number>();
    for (const o of state.overlaySet.overlays) {
      const id = o.type === "pin" ? (o.data?.object_id as string | undefined) : undefined;
      if (id && objectLevel.has(id)) counts.set(objectLevel.get(id)!, (counts.get(objectLevel.get(id)!) ?? 0) + 1);
    }
    return counts.size ? [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0] : null;
  }, [state]);
  const level = levelChoice ?? (levels.includes(paramLevel) ? paramLevel : pinnedLevel ?? levels[0] ?? 0);
  const visible = useMemo(() => (state.status === "ready" ? onLevel(state.space, level) : null), [state, level]);

  const camera = useMemo(() => {
    if (!visible) return null;
    const { center, span } = spaceBounds(visible);
    return { position: [center[0] + span * 0.15, span * 0.95, center[2] + span * 1.05] as [number, number, number] };
  }, [visible]);

  if (state.status === "loading") return <div className="status">Loading home…</div>;
  if (state.status === "error") return <div className="status">Couldn't load this home. {state.message}</div>;

  const { overlaySet } = state;
  const space = visible!;
  const selected = space.objects.find((o) => o.id === selectedId) ?? null;

  return (
    <div className="viewer" style={{ background: THEME.background }}>
      {/* flat: tone mapping happens in the post-processing chain (AgX), not in the renderer. */}
      <Canvas
        shadows
        flat
        dpr={[1, 2]}
        camera={{ position: camera!.position, fov: 40 }}
        gl={{ preserveDrawingBuffer: isSnapshot }}
      >
        <Dollhouse
          space={space}
          overlaySet={overlaySet}
          preset={preset}
          selectedId={selectedId}
          onSelect={setSelectedId}
          walk={isSnapshot ? null : walk}
          walkInput={walkInput}
          onWalk={(entry) => {
            setWalk(entry);
            setSelectedId(null);
          }}
          onWalkRoom={setWalkRoom}
        />
      </Canvas>

      {!isSnapshot && (
        <header className="topbar">
          <span className="brand">Last Mile Home</span>
          {preset && (
            <span className="mode-chip" style={{ background: preset.accent }}>
              {preset.label}
            </span>
          )}
          <span className="meta">
            {space.rooms.length} rooms · {space.objects.length} items
          </span>
          {levels.length > 1 && (
            <nav className="levels" aria-label="Floor">
              {levels.map((l) => (
                <button
                  key={l}
                  className={l === level ? "level active" : "level"}
                  aria-pressed={l === level}
                  onClick={() => {
                    setLevelChoice(l);
                    setSelectedId(null);
                    setWalk(null);
                  }}
                >
                  {levelName(l)}
                </button>
              ))}
            </nav>
          )}
        </header>
      )}

      {!isSnapshot && !walk && <p className="walk-hint">Click any floor to walk in</p>}

      {!isSnapshot && walk && (
        <div className="walk-ui">
          <div className="walk-status">
            <span className="walk-room">{walkRoom ?? "Doorway"}</span>
            <button className="walk-exit" onClick={() => setWalk(null)}>
              Exit tour
            </button>
          </div>
          <div className="walk-pad" role="group" aria-label="Walk">
            <WalkButton cmd="forward" label="Step forward" glyph="▲" input={walkInput} />
            <WalkButton cmd="left" label="Turn left" glyph="◀" input={walkInput} />
            <WalkButton cmd="back" label="Step back" glyph="▼" input={walkInput} />
            <WalkButton cmd="right" label="Turn right" glyph="▶" input={walkInput} />
          </div>
          <p className="walk-help">Drag to look around · click the floor to jump there · arrow keys work too</p>
        </div>
      )}

      {!isSnapshot && selected && (
        <aside className="side-card">
          <h2>{selected.label}</h2>
          <p className="muted">{selected.type.replace(/_/g, " ")}</p>
          <p>
            {objectSize(selected)
              .map((m) => `${Math.round(m * 39.37)} in`)
              .join(" × ")}
          </p>
          {selected.evidence?.[0]?.frame_url && <img src={selected.evidence[0].frame_url} alt="Video frame" />}
        </aside>
      )}
    </div>
  );
}
