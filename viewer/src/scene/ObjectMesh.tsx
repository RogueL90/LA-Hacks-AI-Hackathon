// One SpaceObject: a catalog glTF model when one exists, otherwise a procedural fixture.
// While a model loads, the old tinted box stands in for it.
import { Suspense, useState } from "react";
import { Html } from "@react-three/drei";
import type { Room, SpaceObject } from "../lib/types";
import { objectColor, objectPosition, objectSize } from "../lib/defaults";
import { modelFor } from "./catalog";
import { GltfModel } from "./GltfModel";
import { ProceduralObject } from "./Procedural";

interface Props {
  object: SpaceObject;
  room: Room | undefined;
  selected: boolean;
  night: boolean;
  accent: string;
  walking?: boolean;
  onSelect: (id: string) => void;
}

/** A bed's headboard goes on whichever end of its length is closer to a wall of its room. */
function bedHeadSign(object: SpaceObject, room: Room | undefined): 1 | -1 {
  const pts = room?.polygon ?? [];
  if (pts.length < 3) return -1;
  const [w, , d] = objectSize(object);
  const [x, , z] = objectPosition(object);
  const r = object.rotation_y ?? 0;
  // Direction of the bed's own +length axis in world XZ (see Bed in Procedural.tsx).
  const [lx, lz] = w > d ? [-1, 0] : [0, 1];
  const dx = lx * Math.cos(r) + lz * Math.sin(r);
  const dz = -lx * Math.sin(r) + lz * Math.cos(r);
  const half = Math.max(w, d) / 2;
  const xs = pts.map((p) => p[0]);
  const zs = pts.map((p) => p[1]);
  const wallDist = (px: number, pz: number) =>
    Math.min(px - Math.min(...xs), Math.max(...xs) - px, pz - Math.min(...zs), Math.max(...zs) - pz);
  return wallDist(x + dx * half, z + dz * half) < wallDist(x - dx * half, z - dz * half) ? 1 : -1;
}

function FallbackBox({ size, color }: { size: [number, number, number]; color: string }) {
  return (
    <mesh castShadow receiveShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial color={color} roughness={0.7} />
    </mesh>
  );
}

export function ObjectMesh({ object, room, selected, night, accent, walking = false, onSelect }: Props) {
  const [hovered, setHovered] = useState(false);
  const size = objectSize(object);
  const position = objectPosition(object);
  const color = objectColor(object);
  const entry = modelFor(object);
  const ringRadius = Math.hypot(size[0], size[2]) / 2 + 0.08;

  return (
    <group
      position={position}
      rotation={[0, object.rotation_y ?? 0, 0]}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(object.id);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHovered(true);
      }}
      onPointerOut={() => setHovered(false)}
    >
      <Suspense fallback={<FallbackBox size={size} color={color} />}>
        {entry ? (
          <GltfModel entry={entry} size={size} />
        ) : (
          <ProceduralObject
            type={object.type}
            size={size}
            color={color}
            night={night}
            headSign={object.type === "bed" ? bedHeadSign(object, room) : undefined}
          />
        )}
      </Suspense>

      {(hovered || selected) && (
        // Textured models can't simply glow, so selection is a ring on the floor under the object.
        <mesh position={[0, -position[1] + 0.012, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[ringRadius, ringRadius + (selected ? 0.05 : 0.03), 64]} />
          <meshBasicMaterial color={accent} transparent opacity={selected ? 0.95 : 0.6} toneMapped={false} />
        </mesh>
      )}
      {(hovered || selected) && (
        // Distance-scaled labels suit the dollhouse view; up close in a walk they'd fill the screen.
        <Html position={[0, size[1] / 2 + 0.15, 0]} center distanceFactor={walking ? undefined : 8} zIndexRange={[10, 0]}>
          <div className="object-label">{object.label}</div>
        </Html>
      )}
    </group>
  );
}
