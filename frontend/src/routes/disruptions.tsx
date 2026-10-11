import { createFileRoute } from '@tanstack/react-router';
import { DisruptionsPage } from '@/components/reroute/workspace';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/disruptions')({
 head: () => pageHead('Disruption Management', 'Report logistics incidents and review replanning impact in ReRoute.'),
 component: DisruptionsPage,
});
