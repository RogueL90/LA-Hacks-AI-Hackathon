// Walk-through mode (like Street View): the camera stands at eye height inside the house,
// steps forward/back and turns in fixed increments, and can only pass walls at doorways.
// Inputs arrive through a shared mutable WalkInput (on-screen buttons and keys live outside
// the Canvas); drag on the canvas to look around.
import { useEffect, useMemo, useRef, type MutableRefObject } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import type { Door, Room } from "../lib/types";

export type WalkCmd = "forward" | "back" | "left" | "right";
export interface WalkInput {
  queue: WalkCmd[];
  held: WalkCmd | null; // a held button repeats
}
/** Where to stand and which way to face; a new `key` restarts the move there. */
export interface WalkEntry {
  x: number;
  z: number;
  yaw: number;
  key: number;
}

export const EYE_M = 1.6;
const STEP_M = 0.7;
const TURN_RAD = Math.PI / 6;
const REPEAT_S = 0.3;
const MARGIN_M = 0.25; // how close to a wall you can stand
const DOOR_EDGE_M = 0.12; // keep clear of the door frame
const WALK_FOV = 70;
const DOLLHOUSE_FOV = 40;
const LOOK_RAD_PER_PX = 0.004;
const MAX_PITCH = 0.6;

interface Rect {
  name: string;
  x0: number;
  z0: number;
  x1: number;
  z1: number;
}
interface Gap {
  wallAlongZ: boolean; // the wall is the line x = c (true) or z = c (false)
  c: number;
  lo: number;
  hi: number;
}
export interface WalkBounds {
  rects: Rect[];
  gaps: Gap[];
}

export function walkBounds(rooms: Room[], doors: Door[]): WalkBounds {
  const rects = rooms
    .filter((r) => (r.polygon ?? []).length >= 3)
    .map((r) => {
      const xs = r.polygon.map((p) => p[0]);
      const zs = r.polygon.map((p) => p[1]);
      return { name: r.name, x0: Math.min(...xs), z0: Math.min(...zs), x1: Math.max(...xs), z1: Math.max(...zs) };
    });
  const gaps = doors.flatMap((d) => {
    const [x, , z] = d.position ?? [];
    if (!Number.isFinite(x) || !Number.isFinite(z) || rects.length === 0) return [];
    // Which wall is the door in? The nearest room edge decides.
    const dx = Math.min(...rects.map((r) => Math.min(Math.abs(x - r.x0), Math.abs(x - r.x1))));
    const dz = Math.min(...rects.map((r) => Math.min(Math.abs(z - r.z0), Math.abs(z - r.z1))));
    const half = d.width_m / 2;
    return dx <= dz
      ? [{ wallAlongZ: true, c: x, lo: z - half, hi: z + half }]
      : [{ wallAlongZ: false, c: z, lo: x - half, hi: x + half }];
  });
  return { rects, gaps };
}

export function roomAt(b: WalkBounds, x: number, z: number): Rect | undefined {
  return b.rects.find((r) => x >= r.x0 && x <= r.x1 && z >= r.z0 && z <= r.z1);
}

function passable(b: WalkBounds, x: number, z: number): boolean {
  if (b.rects.some((r) => x > r.x0 + MARGIN_M && x < r.x1 - MARGIN_M && z > r.z0 + MARGIN_M && z < r.z1 - MARGIN_M)) {
    return true;
  }
  // The band along a wall is blocked except where a door or open side cuts through it.
  return b.gaps.some((g) => {
    const [across, along] = g.wallAlongZ ? [x, z] : [z, x];
    return Math.abs(across - g.c) < MARGIN_M + 0.05 && along > g.lo + DOOR_EDGE_M && along < g.hi - DOOR_EDGE_M;
  });
}

function canMove(b: WalkBounds, x0: number, z0: number, x1: number, z1: number): boolean {
  const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, z1 - z0) / 0.05));
  for (let i = 1; i <= n; i++) {
    if (!passable(b, x0 + ((x1 - x0) * i) / n, z0 + ((z1 - z0) * i) / n)) return false;
  }
  return true;
}

/** A clicked point may be hard against a wall; pull it toward the room centre until it is standable. */
export function standablePoint(b: WalkBounds, x: number, z: number): [number, number] | null {
  const r = roomAt(b, x, z);
  if (!r) return null;
  const cx = (r.x0 + r.x1) / 2;
  const cz = (r.z0 + r.z1) / 2;
  for (let t = 0; t <= 1; t += 0.05) {
    const px = x + (cx - x) * t;
    const pz = z + (cz - z) * t;
    if (passable(b, px, pz)) return [px, pz];
  }
  return null;
}

/** Yaw that faces from (fx, fz) toward (tx, tz); the camera looks down its own -z. */
export function yawToward(fx: number, fz: number, tx: number, tz: number): number {
  return Math.atan2(-(tx - fx), -(tz - fz));
}

const damp = (from: number, to: number, dt: number, rate = 7) => from + (to - from) * (1 - Math.exp(-dt * rate));

function wrapAngle(a: number): number {
  return Math.atan2(Math.sin(a), Math.cos(a));
}

interface Props {
  bounds: WalkBounds;
  entry: WalkEntry;
  input: MutableRefObject<WalkInput>;
  onRoomChange: (name: string | null) => void;
}

export function WalkControls({ bounds, entry, input, onRoomChange }: Props) {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const gl = useThree((s) => s.gl);
  const target = useRef({ x: entry.x, z: entry.z, yaw: entry.yaw, pitch: 0 });
  const pose = useRef({ yaw: 0, pitch: 0 });
  const lastStep = useRef(0);
  const lastRoom = useRef<string | null>(null);

  // Start from wherever the camera is now, so entering is a glide rather than a jump.
  const euler = useMemo(() => new THREE.Euler(0, 0, 0, "YXZ"), []);
  useEffect(() => {
    euler.setFromQuaternion(camera.quaternion, "YXZ");
    pose.current = { yaw: euler.y, pitch: euler.x };
    // Turn the short way round.
    target.current = { x: entry.x, z: entry.z, yaw: euler.y + wrapAngle(entry.yaw - euler.y), pitch: 0 };
  }, [entry.key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    camera.fov = WALK_FOV;
    camera.updateProjectionMatrix();
    return () => {
      camera.fov = DOLLHOUSE_FOV;
      camera.updateProjectionMatrix();
    };
  }, [camera]);

  // Drag to look around.
  useEffect(() => {
    const el = gl.domElement;
    let last: { x: number; y: number } | null = null;
    const down = (e: PointerEvent) => (last = { x: e.clientX, y: e.clientY });
    const move = (e: PointerEvent) => {
      if (!last) return;
      target.current.yaw += (e.clientX - last.x) * LOOK_RAD_PER_PX;
      target.current.pitch = THREE.MathUtils.clamp(target.current.pitch + (e.clientY - last.y) * LOOK_RAD_PER_PX, -MAX_PITCH, MAX_PITCH);
      last = { x: e.clientX, y: e.clientY };
    };
    const up = () => (last = null);
    el.addEventListener("pointerdown", down);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      el.removeEventListener("pointerdown", down);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [gl]);

  useFrame((state, dt) => {
    const t = target.current;
    const inp = input.current;
    if (inp.held && state.clock.elapsedTime - lastStep.current > REPEAT_S) inp.queue.push(inp.held);
    while (inp.queue.length) {
      const cmd = inp.queue.shift()!;
      lastStep.current = state.clock.elapsedTime;
      if (cmd === "left") t.yaw += TURN_RAD;
      else if (cmd === "right") t.yaw -= TURN_RAD;
      else {
        const dir = cmd === "forward" ? 1 : -1;
        const nx = t.x - Math.sin(t.yaw) * STEP_M * dir;
        const nz = t.z - Math.cos(t.yaw) * STEP_M * dir;
        if (canMove(bounds, t.x, t.z, nx, nz)) {
          t.x = nx;
          t.z = nz;
        }
      }
    }

    camera.position.set(
      damp(camera.position.x, t.x, dt),
      damp(camera.position.y, EYE_M, dt),
      damp(camera.position.z, t.z, dt),
    );
    pose.current.yaw = damp(pose.current.yaw, t.yaw, dt, 9);
    pose.current.pitch = damp(pose.current.pitch, t.pitch, dt, 9);
    euler.set(pose.current.pitch, pose.current.yaw, 0, "YXZ");
    camera.quaternion.setFromEuler(euler);

    const room = roomAt(bounds, camera.position.x, camera.position.z)?.name ?? null;
    if (room !== lastRoom.current) {
      lastRoom.current = room;
      onRoomChange(room);
    }
  });

  return null;
}
