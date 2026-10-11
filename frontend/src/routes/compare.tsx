import { createFileRoute } from '@tanstack/react-router';
import { ComparePage } from '@/components/reroute/workspace';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/compare')({
 head: () => pageHead('Plan Comparison', 'Compare original and revised delivery plans before approval in ReRoute.'),
 component: ComparePage,
});
