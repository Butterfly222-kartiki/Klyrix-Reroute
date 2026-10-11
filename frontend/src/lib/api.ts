import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

// Empty base = same origin (Vite proxies /api to the Python backend). Set VITE_API_URL to call a remote backend.
const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? '';

export async function api<T = any>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'include',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || (j.errors || []).join('; ') || `Request failed (${r.status})`);
  return j as T;
}

/** minutes-since-midnight -> HH:MM */
export const apiUrl = (p: string) => BASE + p;

export function hhmm(m: number | null | undefined) {
  if (m == null || Number.isNaN(m)) return '—';
  const t = Math.round(m);
  return `${String(Math.floor(t / 60) % 24).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
}

export type Row = { stop_id: string; kind: string; location: string; arrival: number; wait: number; depart: number; load_after: number; tw_start: number; tw_end: number; slack: number };
export type VehiclePlan = { capacity: number; failed: unknown; origin: string; origin_time: number; history: Row[]; rows: Row[] };
export type Compare = { delivery: string; location: string; weight: number; window: string; vehicle_before: string | null; vehicle_after: string | null; eta_before: number | null; eta_after: number | null; status: 'kept' | 'moved' | 'broken' | 'new'; tag: string; reason: string; eta_delta: number };
export type Sim = {
  scenario: { name: string; depot: string; locations: Record<string, { x: number; y: number }>; vehicles: { id: string; capacity: number; start_time: string }[]; deliveries: { id: string; location: string; weight: number; tw_start: number; tw_end: number; service: number }[] };
  plan: { now: number; label: string; vehicles: Record<string, VehiclePlan>; unassigned: Record<string, { reason: string; proven: boolean }>; metrics: Record<string, number> };
  validation: { valid: boolean; errors: string[] };
  events: { time: number; incident: { description: string }; summary?: Record<string, number> }[];
  vs_original: Compare[];
};
export type Preview = { ok: boolean; id?: string; errors?: string[]; message?: string; incident?: { description: string }; requires_confirmation?: boolean; accepted?: boolean; strategy?: string; validation?: { valid: boolean }; summary?: Record<string, number>; comparison?: Compare[]; log?: string[]; revised?: Sim['plan'] };

export function useSim() {
  return useQuery({ queryKey: ['state'], queryFn: () => api<Sim>('/api/state'), refetchInterval: 20000, retry: 1 });
}

/** POST an action, then refresh the shared state. */
export function useAct<T = any>() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => api<T>(path, body ?? {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['state'] }),
  });
}
