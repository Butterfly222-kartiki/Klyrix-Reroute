import { createFileRoute } from '@tanstack/react-router';
import { LiveRecords } from '@/components/reroute/live';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/vehicles')({
 head: () => pageHead('Vehicles & Drivers', 'Inspect vehicle capacity, availability, and driver assignments in ReRoute.'),
 component: () => <LiveRecords kind="vehicles" />,
});
