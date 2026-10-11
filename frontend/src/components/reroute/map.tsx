import { useEffect, useRef, useState } from 'react';
import type { Map as LeafletMap } from 'leaflet';
import { Plus, Minus, Maximize, LocateFixed, WifiOff, LoaderCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
export function FleetMap({ compact = false, planLabel }: { compact?: boolean; planLabel?: string }) {
 const container = useRef<HTMLDivElement>(null);
 const map = useRef<LeafletMap | null>(null);
 const [status, setStatus] = useState<'loading'|'ready'|'error'>('loading');
 const [attempt, setAttempt] = useState(0);
 useEffect(() => {
  let cancelled = false; let instance: LeafletMap | undefined;
  setStatus('loading');
  const timeout = setTimeout(()=>{ if(!cancelled) setStatus(s=>s==='loading'?'error':s); },12000);
  import('leaflet').then(L => {
   if(cancelled || !container.current) return;
   instance=L.map(container.current,{zoomControl:false}).setView([28.6139,77.209],10);
   map.current=instance;
   L.tileLayer((import.meta.env.VITE_MAP_TILE_URL as string | undefined) || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap contributors',maxZoom:19}).addTo(instance)
    .on('load',()=>{if(!cancelled){clearTimeout(timeout);setStatus(s=>s==='error'?s:'ready');}})
    .on('tileerror',()=>{if(!cancelled)setStatus('error');});
   const observer=new ResizeObserver(()=>instance?.invalidateSize());
   observer.observe(container.current);
   instance.on('unload',()=>observer.disconnect());
  }).catch(()=>{if(!cancelled)setStatus('error');});
  return()=>{cancelled=true;clearTimeout(timeout);instance?.remove();map.current=null;};
 },[attempt]);
 return <div className={`fleet-map ${compact?'compact-map':''}`}>
  <div ref={container} className="map-canvas" aria-label="Geographic base map only. No fleet or route data connected."/>
  <div className="map-status"><WifiOff size={12}/> {planLabel?'Plan not selected':'Tracking disconnected'}</div>
  <div className="map-controls"><Button variant="outline" size="icon" disabled={status!=='ready'} aria-label="Zoom in" title="Zoom in" onClick={()=>map.current?.zoomIn()}><Plus/></Button><Button variant="outline" size="icon" disabled={status!=='ready'} aria-label="Zoom out" title="Zoom out" onClick={()=>map.current?.zoomOut()}><Minus/></Button><Button variant="outline" size="icon" disabled={status!=='ready'} aria-label="Reset base map view" title="Reset base map view" onClick={()=>map.current?.setView([28.6139,77.209],10)}><Maximize/></Button></div>
  <div className="map-empty" role="status" aria-live="polite"><div className="empty-icon">{status==='loading'?<LoaderCircle className="animate-spin" size={23}/>:<LocateFixed size={23}/>}</div><strong>{status==='loading'?'Loading base map…':status==='error'?'Base map unavailable':planLabel?`${planLabel} not selected`:'No fleet tracking connected'}</strong><p>{status==='error'?'Map tiles could not be loaded. Fleet tracking remains disconnected.':planLabel?'No plan routes or delivery stops are available for comparison.':'No vehicle positions, delivery stops, or active routes are available.'}</p>{status==='error'?<Button variant="outline" size="sm" className="mt-3" onClick={()=>setAttempt(a=>a+1)}><RefreshCw/>Retry map</Button>:<span><WifiOff size={12}/> {planLabel?'Awaiting operational plans':'Awaiting verified GPS data'}</span>}</div>
  <div className="map-base-label">Geographic base map only</div>
 </div>;
}
