// Object type -> CC0 Poly Haven glTF model (public/models, fetched by scripts/fetch_assets.py).
// Types not listed here are drawn procedurally (Procedural.tsx).

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
  dining_table: m("round_wooden_table_01"),
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
MODEL_CATALOG.light = MODEL_CATALOG.ceiling_light; // the prebuilt demo uses "light"
