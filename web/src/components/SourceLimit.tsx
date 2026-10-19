// A message its sender limited (design 6.35): who it is limited to and the sentence that says so, and the person's way to
// widen it: add people from the list, or remove the limit. Each is one click with an Undo toast.
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import { PersonPicker } from "./PersonPicker";

export function SourceLimit(props: { source: string; limit: S["SourceLimit"] }) {
  const { t } = useWords();
  const act = useAct();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [open, setOpen] = useState(false);
  const [person, setPerson] = useState("");
  const button = useRef<HTMLButtonElement>(null);
  const { limit } = props;
  const inside = new Set(limit.people.map((p) => p.id).filter(Boolean));
  const others = (people.data ?? []).filter((p) => !inside.has(p.id));
  const widen = (body: S["SourceWiden"], message: string) =>
    act(
      () => api.widenSource(props.source, body),
      (done) => ({
        message,
        undo: async () => {
          const report = await api.undo(done.changeset);
          if (!report.restored.length) throw new Error("not undone");
        },
      }),
    ).then((done) => {
      if (!done) return;
      setOpen(false);
      setPerson("");
    });
  return (
    <section className="source-limit" aria-label={t("source.limit.title")} data-source-limit="">
      <p>
        <strong>{t("source.limit.to", { names: limit.people.map((p) => p.name).join(", ") })}</strong>
      </p>
      {limit.why && <p className="hint block">{t("source.limit.why", { why: limit.why })}</p>}
      {limit.widened_by && <p className="hint block">{t("source.limit.widened_by", { name: limit.widened_by })}</p>}
      {!open ? (
        <button ref={button} type="button" className="btn" aria-expanded={false} onClick={() => setOpen(true)}>
          {t("source.limit.widen")}
        </button>
      ) : (
        <div className="source-widen">
          <PersonPicker label={t("source.limit.add_label")} value={person} onChange={setPerson} suggested={[]} people={others} noAdd />
          <div className="row-end">
            <button type="button" className="btn primary" disabled={!person} onClick={() => void widen({ people: [person], open: false }, t("source.limit.widened"))}>
              {t("source.limit.add")}
            </button>
            <button type="button" className="btn" onClick={() => void widen({ people: [], open: true }, t("source.limit.removed"))}>
              {t("source.limit.remove")}
            </button>
            <button type="button" className="btn quiet" onClick={() => setOpen(false)}>
              {t("source.limit.cancel")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
