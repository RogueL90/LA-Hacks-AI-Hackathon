// pin: { object_id, severity 1-5, title, finding_id, frame_url } -> marker above the object.
import { Html } from "@react-three/drei";
import { objectPosition, objectSize } from "../lib/defaults";
import type { OverlayProps } from "./OverlayLayer";

export function Pin({ data, objectsById, accent }: OverlayProps) {
  const object = objectsById.get(data.object_id);
  if (!object) return null;
  const [x, y, z] = objectPosition(object);
  const top = y + objectSize(object)[1] / 2 + 0.35;
  const severity = Math.min(5, Math.max(1, Number(data.severity) || 3));

  return (
    <group position={[x, top, z]}>
      <mesh>
        <sphereGeometry args={[0.06 + severity * 0.012, 24, 24]} />
        <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={0.6} />
      </mesh>
      <Html position={[0, 0.2, 0]} center distanceFactor={8}>
        <div className="pin-label" style={{ borderColor: accent }}>
          <span className="pin-severity" style={{ background: accent }}>
            {severity}
          </span>
          {data.title ?? object.label}
        </div>
      </Html>
    </group>
  );
}
