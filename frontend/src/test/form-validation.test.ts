import { describe, expect, it } from 'vitest';
import { validateTimeRange } from '@/lib/form-validation';
describe('Incident time validation',()=>{
 it('rejects an end before the incident starts',()=>{expect(validateTimeRange('2026-10-12T09:00','2026-10-12T08:00')).toBe('End time must be after the start time.');});
 it('rejects an equal start and end',()=>{expect(validateTimeRange('2026-10-12T09:00','2026-10-12T09:00')).toBeDefined();});
 it('accepts an unknown recovery time',()=>{expect(validateTimeRange('2026-10-12T09:00','')).toBeUndefined();});
 it('accepts a future end',()=>{expect(validateTimeRange('2026-10-12T09:00','2026-10-12T10:00')).toBeUndefined();});
});
