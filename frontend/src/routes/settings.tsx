import { createFileRoute } from '@tanstack/react-router';
import { SettingsPage } from '@/components/reroute/workspace';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/settings')({
 head: () => pageHead('Settings & Integrations', 'Review operational data integration readiness in ReRoute.'),
 component: SettingsPage,
});
