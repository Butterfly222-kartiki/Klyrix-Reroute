import { LayoutDashboard, Map, Route, TriangleAlert, GitCompareArrows, Package, Truck, MapPin, ChartNoAxesCombined, Settings2 } from 'lucide-react';
export const navigation = [
  { label: 'Overview', path: '/', icon: LayoutDashboard },
  { label: 'Live Fleet Map', path: '/fleet', icon: Map },
  { label: 'Delivery Planning', path: '/planning', icon: Route },
  { label: 'Disruptions', path: '/disruptions', icon: TriangleAlert },
  { label: 'Compare Plans', path: '/compare', icon: GitCompareArrows },
  { label: 'Deliveries', path: '/deliveries', icon: Package },
  { label: 'Vehicles & Drivers', path: '/vehicles', icon: Truck },
  { label: 'Locations', path: '/locations', icon: MapPin },
  { label: 'Analytics & Reports', path: '/reports', icon: ChartNoAxesCombined },
  { label: 'Settings & Integrations', path: '/settings', icon: Settings2 },
] as const;
export function pageHead(title: string, description: string) { return { meta: [{ title: `${title} · ReRoute` }, { name: 'description', content: description }, { property: 'og:title', content: `${title} · ReRoute` }, { property: 'og:description', content: description }, { property: 'og:type', content: 'website' }, { name: 'twitter:card', content: 'summary_large_image' }] }; }
