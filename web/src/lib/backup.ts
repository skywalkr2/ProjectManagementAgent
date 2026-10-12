// How the screens word the backup state (design 4.15, 7.1, 7.7): the same words in the status popover, the header chip's
// age and Today's line.
import type { S } from "./api";

type T = (key: string, vars?: Record<string, string | number>) => string;

/** How long ago the last backup was, in words; null when none has succeeded. */
export function backupAge(b: S["BackupStatus"], t: T): string | null {
  if (b.age_hours === null) return null;
  const h = b.age_hours;
  return h < 1 ? t("age.under_hour") : h < 48 ? t("age.hours", { n: Math.floor(h) }) : t("age.days", { n: Math.floor(h / 24) });
}

/** The backup in one phrase: none set up, none yet, the last one failed, overdue, or how long ago it ran. */
export function backupText(b: S["BackupStatus"], t: T): string {
  if (!b.configured) return t("backup.none");
  const age = backupAge(b, t);
  if (age === null) return b.last_error ? t("backup.failed") : t("backup.never");
  return b.needs_attention ? t("backup.overdue", { age }) : t("backup.ok", { age });
}

/** What Today's line says: the action first, then why. */
export function backupLineText(b: S["BackupStatus"], t: T): string {
  if (!b.configured) return t("backup.line.none");
  const age = backupAge(b, t);
  if (age === null) return t(b.last_error ? "backup.line.failed" : "backup.line.never");
  return t("backup.line.overdue", { age });
}

/** What the header chip adds after its word once a backup has succeeded, so the age is always in view. */
export function backupChipAge(b: S["BackupStatus"], t: T): string | null {
  const age = backupAge(b, t);
  if (!b.configured || age === null) return null;
  return t(b.needs_attention ? "backup.chip_last" : "backup.ok", { age });
}
