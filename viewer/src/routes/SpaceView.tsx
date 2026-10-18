// /s/:spaceId?mode=elder&o=ov_123&level=1 — loads a Space (+ overlay set) and renders one floor
// of the dollhouse (the lowest by default; a switcher appears when there are several).
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { SPACE_SERVICE_URL, fetchLatestOverlay, fetchOverlaySet, fetchSpace } from "../lib/api";
import { objectSize } from "../lib/defaults";
import type { OverlaySet, Space } from "../lib/types";
import { Dollhouse, spaceBounds } from "../scene/Dollhouse";
import { MODE_PRESETS, THEME, isMode } from "../modes/presets";
import type { WalkCmd, WalkEntry, WalkInput } from "../scene/WalkControls";
import { CartPanel, type CartItem } from "./CartPanel";

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

/** Frames saved as the service's local address still load when the viewer is opened from outside. */
const servedFrom = (url: string) => url.replace(/^https?:\/\/(127\.0\.0\.1|localhost):8300/, SPACE_SERVICE_URL);

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
  const live = params.get("live") === "1";
  const [liveMode, setLiveMode] = useState<string | null>(null);
  const shownMode = liveMode ?? modeParam;
  const preset = isMode(shownMode) ? MODE_PRESETS[shownMode] : null;

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [levelChoice, setLevelChoice] = useState<number | null>(null);
  const [walk, setWalk] = useState<WalkEntry | null>(null);
  const [walkRoom, setWalkRoom] = useState<string | null>(null);
  const walkInput = useRef<WalkInput>({ queue: [], held: null });
  const [cartOpen, setCartOpen] = useState(true);
  const [focus, setFocus] = useState<{ point: [number, number, number]; key: number; from?: [number, number] } | null>(null);

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

  // Live: when a new check runs on this home (elder, then baby...), switch to its findings.
  const shownOverlayId = useRef<string | null>(overlaySetId);
  useEffect(() => {
    if (!live) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const latest = await fetchLatestOverlay(spaceId, overlaySetId);
        if (cancelled || latest.overlay_set_id === shownOverlayId.current) return;
        const overlaySet = await fetchOverlaySet(spaceId, latest.overlay_set_id);
        if (cancelled) return;
        shownOverlayId.current = latest.overlay_set_id;
        setLiveMode(latest.mode);
        setSelectedId(null);
        setLevelChoice(null);
        setState((s) => (s.status === "ready" ? { ...s, overlaySet } : s));
      } catch {
        /* no overlays yet, or the service is restarting: try again next tick */
      }
    };
    const timer = window.setInterval(tick, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [live, spaceId, overlaySetId]);

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

  // Cart items placed in the home (see before you buy): every unit, and one entry per cart item.
  const ghosts = useMemo(
    () =>
      state.status === "ready"
        ? (state.overlaySet?.overlays ?? [])
            .filter((o) => o.type === "ghost_object" && Array.isArray(o.data?.position))
            .map((o) => o.data as CartItem)
        : [],
    [state],
  );
  const cartItems = useMemo(() => ghosts.filter((g) => (g.unit ?? 0) === 0).sort((a, b) => a.item - b.item), [ghosts]);
  const roomLevel = useMemo(
    () => (state.status === "ready" ? new Map(state.space.rooms.map((r) => [r.id, r.level ?? 0])) : new Map<string, number>()),
    [state],
  );
  useEffect(() => {
    if (cartItems.length) setCartOpen(true); // a new cart arrived (live): show it
  }, [cartItems.length]);
  const roomCenter = (roomId: string): [number, number] | undefined => {
    if (state.status !== "ready") return undefined;
    const pts = state.space.rooms.find((r) => r.id === roomId)?.polygon ?? [];
    if (!pts.length) return undefined;
    return [pts.reduce((a, p) => a + p[0], 0) / pts.length, pts.reduce((a, p) => a + p[1], 0) / pts.length];
  };
  const focusOn = (item: CartItem) =>
    setFocus({ point: item.position as [number, number, number], key: performance.now(), from: roomCenter(item.room_id) });
  // ?item=cart_2_0 opens the view on one cart item (a link from the chat, or a check).
  const itemParam = params.get("item");
  const itemOpened = useRef(false);
  useEffect(() => {
    if (itemOpened.current || !itemParam) return;
    const item = ghosts.find((g) => g.id === itemParam);
    if (!item) return;
    itemOpened.current = true;
    setLevelChoice(roomLevel.get(item.room_id) ?? 0);
    setSelectedId(item.id);
    focusOn(item);
  }, [ghosts, itemParam, roomLevel]); // eslint-disable-line react-hooks/exhaustive-deps

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
  const selectedItem = ghosts.find((g) => g.id === selectedId) ?? null;
  const pickItem = (item: CartItem) => {
    setWalk(null);
    setLevelChoice(roomLevel.get(item.room_id) ?? level);
    setSelectedId(item.id);
    focusOn(item);
  };
  const pins = (overlaySet?.overlays ?? []).filter((o) => o.type === "pin").map((o) => o.data ?? {});
  const findingsFor = (objectId: string) => pins.filter((p) => p.object_id === objectId);
  const onFloor = new Set(space.objects.map((o) => o.id));
  const pinsHere = pins.filter((p) => onFloor.has(p.object_id)).length;

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
          focus={focus}
        />
      </Canvas>

      {!isSnapshot && cartItems.length > 0 && !walk && (
        <CartPanel
          items={cartItems}
          selectedId={selectedId}
          accent={preset?.accent ?? "#3d8bd3"}
          open={cartOpen}
          onToggle={() => setCartOpen((o) => !o)}
          onPick={pickItem}
        />
      )}

      {!isSnapshot && (
        <header className="topbar">
          <span className="brand">Maestro</span>
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
          <p className="muted">
            {selected.type.replace(/_/g, " ")} ·{" "}
            {objectSize(selected)
              .map((m) => `${Math.round(m * 39.37)} in`)
              .join(" × ")}
          </p>
          {findingsFor(selected.id).map((f, i) => (
            <section key={i} className="finding" style={{ borderColor: preset?.accent }}>
              <div className="finding-head">
                {f.severity_label && (
                  <span className="finding-severity" style={{ background: preset?.accent }}>
                    {f.severity_label}
                  </span>
                )}
                <strong>{f.title}</strong>
              </div>
              {f.why?.length > 0 && (
                <>
                  <h3>Why it's flagged</h3>
                  <ul>
                    {f.why.map((w: string, j: number) => (
                      <li key={j}>{w}</li>
                    ))}
                  </ul>
                </>
              )}
              {f.fix && (
                <>
                  <h3>Fix</h3>
                  <p>{f.fix}</p>
                </>
              )}
            </section>
          ))}
          {(findingsFor(selected.id)[0]?.frame_url ?? selected.evidence?.[0]?.frame_url) && (
            <img
              src={servedFrom(findingsFor(selected.id)[0]?.frame_url ?? selected.evidence?.[0]?.frame_url)}
              alt="Where it was seen in your video"
            />
          )}
        </aside>
      )}
      {!isSnapshot && selectedItem && (
        <aside className="side-card">
          <p className="eyebrow" style={{ color: preset?.accent }}>In your cart · placed where it goes</p>
          <h2>{selectedItem.title ?? selectedItem.label}</h2>
          <p className="price">
            ${Number(selectedItem.price_usd).toFixed(2)}
            {Number(selectedItem.quantity) > 1 ? ` × ${selectedItem.quantity}` : ""} · {selectedItem.merchant}
          </p>
          {selectedItem.image_url && <img src={selectedItem.image_url} alt="" referrerPolicy="no-referrer" />}
          {(selectedItem.finding_title || selectedItem.fix) && (
            <section className="finding" style={{ borderColor: preset?.accent }}>
              {selectedItem.finding_title && <strong>Fixes: {selectedItem.finding_title}</strong>}
              {selectedItem.fix && <p>{selectedItem.fix}</p>}
            </section>
          )}
          {selectedItem.url && (
            <a className="store-link" href={selectedItem.url} target="_blank" rel="noopener noreferrer">
              View at {selectedItem.merchant} ↗
            </a>
          )}
        </aside>
      )}
      {!isSnapshot && !selected && !selectedItem && pinsHere > 0 && (
        <aside className={`findings-hint${cartItems.length > 0 && cartOpen && !walk ? " beside-cart" : ""}`}>
          {live && <span className="live-dot" />}
          {pinsHere} finding{pinsHere === 1 ? "" : "s"} on this floor · click a marker to see what's flagged and why
        </aside>
      )}
    </div>
  );
}
