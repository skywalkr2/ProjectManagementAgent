import type { S } from "./api";
import { backupAge } from "./backup";

const t = (key: string, vars: Record<string, string | number> = {}) => `${key}${JSON.stringify(vars)}`;
const status = (age_hours: number | null): S["BackupStatus"] => ({
  configured: true,
  last_success: null,
  age_hours,
  needs_attention: false,
  last_error: null,
  encrypted: false,
});

test("a backup's age is said in whole hours, singular for one, and in days from two days", () => {
  expect(backupAge(status(null), t)).toBeNull();
  expect(backupAge(status(0.2), t)).toBe("age.under_hour{}");
  expect(backupAge(status(1.4), t)).toBe('age.hours.one{"n":1}');
  expect(backupAge(status(3), t)).toBe('age.hours.other{"n":3}');
  expect(backupAge(status(100), t)).toBe('age.days{"n":4}');
});
