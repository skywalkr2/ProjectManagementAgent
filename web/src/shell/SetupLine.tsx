// Today's setup line (design 7.7): one row while first-run setup is unfinished, with how far along it is, the next step and
// a button that opens the setup guide at it. It replaces the start-here card; hiding it is remembered in this browser only.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { IconButton } from "../ui/IconButton";
import { MenuButton } from "../ui/MenuButton";
import { Pill } from "../ui/Pill";
import styles from "./SetupLine.module.css";

const KEY = "start-here-hidden";

function hidden(workspace: string): boolean {
  try {
    return window.localStorage.getItem(`${KEY}:${workspace}`) === "1";
  } catch {
    return false;
  }
}

function remember(workspace: string) {
  try {
    window.localStorage.setItem(`${KEY}:${workspace}`, "1");
  } catch {
    // Storage can be blocked; the line then comes back next time, which is harmless.
  }
}

export function SetupLine(props: { workspace: string; onOpenGuide: (step: string) => void }) {
  const { t, has } = useWords();
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  const [gone, setGone] = useState(() => hidden(props.workspace));
  if (gone || !setup.data || setup.data.finished) return null;
  const steps = setup.data.steps;
  const next = steps.find((s) => !s.done && !s.skipped);
  if (!next) return null;
  const finished = steps.filter((s) => s.done || s.skipped).length;
  const label = next.label || (has(`setup_step.${next.id}`) ? t(`setup_step.${next.id}`) : next.id);
  return (
    <section className={styles.line} aria-label={t("setup_line.label")} data-setup-line="">
      <Pill>{t("setup_line.count", { done: finished, total: steps.length })}</Pill>
      <div
        className={styles.progress}
        role="progressbar"
        aria-label={t("setup_line.progress")}
        aria-valuemin={0}
        aria-valuemax={steps.length}
        aria-valuenow={finished}
        aria-valuetext={t("setup_line.count", { done: finished, total: steps.length })}
      >
        <span className={styles.bar} style={{ width: `${(finished / steps.length) * 100}%` }} />
      </div>
      <p className={styles.next}>{t("setup_line.next", { step: label })}</p>
      <div className={styles.actions}>
        <Button size="sm" onClick={() => props.onOpenGuide(next.id)}>
          {t("setup_line.continue")}
        </Button>
        <MenuButton
          groups={[
            {
              id: "setup",
              entries: [
                {
                  id: "hide",
                  label: t("setup_line.hide"),
                  run: () => {
                    remember(props.workspace);
                    setGone(true);
                  },
                },
              ],
            },
          ]}
          trigger={<IconButton icon="more" size="sm" label={t("menu.more", { what: t("setup_line.what") })} tooltip={false} />}
        />
      </div>
    </section>
  );
}
