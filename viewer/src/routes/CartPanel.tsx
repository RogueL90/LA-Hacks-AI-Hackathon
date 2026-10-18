// "Your cart in your home": a scrollable list on the left of every product in the cart, each with
// the store's photo (or a small 3D model of the fix when the store has none), its price and what it
// fixes. Picking one flies the camera to where it goes in the house.
import { Suspense, useEffect } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { FixModel } from "../scene/FixModels";

export type CartItem = Record<string, any>; // the first unit's ghost_object data for each cart item

const MAX_PREVIEWS = 8; // each 3D thumbnail is its own WebGL context; browsers allow about 16

function Aim({ distance }: { distance: number }) {
  const camera = useThree((s) => s.camera);
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    camera.position.set(distance * 0.75, distance * 0.55, distance);
    camera.lookAt(0, 0, 0);
    invalidate();
  }, [camera, distance, invalidate]);
  return null;
}

/** A small, still 3D view of the fix itself (drawn once; no render loop). */
function MiniPreview({ item }: { item: CartItem }) {
  // A 4 m stair rail would be a hairline: show a 1.2 m piece of it.
  const size = (item.type === "stair_rail" ? [0.05, 0.05, 1.2] : item.size) as [number, number, number];
  const [w, h, d] = size;
  const reach = Math.max(w, h, d, 0.08);
  return (
    <Canvas className="cart-thumb-3d" frameloop="demand" dpr={[1, 2]} camera={{ fov: 30 }} gl={{ antialias: true, alpha: true }}>
      <Aim distance={reach * 2.1} />
      <ambientLight intensity={0.8} />
      <directionalLight position={[1.5, 2.5, 2]} intensity={1.8} />
      <directionalLight position={[-2, 1, -1]} intensity={0.5} />
      <Suspense fallback={null}>
        {/* Long, sloped things (a stair rail) are shown lying flat so they fit the thumbnail. */}
        <group rotation={[0, item.type === "stair_rail" ? Math.PI / 2 : 0, 0]}>
          <FixModel type={item.type} size={size} />
        </group>
      </Suspense>
    </Canvas>
  );
}

function Thumb({ item, index }: { item: CartItem; index: number }) {
  if (item.image_url) {
    return <img className="cart-thumb" src={item.image_url} alt="" referrerPolicy="no-referrer" loading="lazy" />;
  }
  if (index < MAX_PREVIEWS) {
    return (
      <div className="cart-thumb">
        <MiniPreview item={item} />
      </div>
    );
  }
  return <div className="cart-thumb cart-thumb-empty">+</div>;
}

interface Props {
  items: CartItem[];
  selectedId: string | null;
  accent: string;
  open: boolean;
  onToggle: () => void;
  onPick: (item: CartItem) => void;
}

export function CartPanel({ items, selectedId, accent, open, onToggle, onPick }: Props) {
  const total = items.reduce((sum, i) => sum + (Number(i.price_usd) || 0) * (Number(i.quantity) || 1), 0);
  if (!open) {
    return (
      <button className="cart-pill" onClick={onToggle} style={{ borderColor: accent }}>
        Your cart in 3D · {items.length}
      </button>
    );
  }
  return (
    <aside className="cart-panel" aria-label="Your cart in your home">
      <header className="cart-panel-head">
        <div>
          <h2>Your cart in your home</h2>
          <p>
            {items.length} product{items.length === 1 ? "" : "s"} · ${total.toFixed(2)} · see each one before you buy
          </p>
        </div>
        <button className="cart-close" onClick={onToggle} aria-label="Hide the cart">
          ‹
        </button>
      </header>
      <ul className="cart-list">
        {items.map((item, i) => {
          const active = typeof selectedId === "string" && selectedId.startsWith(`cart_${item.item}_`);
          return (
            <li key={item.id}>
              <button
                className={`cart-card${active ? " active" : ""}`}
                style={active ? { borderColor: accent } : undefined}
                onClick={() => onPick(item)}
              >
                <Thumb item={item} index={i} />
                <span className="cart-card-body">
                  <span className="cart-card-title">{item.title ?? item.label}</span>
                  <span className="cart-card-price">
                    ${Number(item.price_usd).toFixed(2)}
                    {Number(item.quantity) > 1 ? ` × ${item.quantity}` : ""} · {item.merchant}
                  </span>
                  {(item.finding_title || item.fix) && (
                    <span className="cart-card-fix">{item.finding_title ? `Fixes: ${item.finding_title}` : item.fix}</span>
                  )}
                  <span className="cart-card-go" style={{ color: accent }}>
                    Show me where →
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
