// One SpaceObject as a tinted box (glTF models from the catalog replace this later).
import { useState } from "react";
import { Html } from "@react-three/drei";
import type { SpaceObject } from "../lib/types";
import { objectColor, objectPosition, objectSize } from "../lib/defaults";

interface Props {
  object: SpaceObject;
  selected: boolean;
  onSelect: (id: string) => void;
}

export function ObjectMesh({ object, selected, onSelect }: Props) {
  const [hovered, setHovered] = useState(false);
  const size = objectSize(object);
  const position = objectPosition(object);

  return (
    <group position={position} rotation={[0, object.rotation_y ?? 0, 0]}>
      <mesh
        castShadow
        receiveShadow
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
        <boxGeometry args={size} />
        <meshStandardMaterial
          color={objectColor(object)}
          roughness={0.7}
          emissive={selected || hovered ? "#ffffff" : "#000000"}
          emissiveIntensity={selected ? 0.25 : hovered ? 0.12 : 0}
        />
      </mesh>
      {(hovered || selected) && (
        <Html position={[0, size[1] / 2 + 0.15, 0]} center distanceFactor={8} zIndexRange={[10, 0]}>
          <div className="object-label">{object.label}</div>
        </Html>
      )}
    </group>
  );
}
