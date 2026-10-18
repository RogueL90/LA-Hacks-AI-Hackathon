// Object types with no catalog model, built from a few primitives with realistic materials.
// Local frame: the object's box is centred on the origin, front faces +z, back is -z.
import { useMemo, type ReactNode } from "react";
import * as THREE from "three";
import { SURFACES, meterBox, meterPlane, usePbr, type Surface } from "./materials";

type Vec3 = [number, number, number];

const FABRIC_NORMAL_SCALE = new THREE.Vector2(0.6, 0.6);

interface Props {
  type: string;
  size: Vec3;
  color: string;
  night: boolean;
  headSign?: 1 | -1; // beds: headboard at the +/- end of the bed's own length axis (see bedHeadSign)
}

function Mat({ surface, color }: { surface: Surface; color?: string }) {
  const s = SURFACES[surface];
  return <meshStandardMaterial color={color ?? s.color} roughness={s.roughness} metalness={s.metalness} />;
}

/** Box of a given size centred at `at` in the object's local frame. */
function Block({ size, at, children }: { size: Vec3; at: Vec3; children: ReactNode }) {
  return (
    <mesh position={at} castShadow receiveShadow>
      <boxGeometry args={size} />
      {children}
    </mesh>
  );
}

function Fabric({ color }: { color: string }) {
  const { normalMap, roughnessMap } = usePbr("fabric");
  // The fabric weave comes from the normal/roughness maps; the colour is the measured one.
  return <meshStandardMaterial color={color} normalMap={normalMap} roughnessMap={roughnessMap} normalScale={FABRIC_NORMAL_SCALE} />;
}

function Oak({ color }: { color?: string }) {
  const { map, normalMap, roughnessMap } = usePbr("oak");
  return <meshStandardMaterial map={map} normalMap={normalMap} roughnessMap={roughnessMap} color={color ?? "#ffffff"} />;
}

function Bed({ size: [w, h, d], color, headSign = -1 }: { size: Vec3; color: string; headSign?: 1 | -1 }) {
  // Work in a frame where the bed's length runs along z; turn it if it is longer in x.
  const alongX = w > d;
  const [bw, bl] = alongX ? [d, w] : [w, d];
  const y0 = -h / 2;
  const frameH = h * 0.4;
  const mattressH = h * 0.38;
  const headZ = (headSign * bl) / 2;
  const duvetLen = bl * 0.72;
  const duvet = useMemo(() => meterBox(bw + 0.04, 0.08, duvetLen), [bw, duvetLen]);
  return (
    <group rotation={[0, alongX ? -Math.PI / 2 : 0, 0]}>
      <Block size={[bw, frameH, bl]} at={[0, y0 + frameH / 2, 0]}>
        <Oak color="#b59a7c" />
      </Block>
      <Block size={[bw - 0.06, mattressH, bl - 0.08]} at={[0, y0 + frameH + mattressH / 2, 0]}>
        <Mat surface="linen" />
      </Block>
      <mesh geometry={duvet} position={[0, y0 + frameH + mattressH + 0.02, -headSign * (bl - duvetLen) / 2]} castShadow receiveShadow>
        <Fabric color={color} />
      </mesh>
      {[-1, 1].map((side) => (
        <Block key={side} size={[bw * 0.38, 0.12, 0.38]} at={[(side * bw) / 4.4, y0 + frameH + mattressH + 0.06, headZ - headSign * 0.3]}>
          <Mat surface="linen" color="#fbfaf6" />
        </Block>
      ))}
      <Block size={[bw + 0.04, Math.max(h * 1.6, 0.95), 0.07]} at={[0, y0 + Math.max(h * 1.6, 0.95) / 2, headZ]}>
        <Oak color="#a88a6a" />
      </Block>
    </group>
  );
}

function Lamp({ size: [w, h], night, floor }: { size: Vec3; night: boolean; floor: boolean }) {
  const y0 = -h / 2;
  const shadeH = floor ? 0.32 : h * 0.45;
  const shadeR = Math.max(w / 2, 0.08);
  return (
    <group>
      <mesh position={[0, y0 + 0.015, 0]} castShadow>
        <cylinderGeometry args={[shadeR * 0.6, shadeR * 0.65, 0.03, 24]} />
        <Mat surface="darkMetal" />
      </mesh>
      <mesh position={[0, y0 + (h - shadeH) / 2, 0]} castShadow>
        <cylinderGeometry args={[0.012, 0.012, h - shadeH, 8]} />
        <Mat surface="darkMetal" />
      </mesh>
      <mesh position={[0, y0 + h - shadeH / 2, 0]} castShadow>
        <cylinderGeometry args={[shadeR * 0.75, shadeR, shadeH, 32, 1, true]} />
        <meshStandardMaterial color="#f3ead8" emissive="#ffcf8a" emissiveIntensity={night ? 1.4 : 0.25} side={2} roughness={0.9} />
      </mesh>
      {night && <pointLight position={[0, y0 + h - shadeH / 2, 0]} intensity={1.2} distance={4} decay={2} color="#ffcf8a" />}
    </group>
  );
}

function Bathtub({ size: [w, h, d] }: { size: Vec3 }) {
  const t = 0.07;
  const y0 = -h / 2;
  return (
    <group>
      <Block size={[w, 0.08, d]} at={[0, y0 + 0.04, 0]}><Mat surface="ceramic" /></Block>
      <Block size={[w, h, t]} at={[0, 0, -d / 2 + t / 2]}><Mat surface="ceramic" /></Block>
      <Block size={[w, h, t]} at={[0, 0, d / 2 - t / 2]}><Mat surface="ceramic" /></Block>
      <Block size={[t, h, d]} at={[-w / 2 + t / 2, 0, 0]}><Mat surface="ceramic" /></Block>
      <Block size={[t, h, d]} at={[w / 2 - t / 2, 0, 0]}><Mat surface="ceramic" /></Block>
    </group>
  );
}

function Toilet({ size: [w, h, d] }: { size: Vec3 }) {
  const y0 = -h / 2;
  return (
    <group>
      <mesh position={[0, y0 + h * 0.27, d * 0.12]} castShadow receiveShadow>
        <cylinderGeometry args={[w * 0.45, w * 0.3, h * 0.54, 28]} />
        <Mat surface="ceramic" />
      </mesh>
      <mesh position={[0, y0 + h * 0.56, d * 0.12]} scale={[1, 1, 1.25]} castShadow>
        <cylinderGeometry args={[w * 0.47, w * 0.47, 0.04, 28]} />
        <Mat surface="ceramic" />
      </mesh>
      <Block size={[w, h * 0.48, d * 0.24]} at={[0, y0 + h * 0.76, -d / 2 + d * 0.12]}><Mat surface="ceramic" /></Block>
    </group>
  );
}

function Sink({ size: [w, h, d] }: { size: Vec3 }) {
  const y0 = -h / 2;
  const topH = 0.05;
  return (
    <group>
      <Block size={[w, h - topH, d]} at={[0, y0 + (h - topH) / 2, 0]}><Oak color="#d8cbb8" /></Block>
      <Block size={[w + 0.02, topH, d + 0.02]} at={[0, h / 2 - topH / 2, 0]}><Mat surface="stone" /></Block>
      <mesh position={[0, h / 2 + 0.005, 0.02]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[Math.min(w, d) * 0.32, 32]} />
        <Mat surface="ceramic" color="#e9e8e3" />
      </mesh>
      <Block size={[0.03, 0.18, 0.03]} at={[0, h / 2 + 0.09, -d / 2 + 0.06]}><Mat surface="metal" /></Block>
    </group>
  );
}

function Shower({ size: [w, h, d] }: { size: Vec3 }) {
  const y0 = -h / 2;
  return (
    <group>
      <Block size={[w, 0.06, d]} at={[0, y0 + 0.03, 0]}><Mat surface="ceramic" /></Block>
      {[[w, h, 0.01, 0, d / 2], [0.01, h, d, w / 2, 0]].map(([gw, gh, gd, x, z], i) => (
        <mesh key={i} position={[x as number, 0, z as number]}>
          <boxGeometry args={[gw as number, gh as number, gd as number]} />
          <meshStandardMaterial color="#dfeff2" transparent opacity={0.18} roughness={0.05} metalness={0.1} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
}

/** Cabinets in the measured colour under a stone top: counters, islands, bathroom vanities. */
function Counter({ size: [w, h, d], color }: { size: Vec3; color?: string }) {
  const topH = 0.04;
  return (
    <group>
      <Block size={[w, h - topH, d - 0.03]} at={[0, -topH / 2, -0.015]}><Mat surface="plastic" color={color} /></Block>
      <Block size={[w + 0.02, topH, d + 0.02]} at={[0, h / 2 - topH / 2, 0]}><Mat surface="stone" /></Block>
    </group>
  );
}

function Laundry({ size: [w, h, d], dryer }: { size: Vec3; dryer: boolean }) {
  const r = Math.min(w, h) * 0.3;
  return (
    <group>
      <Block size={[w, h, d]} at={[0, 0, 0]}><Mat surface="plastic" color="#f4f4f2" /></Block>
      <mesh position={[0, -h * 0.05, d / 2 + 0.006]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[r, r, 0.012, 40]} />
        <Mat surface={dryer ? "darkMetal" : "glossyBlack"} />
      </mesh>
      <Block size={[w * 0.9, 0.08, 0.01]} at={[0, h / 2 - 0.07, d / 2 + 0.005]}><Mat surface="darkMetal" /></Block>
    </group>
  );
}

function Crib({ size: [w, h, d], color }: { size: Vec3; color: string }) {
  const y0 = -h / 2;
  const slats = Math.max(6, Math.round(w / 0.07));
  return (
    <group>
      <Block size={[w - 0.06, 0.12, d - 0.06]} at={[0, y0 + h * 0.35, 0]}><Mat surface="linen" /></Block>
      {[-1, 1].map((sz) => (
        <group key={sz}>
          <Block size={[w, 0.04, 0.04]} at={[0, h / 2 - 0.02, (sz * (d - 0.04)) / 2]}><Oak color={color} /></Block>
          {Array.from({ length: slats }, (_, i) => (
            <Block key={i} size={[0.02, h * 0.62, 0.02]} at={[-w / 2 + ((i + 0.5) * w) / slats, h * 0.18, (sz * (d - 0.04)) / 2]}>
              <Oak color={color} />
            </Block>
          ))}
        </group>
      ))}
      {[-1, 1].map((sx) => (
        <Block key={sx} size={[0.04, h, d]} at={[(sx * (w - 0.04)) / 2, 0, 0]}><Oak color={color} /></Block>
      ))}
    </group>
  );
}

function RangeHood({ size: [w, h, d] }: { size: Vec3 }) {
  const canopyH = Math.min(0.15, h * 0.4);
  return (
    <group>
      <Block size={[w, canopyH, d]} at={[0, -h / 2 + canopyH / 2, 0]}><Mat surface="metal" /></Block>
      <Block size={[w * 0.35, h - canopyH, d * 0.45]} at={[0, canopyH / 2, -d * 0.25]}><Mat surface="metal" /></Block>
    </group>
  );
}

function Curtain({ size: [w, h], color }: { size: Vec3; color: string }) {
  // A thin hanging panel: curtains are drawn against the wall, never as a block in the room.
  return (
    <mesh castShadow>
      <boxGeometry args={[w, h, 0.03]} />
      <Fabric color={color} />
    </mesh>
  );
}

function Stairs({ size: [w, h, d] }: { size: Vec3 }) {
  const n = Math.max(3, Math.round(h / 0.18));
  const rise = h / n;
  const run = d / n;
  return (
    <group>
      {Array.from({ length: n }, (_, i) => (
        <Block key={i} size={[w, rise * (i + 1), run]} at={[0, -h / 2 + (rise * (i + 1)) / 2, d / 2 - run * (i + 0.5)]}>
          <Oak />
        </Block>
      ))}
    </group>
  );
}

function Rug({ size: [w, h, d], color }: { size: Vec3; color: string }) {
  const geo = useMemo(() => meterPlane(w, d), [w, d]);
  return (
    <mesh geometry={geo} position={[0, -h / 2 + 0.004, 0]} receiveShadow>
      <Fabric color={color} />
    </mesh>
  );
}

export function ProceduralObject({ type, size, color, night, headSign }: Props) {
  const [w, h, d] = size;
  switch (type) {
    case "bed":
      return <Bed size={size} color={color} headSign={headSign} />;
    case "lamp_floor":
    case "lamp_table":
      return <Lamp size={size} night={night} floor={type === "lamp_floor"} />;
    case "bathtub":
      return <Bathtub size={size} />;
    case "toilet":
      return <Toilet size={size} />;
    case "sink":
      return <Sink size={size} />;
    case "shower":
      return <Shower size={size} />;
    case "counter":
    case "kitchen_island":
    case "vanity":
      return <Counter size={size} color={color} />;
    case "washer":
    case "dryer":
      return <Laundry size={size} dryer={type === "dryer"} />;
    case "crib":
      return <Crib size={size} color={color} />;
    case "range_hood":
      return <RangeHood size={size} />;
    case "curtain":
      return <Curtain size={size} color={color} />;
    case "dishwasher":
    case "oven":
    case "microwave":
      return (
        <group>
          <Block size={size} at={[0, 0, 0]}><Mat surface="metal" /></Block>
          <Block size={[w * 0.7, h * 0.45, 0.005]} at={[0, h * 0.05, d / 2 + 0.003]}><Mat surface="glossyBlack" /></Block>
        </group>
      );
    case "light_switch":
    case "thermostat":
    case "smoke_detector":
      return <Block size={size} at={[0, 0, 0]}><Mat surface="plastic" /></Block>;
    case "handrail":
      return <Block size={[w, Math.min(h, 0.05), Math.min(d, 0.05)]} at={[0, h / 2 - 0.025, 0]}><Oak /></Block>;
    case "stairs":
      return <Stairs size={size} />;
    case "rug":
      return <Rug size={size} color={color} />;
    case "tv":
      return (
        <group>
          <Block size={size} at={[0, 0, 0]}><Mat surface="darkMetal" /></Block>
          <Block size={[w - 0.03, h - 0.03, 0.005]} at={[0, 0, d / 2 + 0.002]}><Mat surface="glossyBlack" /></Block>
        </group>
      );
    case "laptop":
      return (
        <group>
          <Block size={[w, 0.015, d]} at={[0, -h / 2 + 0.0075, 0]}><Mat surface="metal" /></Block>
          <group position={[0, -h / 2 + 0.015, -d / 2]} rotation={[-0.3, 0, 0]}>
            <Block size={[w, d, 0.008]} at={[0, d / 2, 0]}><Mat surface="glossyBlack" /></Block>
          </group>
        </group>
      );
    case "mirror":
      return (
        <group>
          <Block size={size} at={[0, 0, 0]}><Mat surface="darkMetal" /></Block>
          <Block size={[w - 0.04, h - 0.04, 0.004]} at={[0, 0, d / 2 + 0.002]}><Mat surface="mirror" /></Block>
        </group>
      );
    case "window":
      return (
        <group>
          <Block size={[w, h, d]} at={[0, 0, 0]}>
            <meshStandardMaterial color="#cfe3ee" transparent opacity={0.35} roughness={0.05} depthWrite={false} />
          </Block>
          <Block size={[w, 0.04, Math.max(d, 0.08)]} at={[0, -h / 2, 0]}><Mat surface="plastic" /></Block>
        </group>
      );
    case "refrigerator":
      return (
        <group>
          <Block size={size} at={[0, 0, 0]}><Mat surface="metal" /></Block>
          <Block size={[0.02, h * 0.5, 0.03]} at={[w / 2 - 0.08, h * 0.05, d / 2 + 0.015]}><Mat surface="darkMetal" /></Block>
        </group>
      );
    case "outlet":
      return <Block size={size} at={[0, 0, 0]}><Mat surface="plastic" /></Block>;
    case "cord":
      return <Block size={size} at={[0, 0, 0]}><Mat surface="rubber" /></Block>;
    default:
      // clutter and any type without a model: a plain box in the measured colour.
      return <Block size={size} at={[0, 0, 0]}><meshStandardMaterial color={color} roughness={0.7} /></Block>;
  }
}
