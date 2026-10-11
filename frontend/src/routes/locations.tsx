import { createFileRoute } from '@tanstack/react-router';
import { InventoryPage } from '@/components/reroute/workspace';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/locations')({
 head: () => pageHead('Locations', 'Manage depots, pickup points, and delivery destinations in ReRoute.'),
 component: () => <InventoryPage kind="locations" />,
});
