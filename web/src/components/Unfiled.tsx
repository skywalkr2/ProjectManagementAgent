// Unfiled work (design 7.14, open promise P14): what the assistant filed under no project, gathered in one place. Each row
// says what it is and has "File under…", a project picker that ends with "Add a project…"; choosing a project files it at
// once with Undo, and so does choosing one for several rows at a time. Every filing is a correction the assistant learns
// from (the server records it). With nothing unfiled the group isn't there, so it never shows a zero.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { whenText } from "../lib/dates";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";
import { ProjectPicker } from "./ProjectPicker";
import { SafeText } from "./SafeText";

type Item = S["UnfiledItem"];
const key = (item: Item) => `${item.kind}:${item.id}`;

/** Files items under a project at once, with one Undo; the toast says how many and where. */
function useFile() {
  const { tn } = useWords();
  const act = useAct();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  return async (items: Item[], project: string) => {
    const name = projects.data?.find((p) => p.id === project)?.name ?? "";
    // A project just added is not in the list the picker saw yet, so its name is looked for again.
    const where = name || (await api.projects()).find((p) => p.id === project)?.name || "";
    return act(
      () => api.fileUnfiled({ project, items: items.map((i) => ({ kind: i.kind, id: i.id, read_version: i.version })) }),
      (done) => ({
        message: tn("unfiled.filed", items.length, { project: where }),
        undo: async () => {
          const report = await api.undo(done.changeset);
          if (!report.restored.length) throw new Error("not undone");
        },
      }),
    );
  };
}

export function Unfiled() {
  const { t, tn } = useWords();
  const unfiled = useQuery({ queryKey: ["unfiled"], queryFn: api.unfiled });
  const file = useFile();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [filing, setFiling] = useState<string | null>(null);
  const items = unfiled.data?.items ?? [];
  if (items.length === 0) return null;
  const chosen = items.filter((i) => picked.has(key(i)));
  const toggle = (item: Item) =>
    setPicked((now) => {
      const next = new Set(now);
      if (!next.delete(key(item))) next.add(key(item));
      return next;
    });
  return (
    <section className="unfiled" aria-labelledby="unfiled-title" data-unfiled="">
      <div className="heading">
        <h2 id="unfiled-title">{t("unfiled.title")}</h2>
        <span className="hint">{tn("unfiled.count", items.length)}</span>
      </div>
      <p className="hint">{t("unfiled.why")}</p>
      {chosen.length > 0 && (
        <div className="bar" role="group" aria-label={t("unfiled.selected_label")}>
          <ProjectPicker
            id="unfiled-selected"
            label={tn("unfiled.file_selected", chosen.length)}
            value=""
            onChange={(project) => {
              void file(chosen, project).then(() => setPicked(new Set()));
            }}
          />
        </div>
      )}
      <ul className="queue">
        {items.map((item) => (
          <Row
            key={key(item)}
            pill={<Pill tone="neutral">{t(`unfiled.kind.${item.kind}`)}</Pill>}
            title={
              <label className="check-line">
                <input type="checkbox" checked={picked.has(key(item))} onChange={() => toggle(item)} aria-label={t("unfiled.select", { text: item.text })} />
                <SafeText text={item.text} />
              </label>
            }
            meta={[item.created_at ? t("unfiled.filed_on", { when: whenText(item.created_at) }) : "", item.trust === "untrusted" ? t("setup.note_outside") : ""]
              .filter(Boolean)
              .join(" · ")}
            primary={
              <Button size="sm" variant="primary" aria-expanded={filing === key(item)} onClick={() => setFiling(filing === key(item) ? null : key(item))}>
                {t("unfiled.file_under")}
              </Button>
            }
          >
            {filing === key(item) && (
              <ProjectPicker
                label={t("unfiled.project_for", { text: item.text })}
                value=""
                autoFocus
                onChange={(project) => {
                  void file([item], project).then(() => setFiling(null));
                }}
              />
            )}
          </Row>
        ))}
      </ul>
    </section>
  );
}
