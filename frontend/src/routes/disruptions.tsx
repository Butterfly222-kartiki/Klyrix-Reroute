import { createFileRoute } from '@tanstack/react-router';
import { LiveDisruptions } from '@/components/reroute/live';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/disruptions')({
 head: () => pageHead('Disruption Management', 'Report logistics incidents and review replanning impact in ReRoute.'),
 component: LiveDisruptions,
});
