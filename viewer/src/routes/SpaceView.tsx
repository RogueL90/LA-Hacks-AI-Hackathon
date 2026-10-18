// /s/:spaceId?mode=elder&o=ov_123 — loads a Space (+ overlay set) and renders the dollhouse.
import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { fetchOverlaySet, fetchSpace } from "../lib/api";
import { objectSize } from "../lib/defaults";
import type { OverlaySet, Space } from "../lib/types";
import { Dollhouse, spaceBounds } from "../scene/Dollhouse";
import { MODE_PRESETS, THEME, isMode } from "../modes/presets";

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

  const camera = useMemo(() => {
    if (state.status !== "ready") return null;
    const { center, span } = spaceBounds(state.space);
    return { position: [center[0] + span * 0.15, span * 0.95, center[2] + span * 1.05] as [number, number, number] };
  }, [state]);

  if (state.status === "loading") return <div className="status">Loading home…</div>;
  if (state.status === "error") return <div className="status">Couldn't load this home. {state.message}</div>;

  const { space, overlaySet } = state;
  const selected = space.objects.find((o) => o.id === selectedId) ?? null;

  return (
    <div className="viewer" style={{ background: THEME.background }}>
      <Canvas shadows camera={{ position: camera!.position, fov: 40 }} gl={{ preserveDrawingBuffer: isSnapshot }}>
        <Dollhouse
          space={space}
          overlaySet={overlaySet}
          preset={preset}
          selectedId={selectedId}
          onSelect={setSelectedId}
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
        </header>
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
