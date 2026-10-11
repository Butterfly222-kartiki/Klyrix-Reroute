export function validateTimeRange(start: string, end: string): string | undefined {
 if (start && end && end <= start) return 'End time must be after the start time.';
 return undefined;
}
