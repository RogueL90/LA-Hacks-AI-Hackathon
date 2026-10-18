// One room: floor from its polygon + cut-away walls (~70% of ceiling height) with door openings.
import { useMemo } from "react";
import * as THREE from "three";
import type { Door, Room } from "../lib/types";
import { THEME } from "../modes/presets";

const WALL_THICKNESS = 0.08;
const WALL_CUTAWAY = 0.7;
const DOOR_ON_WALL_M = 0.3; // a door this close to a wall segment cuts an opening in it
const MIN_PIECE_M = 0.02;

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

export function RoomShell({ room, doors }: { room: Room; doors: Door[] }) {
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
    const height = (room.height_m ?? 2.5) * WALL_CUTAWAY;
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
  }, [points, room.height_m, doors]);

  if (!floorShape) return null;

  return (
    <group name={room.id}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <shapeGeometry args={[floorShape]} />
        <meshStandardMaterial color={THEME.floor} roughness={0.9} />
      </mesh>
      {walls.map((w) => (
        <mesh key={w.key} position={w.position} rotation={[0, w.rotationY, 0]} castShadow receiveShadow>
          <boxGeometry args={[w.length, w.height, WALL_THICKNESS]} />
          <meshStandardMaterial color={THEME.wall} roughness={0.95} />
        </mesh>
      ))}
    </group>
  );
}
