import { createFileRoute } from '@tanstack/react-router';
import { LiveReports } from '@/components/reroute/live';
import { pageHead } from '@/lib/reroute';
export const Route = createFileRoute('/reports')({
 head: () => pageHead('Analytics & Reports', 'Review verified fleet and delivery performance in ReRoute.'),
 component: LiveReports,
});
