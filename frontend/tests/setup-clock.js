// The shipped fixtures hold launch windows on 2026-10-05 to 2026-10-07. Several tests assert a countdown to the
// first window, which only exists while "now" is before it. Freeze the clock just before the fixtures so the
// tests give the same result on any day. Only Date is faked, so timers and promises still run for real.
import { beforeEach, vi } from 'vitest';

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-04T00:00:00Z'));
});
