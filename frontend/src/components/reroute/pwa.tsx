import { useEffect, useState } from 'react';
import { Download, Smartphone, WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';

/** Registers the service worker once on the client. */
export function usePwaRegister() {
  useEffect(() => {
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  }, []);
}

export function useOnline() {
  const [on, setOn] = useState(true);
  useEffect(() => {
    setOn(navigator.onLine);
    const u = () => setOn(true), d = () => setOn(false);
    addEventListener('online', u); addEventListener('offline', d);
    return () => { removeEventListener('online', u); removeEventListener('offline', d); };
  }, []);
  return on;
}

export function OfflineBadge() {
  return useOnline() ? null : <span className="small-badge"><WifiOff size={12} /> Offline · showing last saved data</span>;
}

/** "Install app" button (Android/desktop) or Add-to-Home-Screen hint (iOS). Hidden once installed. */
export function InstallButton() {
  const [evt, setEvt] = useState<any>(null);
  const [ios, setIos] = useState(false);
  const [standalone, setStandalone] = useState(true);
  useEffect(() => {
    const h = (e: Event) => { e.preventDefault(); setEvt(e); };
    addEventListener('beforeinstallprompt', h);
    setIos(/iphone|ipad|ipod/i.test(navigator.userAgent));
    setStandalone(matchMedia('(display-mode: standalone)').matches || (navigator as any).standalone === true);
    return () => removeEventListener('beforeinstallprompt', h);
  }, []);
  if (standalone) return null;
  if (evt) return <Button variant="outline" onClick={async () => { evt.prompt(); await evt.userChoice; setEvt(null); }}><Download />Install app</Button>;
  if (ios) return <span className="small-badge"><Smartphone size={12} /> Share → Add to Home Screen</span>;
  return null;
}
