import { createFileRoute } from '@tanstack/react-router';
import { LiveFleet } from '@/components/reroute/live';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/fleet')({
 head: () => pageHead('Live Fleet Map', 'Inspect fleet tracking availability and active delivery routes in ReRoute.'),
 component: LiveFleet,
});
