import { createFileRoute } from '@tanstack/react-router';
import { InventoryPage } from '@/components/reroute/workspace';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/vehicles')({
 head: () => pageHead('Vehicles & Drivers', 'Inspect vehicle capacity, availability, and driver assignments in ReRoute.'),
 component: () => <InventoryPage kind="vehicles" />,
});
