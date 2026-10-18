// Fallbacks so the viewer never crashes on a missing or malformed field.
import type { SpaceObject } from "./types";

export const DEFAULT_SIZE: Record<string, [number, number, number]> = {
  bed: [2.0, 0.6, 1.5], nightstand: [0.45, 0.6, 0.4], sofa: [2.0, 0.85, 0.9], armchair: [0.85, 0.9, 0.85],
  coffee_table: [1.1, 0.45, 0.6], dining_table: [1.6, 0.75, 0.9], chair: [0.45, 0.9, 0.5], desk: [1.2, 0.75, 0.6],
  tv: [1.2, 0.7, 0.06], tv_stand: [1.5, 0.5, 0.4], bookshelf: [0.9, 1.8, 0.35], dresser: [1.2, 1.0, 0.5],
  wardrobe: [1.2, 2.0, 0.6], rug: [2.0, 0.01, 1.4], lamp_floor: [0.35, 1.6, 0.35], lamp_table: [0.25, 0.4, 0.25],
  ceiling_light: [0.3, 0.1, 0.3], plant: [0.45, 1.0, 0.45], toilet: [0.4, 0.76, 0.7], sink: [0.6, 0.86, 0.45],
  bathtub: [1.5, 0.56, 0.75], shower: [0.9, 2.0, 0.9], mirror: [0.6, 0.8, 0.02], stairs: [1.0, 2.5, 3.0],
  outlet: [0.02, 0.11, 0.07], cord: [0.04, 0.02, 1.0], window: [1.0, 1.2, 0.05], door: [0.81, 2.03, 0.05],
  refrigerator: [0.8, 1.8, 0.7], stove: [0.76, 0.91, 0.65], counter: [1.5, 0.91, 0.6], cabinet: [0.8, 0.9, 0.6],
  laptop: [0.35, 0.02, 0.25], painting: [0.8, 0.6, 0.03], clutter: [0.5, 0.3, 0.5],
};

const FALLBACK_SIZE: [number, number, number] = [0.5, 0.5, 0.5];
export const DEFAULT_COLOR = "#cfc6b8";

function vec3(v: unknown, fallback: [number, number, number]): [number, number, number] {
  if (Array.isArray(v) && v.length === 3 && v.every((n) => typeof n === "number" && Number.isFinite(n))) {
    return [v[0], v[1], v[2]];
  }
  return fallback;
}

export function objectSize(o: SpaceObject): [number, number, number] {
  return vec3(o.size, DEFAULT_SIZE[o.type] ?? FALLBACK_SIZE);
}

export function objectPosition(o: SpaceObject): [number, number, number] {
  const [, h] = objectSize(o);
  return vec3(o.position, [0, h / 2, 0]);
}

export function objectColor(o: SpaceObject): string {
  return o.color && /^#[0-9a-f]{3,8}$/i.test(o.color) ? o.color : DEFAULT_COLOR;
}
