// One room: floor from its polygon + cut-away walls (~70% of ceiling height) with door openings.
// While walking through the house the walls go full height and the room gets a ceiling.
import { useMemo } from "react";
import type { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { Door, Room } from "../lib/types";
import { meterBox, usePbr, type TextureKey } from "./materials";

const WALL_THICKNESS = 0.08;
const WALL_CUTAWAY = 0.7;
const DOOR_ON_WALL_M = 0.3; // a door this close to a wall segment cuts an opening in it
const MIN_PIECE_M = 0.02;
const PLASTER_NORMAL_SCALE = new THREE.Vector2(0.5, 0.5);
const CARPET_NORMAL_SCALE = new THREE.Vector2(0.35, 0.35);

// Doors live on Space, not Room: a door on a shared wall must cut both rooms' walls,
// so they are matched to wall segments by geometry rather than by room_id.
function openings(x1: number, z1: number, x2: number, z2: number, length: number, doors: Door[]) {
  const ux = (x2 - x1) / length;
  const uz = (z2 - z1) / length;
  const gaps: [number, number][] = [];
  for (const door of doors) {
    const [dx, , dz] = door.position ?? [];
    if (!Number.isFinite(dx) || !Number.isFinite(dz) || !(door.width_m > 0)) continue;
    const t = (dx - x1) * ux + (dz - z1) * uz;
    const perp = Math.abs((dx - x1) * uz - (dz - z1) * ux);
    if (perp > DOOR_ON_WALL_M || t < 0 || t > length) continue;
    gaps.push([Math.max(0, t - door.width_m / 2), Math.min(length, t + door.width_m / 2)]);
  }
  return gaps.sort((a, b) => a[0] - b[0]);
}

function solidPieces(length: number, gaps: [number, number][]) {
  const pieces: [number, number][] = [];
  let start = 0;
  for (const [a, b] of gaps) {
    if (a - start > MIN_PIECE_M) pieces.push([start, a]);
    start = Math.max(start, b);
  }
  if (length - start > MIN_PIECE_M) pieces.push([start, length]);
  return pieces;
}

type FloorKind = "wood" | "tile" | "carpet" | "concrete";

/** The detected floor material; rooms without one (the prebuilt demo) guess from their name. */
function floorFor(room: Room): FloorKind {
  switch (room.floor_material) {
    case "wood":
    case "laminate":
    case "vinyl":
      return "wood";
    case "tile":
    case "stone":
      return "tile";
    case "carpet":
      return "carpet";
    case "concrete":
      return "concrete";
  }
  return /bath|kitchen|laundry|toilet|wc|shower/i.test(`${room.name} ${room.id}`) ? "tile" : "wood";
}

function TexturedFloor({ texture }: { texture: TextureKey }) {
  const { map, normalMap, roughnessMap } = usePbr(texture);
  return <meshStandardMaterial map={map} normalMap={normalMap} roughnessMap={roughnessMap} />;
}

function CarpetFloor() {
  // Carpet = the fabric weave as surface relief on a soft grey.
  const { normalMap, roughnessMap } = usePbr("fabric");
  return <meshStandardMaterial color="#c4bdb2" normalMap={normalMap} roughnessMap={roughnessMap} normalScale={CARPET_NORMAL_SCALE} />;
}

function FloorMaterial({ kind }: { kind: FloorKind }) {
  if (kind === "carpet") return <CarpetFloor />;
  if (kind === "concrete") return <meshStandardMaterial color="#bdb9b2" roughness={0.85} />;
  return <TexturedFloor texture={kind === "tile" ? "tileFloor" : "woodFloor"} />;
}

interface WallProps {
  length: number;
  height: number;
  position: [number, number, number];
  rotationY: number;
  castShadow: boolean;
}

function Wall({ length, height, position, rotationY, castShadow }: WallProps) {
  const plaster = usePbr("plaster");
  const geometry = useMemo(() => meterBox(length, height, WALL_THICKNESS), [length, height]);
  return (
    <mesh geometry={geometry} position={position} rotation={[0, rotationY, 0]} castShadow={castShadow} receiveShadow>
      {/* Plaster relief only: the texture's own grey colour made the walls look dirty. */}
      <meshStandardMaterial
        normalMap={plaster.normalMap}
        roughnessMap={plaster.roughnessMap}
        color="#fbf8f3"
        normalScale={PLASTER_NORMAL_SCALE}
      />
    </mesh>
  );
}

interface Props {
  room: Room;
  doors: Door[];
  walking?: boolean;
  /** Click on the floor (not a drag): world x, z of the point. */
  onFloorClick?: (x: number, z: number) => void;
}

/** r3f reports how far the pointer moved between down and up; more than this is a drag. */
const CLICK_MAX_PX = 5;

export function RoomShell({ room, doors, walking = false, onFloorClick }: Props) {
  const points = useMemo(
    () => (room.polygon ?? []).filter((p) => Array.isArray(p) && p.length >= 2) as [number, number][],
    [room.polygon],
  );

  const floorShape = useMemo(() => {
    if (points.length < 3) return null;
    // Shape lives in XY; rotating -90deg about X maps (x, -z) -> world (x, 0, z).
    return new THREE.Shape(points.map(([x, z]) => new THREE.Vector2(x, -z)));
  }, [points]);

  const walls = useMemo(() => {
    const height = (room.height_m ?? 2.5) * (walking ? 1 : WALL_CUTAWAY);
    return points.flatMap(([x1, z1], i) => {
      const [x2, z2] = points[(i + 1) % points.length];
      const length = Math.hypot(x2 - x1, z2 - z1);
      if (length < MIN_PIECE_M) return [];
      const ux = (x2 - x1) / length;
      const uz = (z2 - z1) / length;
      const rotationY = Math.atan2(-(z2 - z1), x2 - x1);
      return solidPieces(length, openings(x1, z1, x2, z2, length, doors)).map(([a, b], j) => {
        // Pieces touching a corner overlap the neighbouring wall by half a thickness.
        const from = a === 0 ? -WALL_THICKNESS / 2 : a;
        const to = b === length ? length + WALL_THICKNESS / 2 : b;
        const mid = (from + to) / 2;
        return {
          key: `${i}-${j}`,
          length: to - from,
          height,
          position: [x1 + ux * mid, height / 2, z1 + uz * mid] as [number, number, number],
          rotationY,
        };
      });
    });
  }, [points, room.height_m, doors, walking]);

  if (!floorShape) return null;

  return (
    <group name={room.id}>
      {/* ShapeGeometry UVs are the shape's coordinates in meters, so tiling is real-world sized. */}
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        receiveShadow
        onClick={(e: ThreeEvent<MouseEvent>) => {
          if (!onFloorClick || e.delta > CLICK_MAX_PX) return;
          e.stopPropagation();
          onFloorClick(e.point.x, e.point.z);
        }}
      >
        <shapeGeometry args={[floorShape]} />
        <FloorMaterial kind={floorFor(room)} />
      </mesh>
      {walking && (
        // Same shape as the floor, seen from below.
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, room.height_m ?? 2.5, 0]}>
          <shapeGeometry args={[floorShape]} />
          <meshStandardMaterial color="#fbf9f5" roughness={0.95} side={THREE.BackSide} />
        </mesh>
      )}
      {/* Full-height walls would shade the whole interior from the sun, so they cast no shadow. */}
      {walls.map(({ key, ...w }) => (
        <Wall key={key} {...w} castShadow={!walking} />
      ))}
    </group>
  );
}
