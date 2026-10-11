import { Link } from '@tanstack/react-router';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Package, Truck, Clock3, TriangleAlert, CircleCheck, Undo2, RotateCcw, Send, Check, X, FastForward, Download, RefreshCw, WifiOff, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PageHeading, EmptyState } from './workspace';
import { WorkflowNavigation } from './workflow';
import { InstallButton, OfflineBadge } from './pwa';
import { api, apiUrl, hhmm, useAct, useSim, type Compare, type Preview, type Sim } from '@/lib/api';

const COLORS = ['#2563eb', '#16a34a', '#9333ea', '#ea580c', '#0891b2'];
const STATUS: Record<string, [string, string]> = { kept: ['#166534', '#dcfce7'], moved: ['#92400e', '#fef3c7'], broken: ['#991b1b', '#fee2e2'], new: ['#1e40af', '#dbeafe'] };
const Tag = ({ s }: { s: string }) => <span className="badge-count" style={{ color: (STATUS[s] || ['inherit'])[0], background: (STATUS[s] || [])[1] }}>{s}</span>;

/** Page frame: heading + loading / backend-down states, then children get live data. */
function Page({ title, description, actions, children }: { title: string; description: string; actions?: ReactNode; children: (s: Sim) => ReactNode }) {
  const q = useSim();
  return <>
    <PageHeading title={title} description={description}><OfflineBadge />{actions}</PageHeading>
    {q.data ? children(q.data)
      : q.isLoading ? <EmptyState icon={RefreshCw} title="Loading live plan…" description="Connecting to the ReRoute engine." />
      : <EmptyState icon={WifiOff} title="Engine unreachable" description={`Start the backend (cd backend && python -m reroute.server). ${(q.error as Error | null)?.message ?? ''}`} action={<Button variant="outline" size="sm" onClick={() => q.refetch()}><RefreshCw />Retry</Button>} />}
  </>;
}

function Metric({ label, value, sub, icon: Icon }: { label: string; value: ReactNode; sub: string; icon: typeof Package }) {
  return <div className="metric"><div className="metric-label"><span>{label}</span><span className="metric-icon"><Icon size={15} /></span></div><div className="metric-value">{value}</div><div className="metric-bottom"><span className="status-dot" /> {sub}</div></div>;
}

function DataTable({ cols, rows, empty }: { cols: string[]; rows: ReactNode[][]; empty: string }) {
  const [q, setQ] = useState('');
  const shown = rows.filter(r => !q || r.map(c => (typeof c === 'string' || typeof c === 'number' ? String(c) : '')).join(' ').toLowerCase().includes(q.toLowerCase()));
  return <section className="panel">
    <div className="section-toolbar"><label className="table-search"><Search size={14} /><input aria-label="Search" placeholder="Search…" value={q} onChange={e => setQ(e.target.value)} /></label><span className="badge-count">{shown.length} of {rows.length}</span></div>
    <div className="table-scroll"><table><thead><tr>{cols.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{shown.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table></div>
    {!shown.length && <EmptyState title={empty} description="Nothing matches right now." />}
  </section>;
}

function SimControls({ s }: { s: Sim }) {
  const act = useAct();
  const run = (path: string, body?: unknown) => act.mutate({ path, body });
  return <div className="notice-band" style={{ marginBottom: 18 }}>
    <Clock3 size={19} /><div className="min-w-0"><strong>Simulation clock {hhmm(s.plan.now)}</strong><p>{s.plan.label} · {s.validation.valid ? 'validated plan' : 'validation errors'}{act.error ? ` · ${(act.error as Error).message}` : ''}</p></div>
    <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => run('/api/advance', { minutes: 30 })}><FastForward />+30 min</Button>
      <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => run('/api/undo')}><Undo2 />Undo</Button>
      <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => run('/api/reset')}><RotateCcw />Reset demo</Button>
    </span>
  </div>;
}

export function LiveOverview() {
  return <Page title="Operations Overview" description="Live fleet status, delivery exceptions and replanning readiness." actions={<><InstallButton /><Button asChild variant="outline"><Link to="/disruptions"><TriangleAlert />Report Disruption</Link></Button></>}>
    {s => {
      const m = s.plan.metrics, vs = Object.entries(s.plan.vehicles), down = vs.filter(([, v]) => v.failed).length;
      const un = Object.entries(s.plan.unassigned);
      return <>
        <WorkflowNavigation current="/" />
        <div className="metrics-grid">
          <Metric label="Deliveries" value={m.deliveries} sub={`${m.pending_assigned} pending`} icon={Package} />
          <Metric label="Completed" value={m.completed} sub="delivered so far" icon={CircleCheck} />
          <Metric label="Active vehicles" value={`${vs.length - down}/${vs.length}`} sub={down ? `${down} broken down` : 'all running'} icon={Truck} />
          <Metric label="Unfulfilled" value={m.unfulfilled} sub={m.unfulfilled ? 'needs dispatcher action' : 'none at risk'} icon={TriangleAlert} />
          <Metric label="Total travel" value={`${Math.round(m.total_travel)} min`} sub={`${Math.round(m.total_wait)} min waiting`} icon={Clock3} />
        </div>
        <SimControls s={s} />
        {!!un.length && <section className="panel" style={{ marginBottom: 18 }}><div className="panel-head"><div><h2>Unfulfilled orders <span className="badge-count">{un.length}</span></h2><p>Never silently promised — reasons below.</p></div></div>
          <div style={{ padding: '4px 18px 14px', fontSize: 12 }}>{un.map(([id, u]) => <p key={id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}><strong>{id}</strong> · {u.proven ? 'proven infeasible' : 'heuristic could not place'} — {u.reason}</p>)}</div></section>}
        <section className="panel"><div className="panel-head"><div><h2>Routes by vehicle</h2><p>Upcoming stops, ETAs and slack against each time window.</p></div></div>
          <div className="table-scroll"><table><thead><tr>{['Vehicle', 'Stop', 'Location', 'ETA', 'Window', 'Slack', 'Load'].map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>
            {vs.flatMap(([id, v]) => v.failed ? [<tr key={id}><td>{id}</td><td colSpan={6}><Tag s="broken" /> broke down — stops recovered or flagged</td></tr>]
              : v.rows.map(r => <tr key={id + r.stop_id}><td>{id}</td><td>{r.stop_id} <small>({r.kind})</small></td><td>{r.location}</td><td>{hhmm(r.arrival)}</td><td>{hhmm(r.tw_start)}–{hhmm(r.tw_end)}</td><td>{Math.round(r.slack)} min</td><td>{Math.round(r.load_after)}/{v.capacity}</td></tr>))}
          </tbody></table></div></section>
      </>;
    }}
  </Page>;
}

const TILE = (import.meta.env.VITE_MAP_TILE_URL as string | undefined) || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
/** The scenario uses an abstract 0-100 grid; project it onto a ~20 km box over Pune for display. */
const toLL = (p: { x: number; y: number }): [number, number] => [18.42 + (100 - p.y) * 0.002, 73.76 + p.x * 0.002];

function LiveMap({ s }: { s: Sim }) {
  const el = useRef<HTMLDivElement>(null);
  const ref = useRef<{ map: any; layer: any; L: any } | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let dead = false, ro: ResizeObserver | undefined;
    import('leaflet').then(L => {
      if (dead || !el.current) return;
      const map = L.map(el.current).setView([18.52, 73.857], 12);
      L.tileLayer(TILE, { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
      ref.current = { map, layer: L.layerGroup().addTo(map), L };
      ro = new ResizeObserver(() => map.invalidateSize()); ro.observe(el.current);
      setReady(true);
    });
    return () => { dead = true; ro?.disconnect(); ref.current?.map.remove(); ref.current = null; };
  }, []);
  useEffect(() => {
    const r = ref.current; if (!r) return;
    const { L, layer, map } = r, locs = s.scenario.locations, pts: [number, number][] = [];
    layer.clearLayers();
    const dep = toLL(locs[s.scenario.depot]); pts.push(dep);
    L.circleMarker(dep, { radius: 9, color: '#111827', fillColor: '#111827', fillOpacity: 1 }).bindTooltip('Depot').addTo(layer);
    Object.entries(s.plan.vehicles).forEach(([id, v], i) => {
      const color = v.failed ? '#dc2626' : COLORS[i % COLORS.length];
      const path = [s.scenario.depot, ...v.history.map(h => h.location), ...v.rows.map(x => x.location)].filter(l => locs[l]).map(l => toLL(locs[l]));
      L.polyline(path, { color, weight: 4, opacity: 0.8, dashArray: v.failed ? '6 8' : undefined }).bindTooltip(`${id}${v.failed ? ' (broken down)' : ''}`).addTo(layer);
      v.history.filter(h => locs[h.location]).forEach(h => L.circleMarker(toLL(locs[h.location]), { radius: 5, color: '#6b7280', fillColor: '#9ca3af', fillOpacity: 1 }).bindTooltip(`${h.stop_id} · done`).addTo(layer));
      v.rows.filter(x => locs[x.location]).forEach(x => { const p = toLL(locs[x.location]); pts.push(p); L.circleMarker(p, { radius: 7, color, fillColor: '#fff', fillOpacity: 1, weight: 3 }).bindTooltip(`${id} → ${x.stop_id} · ETA ${hhmm(x.arrival)}`).addTo(layer); });
    });
    s.scenario.deliveries.filter(d => s.plan.unassigned[d.id]).forEach(d => { const p = toLL(locs[d.location]); pts.push(p); L.circleMarker(p, { radius: 8, color: '#dc2626', fillColor: '#dc2626', fillOpacity: .9 }).bindTooltip(`${d.id} · unfulfilled`).addTo(layer); });
    map.fitBounds(L.latLngBounds(pts), { padding: [30, 30] });
  }, [s, ready]);
  return <div className="fleet-map"><div ref={el} className="map-canvas" aria-label="Fleet routes map" /><div className="map-status">Sim time {hhmm(s.plan.now)} · simulated positions</div></div>;
}

export function LiveFleet() {
  return <Page title="Live Fleet Map" description="Planned routes per vehicle, completed stops and unfulfilled orders." actions={<span className="small-badge">Simulated data</span>}>
    {s => <div className="fleet-layout">
      <section className="panel fleet-sidebar"><div className="panel-head"><h2>Vehicles</h2></div>
        <div style={{ padding: 14, fontSize: 12, display: 'grid', gap: 12 }}>{Object.entries(s.plan.vehicles).map(([id, v], i) => <div key={id} style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ width: 12, height: 12, borderRadius: 6, background: v.failed ? '#dc2626' : COLORS[i % COLORS.length] }} />
          <div><strong>{id}</strong> {v.failed ? <Tag s="broken" /> : <span className="badge-count">active</span>}<br /><small>{v.history.length} done · {v.rows.length} upcoming · cap {v.capacity}</small></div></div>)}
          <small>● red solid = unfulfilled order · grey = completed</small></div></section>
      <LiveMap s={s} />
    </div>}
  </Page>;
}

export function LiveRecords({ kind }: { kind: 'deliveries' | 'vehicles' | 'locations' }) {
  const meta = { deliveries: ['Deliveries', 'Orders, windows, assigned vehicle and status after the latest plan.'], vehicles: ['Vehicles & Drivers', 'Fleet capacity, status and route load.'], locations: ['Locations', 'Depot and customer destinations.'] }[kind];
  return <Page title={meta[0]} description={meta[1]}>
    {s => {
      if (kind === 'deliveries') return <DataTable empty="No deliveries" cols={['ID', 'Location', 'Weight', 'Window', 'Vehicle', 'ETA', 'Status', 'Note']} rows={s.vs_original.map((c: Compare) => [c.delivery, c.location, `${c.weight} kg`, c.window, c.vehicle_after ?? '—', hhmm(c.eta_after), <Tag key="t" s={c.status} />, c.reason])} />;
      if (kind === 'vehicles') return <DataTable empty="No vehicles" cols={['Vehicle', 'Capacity', 'Start', 'Status', 'Done', 'Upcoming', 'Upcoming load (kg)']} rows={s.scenario.vehicles.map(v => { const p = s.plan.vehicles[v.id]; const ids = new Set(p.rows.map(r => r.stop_id)); const kg = s.scenario.deliveries.filter(d => ids.has(d.id)).reduce((a, d) => a + d.weight, 0); return [v.id, v.capacity, v.start_time, p.failed ? 'Broken down' : 'Active', p.history.length, p.rows.length, kg]; })} />;
      return <DataTable empty="No locations" cols={['ID', 'Role', 'Grid X', 'Grid Y', 'Deliveries here']} rows={Object.entries(s.scenario.locations).map(([id, p]) => [id, id === s.scenario.depot ? 'Depot' : 'Customer', p.x, p.y, s.scenario.deliveries.filter(d => d.location === id).length])} />;
    }}
  </Page>;
}

const EXAMPLES = ['V2 broke down at 10:30', 'Road between C1 and C2 closed from 10:00 to 10:30', 'Urgent order to C3, 5kg, window 10:00-11:00'];

export function LiveDisruptions() {
  const act = useAct<Preview>();
  const [text, setText] = useState('');
  const [p, setP] = useState<Preview | null>(null);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  const preview = () => { setErr(''); setMsg(''); setP(null); act.mutate({ path: '/api/incident/text', body: { text } }, { onSuccess: r => { setP(r); if (!r.ok) setErr((r.errors || [r.message || 'Could not understand the incident']).join('; ')); }, onError: e => setErr((e as Error).message) }); };
  const apply = () => p?.id && act.mutate({ path: '/api/incident/apply', body: { id: p.id, confirm: true } }, { onSuccess: () => { setMsg(`Applied: ${p.incident?.description}. See the full impact on Compare Plans.`); setP(null); setText(''); }, onError: e => setErr((e as Error).message) });
  const discard = () => { if (p?.id) api('/api/incident/cancel', { id: p.id }).catch(() => {}); setP(null); };
  const changed = (p?.comparison || []).filter(c => c.status !== 'kept' || c.tag === 'new');
  return <Page title="Disruption Management" description="Describe an incident in plain text, preview the impact, then approve." actions={<Button asChild variant="outline"><Link to="/compare">Compare Plans</Link></Button>}>
    {() => <>
      <WorkflowNavigation current="/disruptions" />
      <section className="panel"><div className="form-body">
        <label className="field field-wide">Incident (plain text)<textarea value={text} onChange={e => setText(e.target.value)} placeholder="e.g. V2 broke down at 10:30" /><small>Nothing changes until you approve the preview.</small></label>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>{EXAMPLES.map(x => <button key={x} type="button" className="small-badge" onClick={() => setText(x)}>{x}</button>)}</div>
        <div className="form-actions"><Button disabled={!text.trim() || act.isPending} onClick={preview}><Send />{act.isPending ? 'Working…' : 'Preview impact'}</Button></div>
        {err && <p className="form-error" role="alert">{err}</p>}
        {msg && <p className="form-feedback" role="status">{msg}</p>}
      </div></section>
      {p?.ok && <section className="panel" style={{ marginTop: 18 }}>
        <div className="panel-head"><div><h2>Preview: {p.incident?.description}</h2><p>Strategy: {p.strategy} · {p.validation?.valid ? 'plan validated' : 'validation failed'}</p></div>
          <span style={{ display: 'flex', gap: 6 }}>{Object.entries(p.summary || {}).filter(([k]) => ['kept', 'moved', 'broken', 'new'].includes(k)).map(([k, v]) => <span key={k}><Tag s={k} /> {v}</span>)}</span></div>
        <div style={{ padding: '10px 18px', fontSize: 12 }}>{(p.log || []).map((l, i) => <p key={i} style={{ padding: '3px 0' }}>• {l}</p>)}</div>
        <div className="table-scroll"><table><thead><tr>{['Order', 'Window', 'Before', 'After', 'ETA after', 'Status', 'Why'].map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{changed.map(c => <tr key={c.delivery}><td>{c.delivery}</td><td>{c.window}</td><td>{c.vehicle_before ?? '—'}</td><td>{c.vehicle_after ?? '—'}</td><td>{hhmm(c.eta_after)}</td><td><Tag s={c.status} /></td><td>{c.reason}</td></tr>)}{!changed.length && <tr><td colSpan={7}>No existing order is affected.</td></tr>}</tbody></table></div>
        <div className="decision-strip" style={{ padding: '16px 18px' }}><div><strong>Approval required</strong><p>Applying changes the live plan. You can undo from the Overview.</p></div>
          <div className="decision-actions"><Button variant="outline" onClick={discard}><X />Discard</Button><Button disabled={act.isPending || p.accepted === false} onClick={apply}><Check />Approve &amp; apply</Button></div></div>
      </section>}
    </>}
  </Page>;
}

export function LiveCompare() {
  const [f, setF] = useState('all');
  return <Page title="Plan Comparison" description="Original plan vs current plan: what was kept, moved or broken." actions={<><Button asChild variant="outline"><a href={apiUrl('/api/export?format=xlsx')}><Download />Excel</a></Button><Button asChild variant="outline"><a href={apiUrl('/api/export?format=csv&report=comparison')}><Download />CSV</a></Button></>}>
    {s => {
      const rows = s.vs_original, count = (k: string) => rows.filter(r => r.status === k).length;
      return <>
        <WorkflowNavigation current="/compare" />
        <div className="metrics-grid">{(['kept', 'moved', 'broken', 'new'] as const).map(k => <Metric key={k} label={k[0].toUpperCase() + k.slice(1)} value={count(k)} sub={{ kept: 'unaffected or completed', moved: 'reassigned to another vehicle', broken: 'window or capacity lost', new: 'added by an urgent order' }[k]} icon={k === 'broken' ? TriangleAlert : CircleCheck} />)}<Metric label="Events" value={s.events.length} sub="applied incidents" icon={Clock3} /></div>
        <section className="panel"><div className="section-toolbar"><select className="control-select" aria-label="Filter" value={f} onChange={e => setF(e.target.value)}><option value="all">All orders</option>{['kept', 'moved', 'broken', 'new'].map(k => <option key={k}>{k}</option>)}</select><span className="badge-count">{s.events.map(e => e.incident.description).join(' → ') || 'No incident applied yet'}</span></div>
          <div className="table-scroll"><table><thead><tr>{['Order', 'Location', 'Window', 'Vehicle before', 'Vehicle after', 'ETA before', 'ETA after', 'Δ min', 'Status', 'Reason'].map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>
            {rows.filter(r => f === 'all' || r.status === f).map(r => <tr key={r.delivery}><td>{r.delivery}</td><td>{r.location}</td><td>{r.window}</td><td>{r.vehicle_before ?? '—'}</td><td>{r.vehicle_after ?? '—'}</td><td>{hhmm(r.eta_before)}</td><td>{hhmm(r.eta_after)}</td><td>{Math.round(r.eta_delta)}</td><td><Tag s={r.status} /></td><td>{r.reason}</td></tr>)}</tbody></table></div></section>
      </>;
    }}
  </Page>;
}

export function LiveReports() {
  return <Page title="Analytics & Reports" description="Plan quality for the current session." actions={<Button asChild variant="outline"><a href={apiUrl('/api/export?format=xlsx')}><Download />Export Excel</a></Button>}>
    {s => { const m = s.plan.metrics, u = m.peak_utilization_pct as unknown as Record<string, number> | number;
      return <><div className="metrics-grid">
        <Metric label="Deliveries" value={m.deliveries} sub="in scenario" icon={Package} /><Metric label="Completed" value={m.completed} sub="so far" icon={CircleCheck} /><Metric label="Unfulfilled" value={m.unfulfilled} sub="flagged with reasons" icon={TriangleAlert} /><Metric label="Total travel" value={`${Math.round(m.total_travel)} min`} sub="all vehicles" icon={Truck} /><Metric label="Total waiting" value={`${Math.round(m.total_wait)} min`} sub="early arrivals" icon={Clock3} /></div>
        <section className="panel"><div className="panel-head"><div><h2>Peak capacity utilization</h2><p>Highest load reached on each route.</p></div></div>
          <div style={{ padding: '4px 18px 16px', fontSize: 12 }}>{typeof u === 'object' && u ? Object.entries(u).map(([id, v]) => <p key={id} style={{ padding: '8px 0' }}><strong>{id}</strong> — {Math.round(v)}%</p>) : <p>{String(u)}%</p>}</div></section></>; }}
  </Page>;
}
