// ghost_object: a product from the cart, placed where it would go in the home (see before you buy).
// data: { id, item, unit, type, label, title, position, size, rotation_y, pitch?, room_id, price_usd,
//         merchant, url, image_url, frame_url, finding_title, fix }
// Drawn at its real size with a realistic model; items drop in one after another. Hover or select
// outlines it and shows its name and price. Entries without a position (the plan's "add a desk on
// the back wall" notes) are skipped.
import { useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Edges, Html } from "@react-three/drei";
import type { Group } from "three";
import { FixModel } from "../scene/FixModels";
import type { OverlayProps } from "./OverlayLayer";

const DROP_S = 0.7; // one item's drop
const STAGGER_S = 0.22; // gap between items

export function GhostObject({ data, accent, walking = false, selectedId, onSelect, roomIds, night }: OverlayProps) {
  const drop = useRef<Group>(null);
  const start = useRef<number | null>(null);
  const [hovered, setHovered] = useState(false);
  useFrame(({ clock }) => {
    const g = drop.current;
    if (!g) return;
    if (start.current === null) start.current = clock.elapsedTime;
    const t = Math.min(1, Math.max(0, (clock.elapsedTime - start.current - (Number(data.item) || 0) * STAGGER_S) / DROP_S));
    const e = 1 - Math.pow(1 - t, 3);
    g.visible = t > 0;
    g.position.y = (1 - e) * 0.45;
    g.scale.setScalar(0.6 + 0.4 * e);
  });

  if (!Array.isArray(data.position) || !Array.isArray(data.size)) return null;
  if (roomIds && data.room_id && !roomIds.has(data.room_id)) return null; // on another floor

  const [x, y, z] = data.position as number[];
  const size = data.size as [number, number, number];
  const selected = typeof selectedId === "string" && selectedId.startsWith(`cart_${data.item}_`);
  const active = selected || hovered;
  const select = () => onSelect?.(data.id);
  const hit: [number, number, number] = [
    Math.max(size[0], 0.12) + 0.04,
    Math.max(size[1], 0.12) + 0.04,
    Math.max(size[2], 0.12) + 0.04,
  ];
  const price = typeof data.price_usd === "number" ? `$${data.price_usd.toFixed(2)}` : "";

  return (
    <group position={[x, y, z]} rotation={[data.pitch ?? 0, data.rotation_y ?? 0, 0, "YXZ"]}>
      <group ref={drop} visible={false}>
        <group
          onClick={(e) => {
            e.stopPropagation();
            select();
          }}
          onPointerOver={(e) => {
            e.stopPropagation();
            setHovered(true);
          }}
          onPointerOut={() => setHovered(false)}
        >
          <FixModel type={data.type} size={size} night={night} />
          {/* A slightly larger invisible box, so a 7 cm outlet cover is still easy to click. */}
          <mesh>
            <boxGeometry args={hit} />
            <meshBasicMaterial transparent opacity={0} depthWrite={false} />
            {active && <Edges color={accent} lineWidth={2} />}
          </mesh>
        </group>
        {(data.unit ?? 0) === 0 && !walking && (
          <Html position={[0, size[1] / 2 + 0.08, 0]} center zIndexRange={[25, 5]}>
            <button
              className={`ghost-marker${active ? " active" : ""}`}
              style={{ background: accent }}
              onPointerDown={(e) => e.stopPropagation()}
              onPointerUp={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                select();
              }}
              title={`${data.label ?? "New item"}${price ? ` · ${price}` : ""}`}
            >
              +
            </button>
          </Html>
        )}
        {active && (hovered || (data.unit ?? 0) === 0) && (
          <Html position={[0, size[1] / 2 + 0.22, 0]} center zIndexRange={[40, 30]}>
            <div className="ghost-label">
              <span className="ghost-new" style={{ background: accent }}>
                In your cart
              </span>
              {data.label}
              {price && <strong>{price}</strong>}
            </div>
          </Html>
        )}
      </group>
    </group>
  );
}
