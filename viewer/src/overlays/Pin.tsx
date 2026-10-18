// pin: { object_id, severity 1-5, title, finding_id, why[], fix, severity_label, frame_url }
// Drawn on the flagged object itself: an outline around it, a ring on the floor under it and a
// marker on its top surface. Clicking the marker (or the object) opens the "what and why" card.
import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Edges, Html } from "@react-three/drei";
import type { Mesh, MeshBasicMaterial } from "three";
import { objectPosition, objectSize } from "../lib/defaults";
import type { OverlayProps } from "./OverlayLayer";

export function Pin({ data, objectsById, accent, walking = false, selectedId, onSelect }: OverlayProps) {
  const ring = useRef<Mesh>(null);
  useFrame(({ clock }) => {
    // A slow pulse on the floor ring so flagged objects read at a glance.
    const m = ring.current?.material as MeshBasicMaterial | undefined;
    if (m) m.opacity = 0.45 + 0.35 * (0.5 + 0.5 * Math.sin(clock.elapsedTime * 2.4));
  });

  const object = objectsById.get(data.object_id);
  if (!object) return null;
  const [x, y, z] = objectPosition(object);
  const [w, h, d] = objectSize(object);
  const severity = Math.min(5, Math.max(1, Number(data.severity) || 3));
  const selected = selectedId === object.id;
  // While a cart item is in focus, findings shrink to their severity dot so the item stays in view.
  const compact = walking || (typeof selectedId === "string" && selectedId.startsWith("cart_"));
  const radius = Math.hypot(w, d) / 2 + 0.12;
  const select = () => onSelect?.(object.id);

  return (
    <group>
      <group position={[x, y, z]} rotation={[0, object.rotation_y ?? 0, 0]}>
        {/* Outline exactly around the object (invisible box, visible edges). */}
        <mesh onClick={(e) => (e.stopPropagation(), select())}>
          <boxGeometry args={[w + 0.04, h + 0.04, d + 0.04]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} />
          <Edges color={accent} lineWidth={selected ? 3 : 2} />
        </mesh>
        <mesh ref={ring} position={[0, -y + 0.014, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[radius, radius + (selected ? 0.07 : 0.045), 64]} />
          <meshBasicMaterial color={accent} transparent opacity={0.7} toneMapped={false} />
        </mesh>
      </group>
      {/* The marker sits on the object's top surface; walking, it hides behind walls and furniture. */}
      <Html
        position={[x, y + h / 2 + 0.05, z]}
        center
        occlude={walking}
        distanceFactor={compact ? undefined : 8}
        zIndexRange={[30, 10]}
      >
        <button
          className={`pin-marker${selected ? " selected" : ""}${compact ? " compact" : ""}`}
          style={{ borderColor: accent }}
          // The marker lives in the canvas's container: stop the event, or the scene's "clicked
          // nothing" handler deselects right away.
          onPointerDown={(e) => e.stopPropagation()}
          onPointerUp={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            select();
          }}
          title={data.title}
        >
          <span className="pin-severity" style={{ background: accent }}>
            {severity}
          </span>
          {(!compact || selected) && <span className="pin-title">{data.title ?? object.label}</span>}
        </button>
      </Html>
    </group>
  );
}
