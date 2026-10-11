import { createFileRoute } from '@tanstack/react-router';
import { PlanningPage } from '@/components/reroute/workspace';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/planning')({
 head: () => pageHead('Delivery Planning', 'Configure delivery planning inputs and operational constraints in ReRoute.'),
 component: PlanningPage,
});
