import type { OverlaySet, Space } from "./types";

export const SPACE_SERVICE_URL = (import.meta.env.VITE_SPACE_SERVICE_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${SPACE_SERVICE_URL}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json() as Promise<T>;
}

export const fetchSpace = (spaceId: string) => getJson<Space>(`/spaces/${spaceId}`);

export const fetchOverlaySet = (spaceId: string, overlaySetId: string) =>
  getJson<OverlaySet>(`/spaces/${spaceId}/overlays/${overlaySetId}`);
