// The whole space: lighting, rooms, objects, overlays, camera controls, post-processing.
import { Suspense, useEffect, useMemo, type MutableRefObject } from "react";
import { useThree } from "@react-three/fiber";
import { Environment, OrbitControls, SoftShadows } from "@react-three/drei";
import { EffectComposer, N8AO, SMAA, ToneMapping } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import type { OverlaySet, Space } from "../lib/types";
import { NEUTRAL_ACCENT, type ModePreset } from "../modes/presets";
import { RoomShell } from "./RoomShell";
import {
  WalkControls,
  roomAt,
  standablePoint,
  walkBounds,
  yawToward,
  type WalkEntry,
  type WalkInput,
} from "./WalkControls";
import { ObjectMesh } from "./ObjectMesh";
import { OverlayLayer } from "../overlays/OverlayLayer";

interface Props {
  space: Space;
  overlaySet: OverlaySet | null;
  preset: ModePreset | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** Walk-through mode: where to stand, or null for the dollhouse view. */
  walk: WalkEntry | null;
  walkInput: MutableRefObject<WalkInput>;
  /** A floor was clicked: start walking there (or move there if already walking). */
  onWalk: (entry: WalkEntry) => void;
  onWalkRoom: (name: string | null) => void;
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

/** Re-frames the camera when the visible floor changes (the Canvas only sets it once on mount). */
function FitCamera({ center, span, walking }: { center: [number, number, number]; span: number; walking: boolean }) {
  const camera = useThree((s) => s.camera);
  const [cx, , cz] = center;
  useEffect(() => {
    if (walking) return; // also re-frames when a walk ends
    camera.position.set(cx + span * 0.15, span * 0.95, cz + span * 1.05);
    camera.lookAt(cx, 0, cz);
  }, [camera, cx, cz, span, walking]);
  return null;
}

/** Floor click -> a standing spot facing into the room (toward its far side, never a wall). */
function useFloorWalk(bounds: ReturnType<typeof walkBounds>, onWalk: (e: WalkEntry) => void) {
  const camera = useThree((s) => s.camera);
  return (x: number, z: number) => {
    const spot = standablePoint(bounds, x, z);
    const room = spot && roomAt(bounds, spot[0], spot[1]);
    if (!spot || !room) return;
    const cx = (room.x0 + room.x1) / 2;
    const cz = (room.z0 + room.z1) / 2;
    // Near the middle of the room, keep looking the way the camera already was.
    const nearCentre = Math.hypot(spot[0] - cx, spot[1] - cz) < 0.6;
    const yaw = nearCentre
      ? yawToward(camera.position.x, camera.position.z, spot[0], spot[1])
      : yawToward(spot[0], spot[1], cx, cz);
    onWalk({ x: spot[0], z: spot[1], yaw, key: performance.now() });
  };
}

export function Dollhouse({ space, overlaySet, preset, selectedId, onSelect, walk, walkInput, onWalk, onWalkRoom }: Props) {
  const { center, span } = useMemo(() => spaceBounds(space), [space]);
  const objectsById = useMemo(() => new Map(space.objects.map((o) => [o.id, o])), [space.objects]);
  const doors = useMemo(() => space.doors ?? [], [space.doors]);
  const roomsById = useMemo(() => new Map(space.rooms.map((r) => [r.id, r])), [space.rooms]);
  const night = preset?.night ?? false;
  const accent = preset?.accent ?? NEUTRAL_ACCENT;
  const walking = walk !== null;
  const bounds = useMemo(() => walkBounds(space.rooms, doors), [space.rooms, doors]);
  const floorWalk = useFloorWalk(bounds, onWalk);

  return (
    <>
      {/* Image-based light from a real interior (CC0 Poly Haven HDRI); the page background stays ours. */}
      <Suspense fallback={null}>
        <Environment files="/hdri/lythwood_room.hdr" environmentIntensity={night ? 0.18 : 0.75} />
      </Suspense>
      <hemisphereLight args={["#fff8ee", "#d8cfc2", night ? 0.05 : 0.15]} />
      {/* The sun: the environment light casts no shadows, this one does. */}
      <directionalLight
        position={[center[0] + span * 0.4, span * 1.2, center[2] + span * 0.6]}
        intensity={night ? 0.35 : 1.3}
        color="#ffe9cc"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-span}
        shadow-camera-right={span}
        shadow-camera-top={span}
        shadow-camera-bottom={-span}
      />

      <FitCamera center={center} span={span} walking={walking} />
      {walk && <WalkControls bounds={bounds} entry={walk} input={walkInput} onRoomChange={onWalkRoom} />}
      <SoftShadows size={18} samples={12} focus={0.6} />

      <group onPointerMissed={() => onSelect(null)}>
        <Suspense fallback={null}>
          {space.rooms.map((room) => (
            <RoomShell key={room.id} room={room} doors={doors} walking={walking} onFloorClick={floorWalk} />
          ))}
        </Suspense>
        {space.objects.map((o) => (
          <ObjectMesh
            key={o.id}
            object={o}
            room={roomsById.get(o.room_id)}
            selected={o.id === selectedId}
            night={night}
            accent={accent}
            walking={walking}
            onSelect={onSelect}
          />
        ))}
      </group>

      {overlaySet && <OverlayLayer overlays={overlaySet.overlays} objectsById={objectsById} preset={preset} />}

      {/* Ground that only shows the house's real shadow (ContactShadows drew stray blobs with SoftShadows). */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[center[0], -0.002, center[2]]} receiveShadow>
        <planeGeometry args={[span * 3, span * 3]} />
        <shadowMaterial opacity={0.16} />
      </mesh>
      <OrbitControls
        enabled={!walking}
        target={center}
        maxPolarAngle={Math.PI / 2.2}
        minDistance={2}
        maxDistance={span * 3}
        makeDefault
      />

      {/* MSAA off: it conflicts with N8AO, and SMAA handles the edges. */}
      <EffectComposer multisampling={0}>
        <N8AO halfRes aoRadius={0.6} distanceFalloff={1} intensity={2.5} quality="medium" />
        <ToneMapping mode={ToneMappingMode.AGX} />
        <SMAA />
      </EffectComposer>
    </>
  );
}
