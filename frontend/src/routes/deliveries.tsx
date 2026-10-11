import { createFileRoute } from '@tanstack/react-router';
import { InventoryPage } from '@/components/reroute/workspace';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/deliveries')({
 head: () => pageHead('Deliveries', 'Manage delivery assignments, priorities, and time windows in ReRoute.'),
 component: () => <InventoryPage kind="deliveries" />,
});
