// PBR texture sets (public/textures, CC0 Poly Haven) and shared material presets.
//
// Every textured geometry in the viewer has UVs in meters (ShapeGeometry floors already
// do; boxes use meterBox below), so one texture instance can be shared everywhere and
// its repeat is simply 1 / the texture's real-world size.
import { useMemo } from "react";
import * as THREE from "three";
import { useTexture } from "@react-three/drei";

// Real-world size of one texture tile, in meters (from the Poly Haven asset info).
export const TEXTURES = {
  woodFloor: { id: "laminate_floor_02", tileM: 1.7 },
  tileFloor: { id: "floor_tiles_06", tileM: 1.5 },
  plaster: { id: "plastered_wall_04", tileM: 3.2 },
  fabric: { id: "fabric_pattern_07", tileM: 0.4 },
  oak: { id: "oak_veneer_01", tileM: 1.83 },
} as const;
export type TextureKey = keyof typeof TEXTURES;

export interface PbrMaps {
  map: THREE.Texture;
  normalMap: THREE.Texture;
  roughnessMap: THREE.Texture;
}

export function usePbr(key: TextureKey): PbrMaps {
  const { id, tileM } = TEXTURES[key];
  const maps = useTexture({
    map: `/textures/${id}/diff.jpg`,
    normalMap: `/textures/${id}/nor_gl.jpg`,
    roughnessMap: `/textures/${id}/rough.jpg`,
  }) as PbrMaps;
  useMemo(() => {
    for (const t of Object.values(maps)) {
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.repeat.set(1 / tileM, 1 / tileM);
      t.anisotropy = 8;
    }
    maps.map.colorSpace = THREE.SRGBColorSpace; // colour data only; normal/roughness stay linear
  }, [maps, tileM]);
  return maps;
}

/** Box whose UVs are in meters on every face, so tiled textures keep their real-world size. */
export function meterBox(w: number, h: number, d: number): THREE.BoxGeometry {
  const geo = new THREE.BoxGeometry(w, h, d);
  const uv = geo.attributes.uv as THREE.BufferAttribute;
  // BoxGeometry face order: +x, -x, +y, -y, +z, -z; 4 vertices each. [u span, v span] per face:
  const spans: [number, number][] = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]];
  spans.forEach(([su, sv], face) => {
    for (let i = face * 4; i < face * 4 + 4; i++) uv.setXY(i, uv.getX(i) * su, uv.getY(i) * sv);
  });
  uv.needsUpdate = true;
  return geo;
}

/** Plane lying flat (XZ) with meter UVs. */
export function meterPlane(w: number, d: number): THREE.PlaneGeometry {
  const geo = new THREE.PlaneGeometry(w, d);
  const uv = geo.attributes.uv as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * w, uv.getY(i) * d);
  uv.needsUpdate = true;
  geo.rotateX(-Math.PI / 2);
  return geo;
}

// Untextured presets for the procedural fixtures.
export const SURFACES = {
  ceramic: { color: "#f3f2ee", roughness: 0.12, metalness: 0 },
  metal: { color: "#c8cbcf", roughness: 0.32, metalness: 0.9 },
  darkMetal: { color: "#2b2d30", roughness: 0.4, metalness: 0.8 },
  glossyBlack: { color: "#0c0c0e", roughness: 0.12, metalness: 0.2 },
  plastic: { color: "#f1efe9", roughness: 0.45, metalness: 0 },
  rubber: { color: "#1a1a1a", roughness: 0.8, metalness: 0 },
  stone: { color: "#e6e1d8", roughness: 0.3, metalness: 0 },
  mirror: { color: "#ffffff", roughness: 0.02, metalness: 1 },
  linen: { color: "#f4f1ea", roughness: 0.9, metalness: 0 },
} as const;
export type Surface = keyof typeof SURFACES;
