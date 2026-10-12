// One long text field on a record's page: its current text, who wrote what (three separate counts), its versions with
// Review on each one waiting, Edit in place, and its working copies.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { readable } from "../lib/records";
import { useWords } from "../lib/wording";
import { restoreFocus } from "./ModalPanel";
import { SafeText } from "./SafeText";
import { WorkingCopies } from "./WorkingCopies";
import { Skeleton } from "../ui/Skeleton";

type Review = (version: string, returnTo?: () => HTMLElement | null | undefined) => void;

/** Words by who wrote them. The three kinds are never folded together. */
export function authorshipCounts(spans: S["AuthorSpan"][]) {
  const counts = { person: 0, assistant: 0, assistant_edit: 0 };
  for (const span of spans) {
    if (span.kind === "person" || span.kind === "assistant" || span.kind === "assistant_edit") counts[span.kind] += span.words ?? 0;
  }
  return counts;
}

export function TextSection(props: { kind: string; id: string; field: string; help?: string; onReview: Review }) {
  const { t, tn } = useWords();
  const act = useAct();
  const { kind, id, field } = props;
  const base = useId();
  const text = useQuery({ queryKey: ["text", kind, id, field], queryFn: () => api.text(kind, id, field) });
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const editButton = useRef<HTMLButtonElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const titleId = `${base}-title`;
  const data = text.data;

  useEffect(() => {
    if (editing) area.current?.focus();
  }, [editing]);

  const startEdit = () => {
    setDraft(data?.text ?? "");
    setEditing(true);
  };
  const stopEdit = () => {
    setEditing(false);
    restoreFocus(() => editButton.current);
  };
  const save = async () => {
    setSaving(true);
    const result = await act(
      () => api.editText({ kind, id, field, text: draft }),
      (done) => ({
        message: t("text.saved"),
        undo: async () => {
          const report = await api.undo(done.changeset);
          if (!report.restored.length) throw new Error("not undone");
        },
      }),
    );
    setSaving(false);
    if (result) stopEdit();
  };

  const counts = data ? authorshipCounts(data.authorship) : null;
  const pending = (data?.versions ?? []).filter((v) => v.status === "pending");

  return (
    <section className="text-section" aria-labelledby={titleId}>
      <div className="heading">
        <h3 id={titleId}>{readable(field)}</h3>
        {data && !editing && (
          <button ref={editButton} type="button" className="btn" onClick={startEdit}>
            {t("text.edit")}
          </button>
        )}
      </div>
      {props.help && <p className="hint">{props.help}</p>}
      {text.isPending && <Skeleton />}
      {text.isError && (
        <p className="empty">
          {t("text.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void text.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      )}
      {data &&
        (editing ? (
          <div className="field">
            <label htmlFor={`${base}-edit`}>{t("text.edit_label", { field: readable(field) })}</label>
            <textarea
              id={`${base}-edit`}
              ref={area}
              className="msg"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.stopPropagation();
                  stopEdit();
                }
              }}
            />
            <div className="row-end">
              <button type="button" className="btn quiet" onClick={stopEdit}>
                {t("action.cancel")}
              </button>
              <button type="button" className="btn primary" disabled={saving} onClick={() => void save()}>
                {t(saving ? "text.saving" : "text.save")}
              </button>
            </div>
          </div>
        ) : data.text.trim() ? (
          <div className="text-body">
            <SafeText text={data.text} />
          </div>
        ) : (
          <p className="empty">{t("text.empty")}</p>
        ))}
      {counts && data && data.authorship.length > 0 && (
        <div>
          <span className="what" id={`${base}-who`}>
            {t("text.authorship")}
          </span>
          <ul className="plain-list" aria-labelledby={`${base}-who`}>
            <li>{tn("text.by_person", counts.person)}</li>
            <li>{tn("text.by_assistant", counts.assistant)}</li>
            <li>{tn("text.by_assistant_edit", counts.assistant_edit)}</li>
          </ul>
        </div>
      )}
      {data && data.versions.length > 0 && (
        <section aria-labelledby={`${base}-versions`}>
          <h4 id={`${base}-versions`} className="what">
            {t("text.versions")}
            {pending.length > 0 ? ` · ${tn("text.waiting", pending.length)}` : ""}
          </h4>
          <ul className="queue">
            {data.versions.map((v) => (
              <VersionRow key={v.id} version={v} current={data.current} onReview={props.onReview} />
            ))}
          </ul>
        </section>
      )}
      <WorkingCopies kind={kind} id={id} field={field} onReview={props.onReview} />
    </section>
  );
}

function VersionRow(props: { version: S["TextVersionView"]; current: number | null; onReview: Review }) {
  const { t, tn, has } = useWords();
  const { version } = props;
  const button = useRef<HTMLButtonElement>(null);
  const status = has(`text.status.${version.status}`) ? t(`text.status.${version.status}`) : readable(version.status);
  const source = has(`text.source.${version.source}`) ? t(`text.source.${version.source}`) : readable(version.source);
  const facts = [
    status,
    source,
    tn("text.words", version.words),
    ...(version.created_at ? [day(version.created_at)] : []),
    ...(version.number === props.current ? [t("text.shown_now")] : []),
  ];
  return (
    <li className="line" data-row>
      <div className="row pair">
        <div className="text">
          <div className="name">{t("text.version_n", { n: version.number })}</div>
          <span className="sub">{facts.join(" · ")}</span>
          {version.note && (
            <div className="sub">
              <SafeText text={version.note} />
            </div>
          )}
        </div>
        {version.status === "pending" && (
          <div className="acts">
            <button
              ref={button}
              type="button"
              className="btn primary"
              data-key="primary"
              aria-label={t("text.review_named", { n: version.number })}
              onClick={() => props.onReview(version.id, () => button.current)}
            >
              {t("text.review")}
            </button>
          </div>
        )}
      </div>
    </li>
  );
}
