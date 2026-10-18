// Fallbacks so the viewer never crashes on a missing or malformed field.
import type { SpaceObject } from "./types";

export const DEFAULT_SIZE: Record<string, [number, number, number]> = {
  // One entry per type in space_service/pipeline/catalog.py.
  // living room
  sofa: [2.0, 0.85, 0.9],
  sectional_sofa: [2.8, 0.85, 2.0],
  armchair: [0.85, 0.9, 0.85],
  recliner: [0.9, 1.0, 0.95],
  ottoman: [0.6, 0.45, 0.6],
  coffee_table: [1.1, 0.45, 0.6],
  side_table: [0.5, 0.55, 0.5],
  console_table: [1.2, 0.8, 0.35],
  tv: [1.2, 0.7, 0.06],
  tv_stand: [1.5, 0.5, 0.4],
  bookshelf: [0.9, 1.8, 0.35],
  shelf: [0.8, 0.03, 0.25],
  cabinet: [0.8, 0.9, 0.6],
  bench: [1.2, 0.45, 0.4],
  fireplace: [1.5, 1.1, 0.4],
  piano: [1.5, 1.2, 0.6],
  // bedroom
  bed: [2.0, 0.6, 1.5],
  crib: [1.3, 1.0, 0.7],
  nightstand: [0.45, 0.6, 0.4],
  dresser: [1.2, 1.0, 0.5],
  wardrobe: [1.2, 2.0, 0.6],
  vanity: [1.0, 0.76, 0.45],
  changing_table: [0.9, 0.95, 0.5],
  toy_box: [0.8, 0.5, 0.45],
  toys: [0.3, 0.2, 0.3],
  // dining and office
  dining_table: [1.6, 0.75, 0.9],
  chair: [0.45, 0.9, 0.5],
  high_chair: [0.6, 1.05, 0.75],
  stool: [0.4, 0.65, 0.4],
  desk: [1.2, 0.75, 0.6],
  office_chair: [0.65, 1.1, 0.65],
  // kitchen
  counter: [1.5, 0.91, 0.6],
  kitchen_island: [1.8, 0.91, 0.9],
  refrigerator: [0.8, 1.8, 0.7],
  stove: [0.76, 0.91, 0.65],
  oven: [0.76, 0.91, 0.65],
  microwave: [0.5, 0.3, 0.38],
  dishwasher: [0.6, 0.85, 0.6],
  sink: [0.6, 0.86, 0.45],
  range_hood: [0.76, 0.4, 0.5],
  small_appliance: [0.3, 0.35, 0.25],
  trash_can: [0.35, 0.65, 0.35],
  // laundry and utility
  washer: [0.68, 0.85, 0.65],
  dryer: [0.68, 0.85, 0.65],
  water_heater: [0.55, 1.5, 0.55],
  laundry_basket: [0.5, 0.55, 0.35],
  ironing_board: [1.2, 0.9, 0.35],
  // bathroom
  toilet: [0.4, 0.76, 0.7],
  bathtub: [1.5, 0.56, 0.75],
  shower: [0.9, 2.0, 0.9],
  bath_mat: [0.8, 0.01, 0.5],
  towel_rack: [0.6, 0.08, 0.12],
  grab_bar: [0.45, 0.08, 0.08],
  shower_seat: [0.45, 0.45, 0.35],
  // lighting
  light: [0.3, 0.1, 0.3],
  lamp_floor: [0.35, 1.6, 0.35],
  lamp_table: [0.25, 0.4, 0.25],
  // decor
  rug: [2.0, 0.01, 1.4],
  plant: [0.45, 1.0, 0.45],
  painting: [0.8, 0.6, 0.03],
  mirror: [0.6, 0.8, 0.02],
  curtain: [1.4, 2.2, 0.05],
  clock: [0.3, 0.3, 0.05],
  decor: [0.2, 0.25, 0.2],
  // electronics
  laptop: [0.35, 0.02, 0.25],
  monitor: [0.6, 0.4, 0.2],
  computer: [0.2, 0.45, 0.45],
  game_console: [0.3, 0.08, 0.25],
  speaker: [0.2, 0.3, 0.2],
  printer: [0.45, 0.25, 0.4],
  router: [0.25, 0.05, 0.15],
  fan: [0.4, 1.0, 0.4],
  space_heater: [0.35, 0.5, 0.25],
  air_conditioner: [0.8, 0.3, 0.25],
  // building
  window: [1.0, 1.2, 0.05],
  door: [0.81, 2.03, 0.05],
  stairs: [1.0, 2.5, 3.0],
  step: [1.0, 0.18, 0.3],
  handrail: [2.0, 0.06, 0.08],
  radiator: [0.8, 0.6, 0.1],
  outlet: [0.02, 0.11, 0.07],
  light_switch: [0.02, 0.11, 0.07],
  thermostat: [0.02, 0.1, 0.1],
  smoke_detector: [0.12, 0.04, 0.12],
  // safety and mobility
  stair_gate: [0.8, 0.75, 0.05],
  walker: [0.6, 0.85, 0.5],
  wheelchair: [0.65, 0.9, 1.05],
  // storage and misc
  box: [0.5, 0.4, 0.4],
  shoe_rack: [0.8, 0.5, 0.3],
  coat_rack: [0.45, 1.8, 0.45],
  pet_bed: [0.7, 0.2, 0.55],
  bicycle: [1.7, 1.0, 0.5],
  exercise_equipment: [1.8, 1.3, 0.8],
  cord: [0.04, 0.02, 1.0],
  clutter: [0.5, 0.3, 0.5],
  other: [0.5, 0.5, 0.5],
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
