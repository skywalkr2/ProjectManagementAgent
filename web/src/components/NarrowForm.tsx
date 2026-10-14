// Narrowing what an entry or a rule applies to (design 7.18): only some projects, or every project except some. A rule
// that already applies to named projects can only be limited to those, never widened here.
import { useEffect, useId, useRef, useState } from "react";
import type { S } from "../lib/api";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import styles from "./Knowledge.module.css";

type Mode = "projects" | "workspace";

export function NarrowForm(props: {
  scope: S["Scope"];
  projects: S["ProjectView"][];
  onSave: (scope: S["Scope"]) => void;
  onCancel: () => void;
}) {
  const { t } = useWords();
  const { scope } = props;
  const named = scope.scope === "projects";
  const [mode, setMode] = useState<Mode>(named || !(scope.except ?? []).length ? "projects" : "workspace");
  const [chosen, setChosen] = useState<string[]>(named ? [...(scope.projects ?? [])] : [...(scope.except ?? [])]);
  const group = useId();
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => first.current?.focus(), []);
  // A rule limited to named projects can only be limited further, to some of those.
  const choices = named ? props.projects.filter((p) => (scope.projects ?? []).includes(p.id)) : props.projects;
  const switchTo = (next: Mode) => {
    setMode(next);
    setChosen([]);
  };
  const toggle = (id: string) => setChosen((now) => (now.includes(id) ? now.filter((x) => x !== id) : [...now, id]));
  const save = () =>
    props.onSave({ ...scope, scope: mode, projects: mode === "projects" ? chosen : [], except: mode === "workspace" ? chosen : [] });
  const none = chosen.length === 0;
  return (
    <fieldset
      className={styles.narrow}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          props.onCancel();
        }
      }}
    >
      <legend>{t("knowledge.narrow.title")}</legend>
      <label className={styles.choice}>
        <input ref={first} type="radio" name={group} checked={mode === "projects"} onChange={() => switchTo("projects")} />
        {t("knowledge.narrow.only")}
      </label>
      {!named && (
        <label className={styles.choice}>
          <input type="radio" name={group} checked={mode === "workspace"} onChange={() => switchTo("workspace")} />
          {t("knowledge.narrow.except")}
        </label>
      )}
      <ul className={styles.projects} aria-label={t("knowledge.narrow.projects")}>
        {choices.map((p) => (
          <li key={p.id}>
            <label className={styles.choice}>
              <input type="checkbox" checked={chosen.includes(p.id)} onChange={() => toggle(p.id)} />
              {p.name}
            </label>
          </li>
        ))}
      </ul>
      <div className={styles.buttons}>
        <Button variant="primary" size="sm" disabled={none} reason={t("knowledge.narrow.choose")} onClick={save}>
          {t("knowledge.narrow.save")}
        </Button>
        <Button size="sm" onClick={props.onCancel}>
          {t("action.cancel")}
        </Button>
      </div>
    </fieldset>
  );
}
