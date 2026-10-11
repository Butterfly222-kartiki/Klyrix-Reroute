import { createFileRoute } from '@tanstack/react-router';
import { LiveOverview } from '@/components/reroute/live';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/')({
 head: () => pageHead('Operations Overview', 'Monitor your fleet, delivery exceptions, and operational planning in ReRoute.'),
 component: LiveOverview,
});
