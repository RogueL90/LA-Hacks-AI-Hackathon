// The products in a cart, drawn at their real size where they'd go in the home (see before you buy).
// Local frame as everywhere else: the item's box is centred on the origin, front faces +z, back is -z.
// Furniture that has a catalog model (desk, chair, shelf) uses it; small fixes are built here.
import { Suspense } from "react";
import { SURFACES, type Surface } from "./materials";
import { MODEL_CATALOG } from "./catalog";
import { GltfModel } from "./GltfModel";
import { ProceduralObject } from "./Procedural";

type Vec3 = [number, number, number];

function Mat({ surface, color, opacity }: { surface: Surface; color?: string; opacity?: number }) {
  const s = SURFACES[surface];
  return (
    <meshStandardMaterial
      color={color ?? s.color}
      roughness={s.roughness}
      metalness={s.metalness}
      transparent={opacity !== undefined}
      opacity={opacity ?? 1}
    />
  );
}

function Box({ size, at = [0, 0, 0], children }: { size: Vec3; at?: Vec3; children: React.ReactNode }) {
  return (
    <mesh position={at} castShadow receiveShadow>
      <boxGeometry args={size} />
      {children}
    </mesh>
  );
}

/** A cylinder along the local x axis (rails, bars). */
function RodX({ length, radius, at = [0, 0, 0], children }: { length: number; radius: number; at?: Vec3; children: React.ReactNode }) {
  return (
    <mesh position={at} rotation={[0, 0, Math.PI / 2]} castShadow>
      <cylinderGeometry args={[radius, radius, length, 20]} />
      {children}
    </mesh>
  );
}

/** A cylinder along the local z axis. */
function RodZ({ length, radius, at = [0, 0, 0], children }: { length: number; radius: number; at?: Vec3; children: React.ReactNode }) {
  return (
    <mesh position={at} rotation={[Math.PI / 2, 0, 0]} castShadow>
      <cylinderGeometry args={[radius, radius, length, 20]} />
      {children}
    </mesh>
  );
}

function GrabBar({ size: [w, , d] }: { size: Vec3 }) {
  const r = 0.016;
  const bar = w - 0.06;
  return (
    <group>
      <RodX length={bar} radius={r} at={[0, 0, d / 2 - r]}><Mat surface="metal" /></RodX>
      {[-1, 1].map((s) => (
        <group key={s} position={[(s * bar) / 2, 0, 0]}>
          {/* Arm from the wall to the bar, and the round flange screwed into the wall. */}
          <RodZ length={d - r} radius={r * 0.9} at={[0, 0, -r / 2]}><Mat surface="metal" /></RodZ>
          <mesh position={[0, 0, -d / 2 + 0.004]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.04, 0.04, 0.008, 24]} />
            <Mat surface="metal" />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function NightLight({ size: [w, h, d], night }: { size: Vec3; night: boolean }) {
  return (
    <group>
      <Box size={[w, h, d * 0.5]} at={[0, 0, -d / 4]}><Mat surface="plastic" /></Box>
      <mesh position={[0, -h * 0.12, d * 0.1]} scale={[1, 0.7, 0.55]}>
        <sphereGeometry args={[w * 0.38, 20, 14]} />
        <meshStandardMaterial color="#fff6df" emissive="#ffc766" emissiveIntensity={night ? 3 : 1.4} roughness={0.3} />
      </mesh>
      {night && <pointLight position={[0, -h * 0.2, 0.08]} intensity={0.35} distance={1.6} color="#ffc766" />}
    </group>
  );
}

function StairRail({ size: [, , d] }: { size: Vec3 }) {
  // Runs along the local z axis (the group is pitched to the stairs' slope by the caller).
  const brackets = Math.max(2, Math.round(d / 1.1));
  return (
    <group>
      <RodZ length={d} radius={0.024}><meshStandardMaterial color="#9b7653" roughness={0.55} /></RodZ>
      {Array.from({ length: brackets }, (_, i) => {
        const z = -d / 2 + 0.2 + (i * (d - 0.4)) / (brackets - 1);
        return (
          <Box key={i} size={[0.02, 0.07, 0.02]} at={[0.035, -0.035, z]}>
            <Mat surface="metal" />
          </Box>
        );
      })}
    </group>
  );
}

function BabyGate({ size: [w, h, d] }: { size: Vec3 }) {
  const bars = Math.max(6, Math.round(w / 0.065));
  const color = "#f4f3ef";
  return (
    <group>
      <Box size={[w, 0.035, d]} at={[0, h / 2 - 0.018, 0]}><Mat surface="plastic" color={color} /></Box>
      <Box size={[w, 0.035, d]} at={[0, -h / 2 + 0.018, 0]}><Mat surface="plastic" color={color} /></Box>
      {[-1, 1].map((s) => (
        <Box key={s} size={[0.035, h, d]} at={[(s * (w - 0.035)) / 2, 0, 0]}><Mat surface="plastic" color={color} /></Box>
      ))}
      {Array.from({ length: bars }, (_, i) => (
        <Box key={i} size={[0.012, h - 0.07, 0.012]} at={[-w / 2 + 0.05 + (i * (w - 0.1)) / (bars - 1), 0, 0]}>
          <Mat surface="plastic" color={color} />
        </Box>
      ))}
    </group>
  );
}

function Monitor({ size: [w, h, d] }: { size: Vec3 }) {
  const screenH = h * 0.72;
  return (
    <group>
      <Box size={[0.22, 0.012, Math.min(0.18, d)]} at={[0, -h / 2 + 0.006, 0]}><Mat surface="darkMetal" /></Box>
      <Box size={[0.04, h - screenH + 0.04, 0.03]} at={[0, -h / 2 + (h - screenH) / 2 + 0.01, -0.03]}><Mat surface="darkMetal" /></Box>
      <Box size={[w, screenH, 0.03]} at={[0, h / 2 - screenH / 2, 0]}><Mat surface="darkMetal" /></Box>
      <Box size={[w - 0.02, screenH - 0.03, 0.004]} at={[0, h / 2 - screenH / 2 + 0.005, 0.016]}><Mat surface="glossyBlack" /></Box>
    </group>
  );
}

function Keyboard({ size: [w, h, d], at = [0, 0, 0] }: { size: Vec3; at?: Vec3 }) {
  return (
    <group position={at}>
      <Box size={[w, h * 0.6, d]}><Mat surface="darkMetal" color="#3a3c40" /></Box>
      <Box size={[w - 0.02, h * 0.3, d - 0.03]} at={[0, h * 0.42, 0.005]}><Mat surface="plastic" color="#1f2023" /></Box>
    </group>
  );
}

function Mouse({ at = [0, 0, 0] }: { at?: Vec3 }) {
  return (
    <mesh position={at} scale={[0.034, 0.02, 0.055]} castShadow>
      <sphereGeometry args={[1, 20, 14]} />
      <Mat surface="plastic" color="#1f2023" />
    </mesh>
  );
}

function Package({ size: [w, h, d] }: { size: Vec3 }) {
  return (
    <group>
      <Box size={[w, h, d]}><meshStandardMaterial color="#c79f6e" roughness={0.85} /></Box>
      <Box size={[w + 0.002, 0.004, 0.05]} at={[0, h / 2, 0]}><meshStandardMaterial color="#d9c19b" roughness={0.5} /></Box>
    </group>
  );
}

export function FixModel({ type, size, night = false }: { type: string; size: Vec3; night?: boolean }) {
  const [w, h, d] = size;
  const catalog = MODEL_CATALOG[type];
  if (catalog) {
    return (
      <Suspense fallback={<Package size={size} />}>
        <GltfModel entry={catalog} size={size} />
      </Suspense>
    );
  }
  switch (type) {
    case "grab_bar":
      return <GrabBar size={size} />;
    case "night_light":
      return <NightLight size={size} night={night} />;
    case "stair_rail":
      return <StairRail size={size} />;
    case "baby_gate":
      return <BabyGate size={size} />;
    case "anchor_strap":
      return <Box size={size}><Mat surface="plastic" color="#e9e6df" /></Box>;
    case "corner_guard":
      return (
        <mesh castShadow>
          <sphereGeometry args={[w / 2, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshStandardMaterial color="#eef3f6" roughness={0.15} transparent opacity={0.75} />
        </mesh>
      );
    case "outlet_cover":
      return (
        <group>
          <Box size={size}><Mat surface="plastic" /></Box>
          {[-1, 1].map((s) => (
            <Box key={s} size={[w * 0.5, h * 0.18, 0.004]} at={[0, (s * h) / 4, d / 2]}><Mat surface="plastic" color="#e6e2da" /></Box>
          ))}
        </group>
      );
    case "rug_pad":
      return <Box size={size}><meshStandardMaterial color="#8d949b" roughness={0.95} /></Box>;
    case "monitor":
      return <Monitor size={size} />;
    case "keyboard":
      return <Keyboard size={size} />;
    case "mouse":
      return <Mouse />;
    case "keyboard_mouse":
      return (
        <group>
          <Keyboard size={[w * 0.78, h * 0.7, d]} at={[-w * 0.11, -h * 0.15, 0]} />
          <Mouse at={[w * 0.4, -h / 2 + 0.02, 0.01]} />
        </group>
      );
    case "cable_tray":
      return <Box size={size}><Mat surface="darkMetal" /></Box>;
    case "package":
      return <Package size={size} />;
    default:
      // Types the house itself uses (rug, lamps, handrail...) are drawn the same way here.
      return <ProceduralObject type={type} size={size} color="#b9b2a8" night={night} />;
  }
}
