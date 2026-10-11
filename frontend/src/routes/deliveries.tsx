import { createFileRoute } from '@tanstack/react-router';
import { LiveRecords } from '@/components/reroute/live';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/deliveries')({
 head: () => pageHead('Deliveries', 'Manage delivery assignments, priorities, and time windows in ReRoute.'),
 component: () => <LiveRecords kind="deliveries" />,
});
