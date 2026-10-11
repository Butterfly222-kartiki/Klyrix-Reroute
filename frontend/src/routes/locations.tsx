import { createFileRoute } from '@tanstack/react-router';
import { LiveRecords } from '@/components/reroute/live';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/locations')({
 head: () => pageHead('Locations', 'Manage depots, pickup points, and delivery destinations in ReRoute.'),
 component: () => <LiveRecords kind="locations" />,
});
