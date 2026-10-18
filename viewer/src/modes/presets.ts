// Per-mode look and camera behaviour (ADITYA.md §4 "Mode presets").
import type { Mode } from "../lib/types";

export interface ModePreset {
  label: string;
  accent: string;
  camera: "hero" | "first_person" | "toddler" | "orbit" | "flythrough";
  eyeHeightM?: number;
  night?: boolean;
}

export const MODE_PRESETS: Record<Mode, ModePreset> = {
  elder: { label: "Elder Safety", accent: "#E8A33D", camera: "first_person", eyeHeightM: 1.55, night: true },
  baby: { label: "Baby-proofing", accent: "#5BC8A8", camera: "toddler", eyeHeightM: 0.75 },
  interior: { label: "Interior Design", accent: "#C9714F", camera: "orbit" },
  claim: { label: "Insurance Claim", accent: "#2F5D9B", camera: "flythrough" },
};

export const NEUTRAL_ACCENT = "#3A3A3A";

export const THEME = {
  background: "#F6F2EC", // warm off-white
  text: "#2F2F2F", // soft charcoal
  floor: "#E9E2D6",
  wall: "#FBF8F3",
};

export function isMode(value: string | null): value is Mode {
  return value === "elder" || value === "baby" || value === "interior" || value === "claim";
}
