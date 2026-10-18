// The house assembles when it opens: each room grows up from its floor in turn, its furniture
// settles in after it, then the finding pins drop in last. Plays once per floor shown.
import { useRef, useState, type ReactNode } from "react";
import { useFrame } from "@react-three/fiber";
import type { Group } from "three";

export const ROOM_STAGGER_S = 0.45; // gap between one room starting and the next
export const RISE_S = 1.2; // how long one room takes to grow

const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

interface Props {
  delay: number; // seconds after the floor appears
  children: ReactNode;
  drop?: boolean; // pins fall into place instead of growing
}

export function Rise({ delay, children, drop = false }: Props) {
  const ref = useRef<Group>(null);
  const start = useRef<number | null>(null);
  const done = useRef(false);
  // Pins are HTML labels, which ignore 3D visibility: mount them only when their turn comes.
  const [live, setLive] = useState(!drop);

  useFrame(({ clock }) => {
    const g = ref.current;
    if (start.current === null) start.current = clock.elapsedTime;
    const t = Math.min(1, Math.max(0, (clock.elapsedTime - start.current - delay) / RISE_S));
    if (!live && t > 0) setLive(true);
    if (!g || done.current) return;
    const e = easeOut(t);
    g.visible = t > 0;
    if (drop) {
      g.position.y = (1 - e) * 1.5; // fall 1.5 m into place
    } else {
      g.scale.y = Math.max(0.001, e); // grow up from the floor (y = 0)
    }
    if (t >= 1) {
      g.position.y = 0;
      g.scale.y = 1;
      done.current = true;
    }
  });

  return (
    <group ref={ref} visible={false} scale={[1, drop ? 1 : 0.001, 1]}>
      {live && children}
    </group>
  );
}
