import { createFileRoute } from '@tanstack/react-router';
import { LiveCompare } from '@/components/reroute/live';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/compare')({
 head: () => pageHead('Plan Comparison', 'Compare original and revised delivery plans before approval in ReRoute.'),
 component: LiveCompare,
});
