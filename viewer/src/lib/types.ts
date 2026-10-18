// TypeScript mirror of the shared contracts (MASTER.md §5). Units: meters; x right, y up, z forward.

export type Mode = "elder" | "baby" | "interior" | "claim";

export interface Evidence {
  frame_url?: string | null;
  timestamp_s?: number | null;
  note?: string | null;
}

export interface SpaceObject {
  id: string;
  type: string;
  label: string;
  room_id: string;
  position: number[]; // [x, y, z] center
  size: number[]; // [w, h, d]
  rotation_y?: number;
  color?: string | null;
  material?: string | null;
  attributes?: Record<string, unknown>;
  confidence?: number;
  evidence?: Evidence[];
}

export interface Door {
  id: string;
  room_id: string;
  position: number[];
  width_m: number;
  kind?: "door" | "doorway" | "open"; // "open": no wall between the rooms (open-plan)
}

export interface Room {
  id: string;
  name: string;
  polygon: number[][]; // [[x, z], ...]
  height_m?: number;
  level?: number; // 0 = entry floor, 1 = upstairs, -1 = basement
  floor_material?: string | null; // wood | laminate | vinyl | tile | stone | carpet | concrete
}

export interface Space {
  space_id: string;
  source_type: "video" | "photos";
  rooms: Room[];
  doors?: Door[];
  objects: SpaceObject[];
  scale_method: string;
  scale_confidence: number;
  viewer_url: string;
  snapshot_url: string;
}

export type OverlayType = "pin" | "path" | "ghost_object" | "tag" | "highlight" | "camera";

export interface Overlay {
  type: OverlayType;
  data: Record<string, any>;
}

export interface OverlaySet {
  mode: Mode;
  overlays: Overlay[];
}
