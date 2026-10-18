// Object type -> CC0 Poly Haven glTF model (public/models, fetched by scripts/fetch_assets.py).
// Types not listed here are drawn procedurally (Procedural.tsx).
import type { SpaceObject } from "../lib/types";

export type Fit =
  | "stretch" // scale each axis to the object's measured size
  | "uniform_height" // keep proportions, match height (plants look absurd stretched)
  | "uniform_width"; // keep proportions, match width (pendant lamps)

export interface ModelEntry {
  url: string;
  fit: Fit;
  yaw?: number; // radians; turns the model so its front faces +z and its width runs along x
  anchor?: "bottom" | "top"; // "top" hangs from the top of the object's box (ceiling lights)
}

const m = (id: string, fit: Fit = "stretch", extra: Partial<ModelEntry> = {}): ModelEntry => ({
  url: `/models/${id}.glb`,
  fit,
  ...extra,
});

export const MODEL_CATALOG: Record<string, ModelEntry> = {
  sofa: m("Sofa_01"),
  armchair: m("modern_arm_chair_01"),
  coffee_table: m("modern_coffee_table_01", "stretch", { yaw: Math.PI / 2 }),
  dining_table: m("wooden_table_02"),
  chair: m("dining_chair_02"),
  desk: m("metal_office_desk"),
  tv_stand: m("modern_wooden_cabinet"),
  bookshelf: m("wooden_display_shelves_01", "stretch", { yaw: Math.PI / 2 }),
  dresser: m("drawer_cabinet"),
  wardrobe: m("vintage_cabinet_01"),
  nightstand: m("side_table_01"),
  cabinet: m("painted_wooden_cabinet"),
  stove: m("electric_stove"),
  painting: m("fancy_picture_frame_01"),
  plant: m("potted_plant_02", "uniform_height"),
  ceiling_light: m("modern_ceiling_lamp_01", "uniform_width", { anchor: "top" }),
};
// Close relatives share a model.
Object.assign(MODEL_CATALOG, {
  light: MODEL_CATALOG.ceiling_light, // fixed fixtures; the prebuilt demo uses it too
  sectional_sofa: MODEL_CATALOG.sofa,
  recliner: MODEL_CATALOG.armchair,
  office_chair: MODEL_CATALOG.chair,
  side_table: MODEL_CATALOG.nightstand,
  console_table: m("wooden_table_02"),
  stool: m("metal_stool_02"),
  ottoman: m("Ottoman_01"),
});

// A round table stretched into a rectangle (or the reverse) looks wrong, so the footprint
// shape the extractor reports (attributes.shape) picks between models.
const ROUND_MODELS: Record<string, ModelEntry> = {
  dining_table: m("round_wooden_table_01"),
  coffee_table: m("coffee_table_round_01"),
  side_table: m("coffee_table_round_01"),
};

export function modelFor(object: SpaceObject): ModelEntry | undefined {
  const shape = object.attributes?.shape;
  if ((shape === "round" || shape === "oval") && ROUND_MODELS[object.type]) return ROUND_MODELS[object.type];
  return MODEL_CATALOG[object.type];
}

export const ALL_MODELS = [...Object.values(MODEL_CATALOG), ...Object.values(ROUND_MODELS)];
