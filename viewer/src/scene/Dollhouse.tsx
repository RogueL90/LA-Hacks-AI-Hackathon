// The whole space: lighting, rooms, objects, overlays, camera controls.
import { useMemo } from "react";
import { ContactShadows, OrbitControls } from "@react-three/drei";
import type { OverlaySet, Space } from "../lib/types";
import type { ModePreset } from "../modes/presets";
import { RoomShell } from "./RoomShell";
import { ObjectMesh } from "./ObjectMesh";
import { OverlayLayer } from "../overlays/OverlayLayer";

interface Props {
  space: Space;
  overlaySet: OverlaySet | null;
  preset: ModePreset | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export function spaceBounds(space: Space) {
  const pts = space.rooms.flatMap((r) => r.polygon ?? []);
  const xs = pts.map((p) => p[0]);
  const zs = pts.map((p) => p[1]);
  const minX = Math.min(...xs, 0);
  const maxX = Math.max(...xs, 1);
  const minZ = Math.min(...zs, 0);
  const maxZ = Math.max(...zs, 1);
  return {
    center: [(minX + maxX) / 2, 0, (minZ + maxZ) / 2] as [number, number, number],
    span: Math.max(maxX - minX, maxZ - minZ),
  };
}

export function Dollhouse({ space, overlaySet, preset, selectedId, onSelect }: Props) {
  const { center, span } = useMemo(() => spaceBounds(space), [space]);
  const objectsById = useMemo(() => new Map(space.objects.map((o) => [o.id, o])), [space.objects]);
  const doors = useMemo(() => space.doors ?? [], [space.doors]);
  const night = preset?.night ?? false;

  return (
    <>
      <hemisphereLight args={["#fff8ee", "#d8cfc2", night ? 0.35 : 0.9]} />
      <directionalLight
        position={[center[0] + span * 0.4, span * 1.2, center[2] + span * 0.6]}
        intensity={night ? 0.5 : 1.6}
        color="#ffe9cc"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-span}
        shadow-camera-right={span}
        shadow-camera-top={span}
        shadow-camera-bottom={-span}
      />

      <group onPointerMissed={() => onSelect(null)}>
        {space.rooms.map((room) => (
          <RoomShell key={room.id} room={room} doors={doors} />
        ))}
        {space.objects.map((o) => (
          <ObjectMesh key={o.id} object={o} selected={o.id === selectedId} onSelect={onSelect} />
        ))}
      </group>

      {overlaySet && <OverlayLayer overlays={overlaySet.overlays} objectsById={objectsById} preset={preset} />}

      <ContactShadows position={[center[0], -0.001, center[2]]} scale={span * 1.6} opacity={0.35} blur={2.5} far={4} />
      <OrbitControls target={center} maxPolarAngle={Math.PI / 2.2} minDistance={2} maxDistance={span * 3} makeDefault />
    </>
  );
}
