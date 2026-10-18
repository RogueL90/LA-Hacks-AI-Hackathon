// A catalog glTF model fitted into an object's measured box.
// Model origins vary, so each model is re-centred (XZ centre, floor at y=0) and scaled
// from its own bounding box. Rendered inside a group positioned at the box centre.
import { useMemo } from "react";
import * as THREE from "three";
import { Clone, useGLTF } from "@react-three/drei";
import { MODEL_CATALOG, type ModelEntry } from "./catalog";

// Plain glTF (no Draco/meshopt), so no decoder is fetched from a CDN.
for (const entry of Object.values(MODEL_CATALOG)) useGLTF.preload(entry.url, false, false);

function nativeBounds(scene: THREE.Object3D) {
  const box = new THREE.Box3().setFromObject(scene);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  return { size, offset: new THREE.Vector3(-center.x, -box.min.y, -center.z) };
}

function fitScale(entry: ModelEntry, native: [number, number, number], target: [number, number, number]) {
  const [nw, nh, nd] = native.map((v) => Math.max(v, 1e-4));
  const [w, h, d] = target;
  if (entry.fit === "uniform_height") return new THREE.Vector3(h / nh, h / nh, h / nh);
  if (entry.fit === "uniform_width") return new THREE.Vector3(w / nw, w / nw, w / nw);
  return new THREE.Vector3(w / nw, h / nh, d / nd);
}

export function GltfModel({ entry, size }: { entry: ModelEntry; size: [number, number, number] }) {
  const { scene } = useGLTF(entry.url, false, false);
  const yaw = entry.yaw ?? 0;

  const { offset, native } = useMemo(() => {
    scene.traverse((o) => {
      if ((o as THREE.Mesh).isMesh) o.castShadow = o.receiveShadow = true;
    });
    const { size: s, offset } = nativeBounds(scene);
    // After a quarter turn the model's depth runs along x.
    const quarter = Math.round(yaw / (Math.PI / 2)) % 2 !== 0;
    const native: [number, number, number] = quarter ? [s.z, s.y, s.x] : [s.x, s.y, s.z];
    return { offset, native };
  }, [scene, yaw]);

  const scale = fitScale(entry, native, size);
  const fittedHeight = native[1] * scale.y;
  const baseY = entry.anchor === "top" ? size[1] / 2 - fittedHeight : -size[1] / 2;

  return (
    <group position={[0, baseY, 0]} scale={scale}>
      <group rotation={[0, yaw, 0]}>
        {/* Clone so two chairs can share one loaded scene (an Object3D has one parent). */}
        <Clone object={scene} position={offset} castShadow receiveShadow />
      </group>
    </group>
  );
}
