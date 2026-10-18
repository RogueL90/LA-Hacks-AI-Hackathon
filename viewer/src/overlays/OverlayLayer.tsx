// Dispatches each Overlay (ADITYA.md §4 table) to its renderer.
import type { Overlay, SpaceObject } from "../lib/types";
import type { ModePreset } from "../modes/presets";
import { NEUTRAL_ACCENT } from "../modes/presets";
import { Pin } from "./Pin";
import { Path } from "./Path";
import { GhostObject } from "./GhostObject";
import { Tag } from "./Tag";
import { Highlight } from "./Highlight";
import { CameraRig } from "./CameraRig";

export interface OverlayProps {
  data: Record<string, any>;
  objectsById: Map<string, SpaceObject>;
  accent: string;
}

const RENDERERS: Record<Overlay["type"], (p: OverlayProps) => JSX.Element | null> = {
  pin: Pin,
  path: Path,
  ghost_object: GhostObject,
  tag: Tag,
  highlight: Highlight,
  camera: CameraRig,
};

interface Props {
  overlays: Overlay[];
  objectsById: Map<string, SpaceObject>;
  preset: ModePreset | null;
}

export function OverlayLayer({ overlays, objectsById, preset }: Props) {
  const accent = preset?.accent ?? NEUTRAL_ACCENT;
  return (
    <group name="overlays">
      {overlays.map((overlay, i) => {
        const Renderer = RENDERERS[overlay.type];
        return Renderer ? (
          <Renderer key={i} data={overlay.data ?? {}} objectsById={objectsById} accent={accent} />
        ) : null;
      })}
    </group>
  );
}
