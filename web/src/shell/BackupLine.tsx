// Today's backup line (design 7.7): one row while no off-device backup is set up, none has succeeded yet, the last one
// failed or the last one is overdue. It says what to do first and why after, with the one button that does it. It goes
// away by itself once a backup is current, so the header chip's age is the only reminder left.
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { backupLineText } from "../lib/backup";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Pill } from "../ui/Pill";
import styles from "./BackupLine.module.css";

export function BackupLine(props: { onOpenGuide: (step: string) => void }) {
  const { t } = useWords();
  const act = useAct();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const b = status.data?.backup;
  if (!b?.needs_attention) return null;
  const run = () => void act(() => api.backup(), () => ({ message: t("toast.backup_ran") }));
  return (
    <section className={styles.line} aria-label={t("backup.line.label")} data-backup-line="">
      <Pill>{t("backup.line.label")}</Pill>
      <p className={styles.text}>{backupLineText(b, t)}</p>
      {b.configured ? (
        <Button size="sm" onClick={run}>
          {t("backup.now")}
        </Button>
      ) : (
        <Button size="sm" onClick={() => props.onOpenGuide("backup")}>
          {t("status.backup_set_up")}
        </Button>
      )}
    </section>
  );
}
