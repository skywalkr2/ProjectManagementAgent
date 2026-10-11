// Reviewing what a plugin's action would do (design 5.3): one dialog for every action, wherever it was started. It asks
// for a proposal when it opens, asks again whenever a choice changes, and applies exactly the proposal on screen.
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Heading } from "react-aria-components";
import { api, type S } from "../lib/api";
import { useSize } from "../lib/files";
import { problemText } from "../lib/problem";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { ModalPanel, restoreFocus } from "./ModalPanel";
import { SafeText } from "./SafeText";

export type ActionTarget = { kind: string; id: string } | null;
type Choices = Record<string, string | boolean>;

const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/gif", "image/webp"]);

interface Opened {
  action: S["PersonActionView"];
  target: ActionTarget;
  opener: () => HTMLElement | null | undefined;
}

/** Start the review of an action from anywhere. Render `review` once; call `start` from a button or a menu item. */
export function useActionReview() {
  const [opened, setOpened] = useState<Opened | null>(null);
  const start = useCallback(
    (action: S["PersonActionView"], target: ActionTarget, returnTo?: () => HTMLElement | null | undefined) => {
      const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setOpened({ action, target, opener: returnTo ?? (() => (active?.isConnected ? active : null)) });
    },
    [],
  );
  const close = useCallback(() => {
    setOpened((current) => {
      if (current) restoreFocus(current.opener);
      return null;
    });
  }, []);
  const review = opened ? <ActionReview action={opened.action} target={opened.target} onClose={close} /> : null;
  return { start, review };
}

function decodeText(base64: string): string {
  try {
    const binary = atob(base64);
    return new TextDecoder("utf-8").decode(Uint8Array.from(binary, (c) => c.charCodeAt(0)));
  } catch {
    return "";
  }
}

export function ActionReview(props: { action: S["PersonActionView"]; target: ActionTarget; onClose: () => void }) {
  const { t, tn } = useWords();
  const client = useQueryClient();
  const { push } = useToasts();
  const size = useSize();
  const base = useId();
  const titleId = `${base}-title`;
  const [proposal, setProposal] = useState<S["ActionProposalView"] | null>(null);
  const [values, setValues] = useState<Choices>({});
  const [error, setError] = useState<{ text: string; applying: boolean } | null>(null);
  const [busy, setBusy] = useState(true);
  const [applying, setApplying] = useState(false);
  const latest = useRef(0);
  const sent = useRef<Choices>({});
  const { name } = props.action;
  const targetKind = props.target?.kind;
  const targetId = props.target?.id;

  const preview = useCallback(
    async (choices: Choices) => {
      const mine = ++latest.current;
      sent.current = choices;
      setBusy(true);
      setError(null);
      try {
        const target = targetKind && targetId ? { kind: targetKind, id: targetId } : null;
        const result = await api.actionPreview(name, { target, choices });
        if (mine !== latest.current) return;
        const shown = Object.fromEntries(result.choices.map((c) => [c.id, c.value]));
        sent.current = shown;
        setValues(shown);
        setProposal(result);
      } catch (err) {
        if (mine === latest.current) setError({ text: problemText(err, t), applying: false });
      } finally {
        if (mine === latest.current) setBusy(false);
      }
    },
    [name, targetKind, targetId, t],
  );

  useEffect(() => {
    void preview({});
    return () => {
      latest.current++;
    };
  }, [preview]);

  const change = (id: string, value: string | boolean) => {
    const next = { ...sent.current, [id]: value };
    setValues(next);
    void preview(next);
  };

  const apply = async () => {
    if (!proposal) return;
    setApplying(true);
    try {
      const done = await api.actionApply(proposal.token);
      await client.invalidateQueries();
      const parts = [
        done.applied ? tn("review.count_applied", done.applied) : "",
        done.held ? tn("review.count_waiting", done.held) : "",
        done.refused ? tn("review.count_refused", done.refused) : "",
      ].filter(Boolean);
      push({
        message: t("review.toast", { what: proposal.summary, counts: parts.length ? parts.join(", ") : t("review.count_none") }),
        undo: done.applied
          ? async () => {
              const report = await api.undo(done.changeset);
              await client.invalidateQueries();
              if (!report.restored.length) throw new Error("not undone");
            }
          : undefined,
      });
      props.onClose();
    } catch (err) {
      setError({ text: problemText(err, t), applying: true });
      setApplying(false);
    }
  };

  const again = () => void preview({ ...sent.current });
  const heading = proposal?.summary ?? props.action.label;

  return (
    <ModalPanel titleId={titleId} onClose={props.onClose}>
      <Heading slot="title" id={titleId}>
        {heading}
      </Heading>
      {!proposal && busy && (
        <p className="hint" role="status">
          {t("review.loading")}
        </p>
      )}
      {error && (
        <p className="problem-note" role="alert">
          {error.text}
        </p>
      )}
      {proposal && (
        <div className="review-body" aria-busy={busy}>
          {busy && (
            <p className="hint" role="status">
              {t("review.updating")}
            </p>
          )}
          {proposal.choices.length > 0 && (
            <div className="review-choices" role="group" aria-label={t("review.choices")}>
              {proposal.choices.map((c) => {
                const value = values[c.id] ?? c.value;
                const field = `${base}-choice-${c.id}`;
                const help = c.help ? `${field}-help` : undefined;
                return c.options.length > 0 ? (
                  <div className="field" key={c.id}>
                    <label htmlFor={field}>{c.label}</label>
                    <select id={field} value={String(value)} aria-describedby={help} onChange={(e) => change(c.id, e.target.value)}>
                      {c.options.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                    {c.help && (
                      <span id={help} className="hint">
                        {c.help}
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="field" key={c.id}>
                    <label className="check-line" htmlFor={field}>
                      <input id={field} type="checkbox" checked={value === true} aria-describedby={help} onChange={(e) => change(c.id, e.target.checked)} />
                      <span>{c.label}</span>
                    </label>
                    {c.help && (
                      <span id={help} className="hint">
                        {c.help}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <section aria-labelledby={`${base}-changes`}>
            <h3 id={`${base}-changes`} className="what">
              {t("review.changes")}
            </h3>
            {proposal.ops.length > 0 ? (
              <ul className="plain-list">
                {proposal.ops.map((op, i) => (
                  <li key={i}>{op.label.trim() || t("review.op_generic")}</li>
                ))}
              </ul>
            ) : (
              <p className="hint">{t("review.no_changes")}</p>
            )}
          </section>
          {proposal.files.length > 0 && (
            <section aria-labelledby={`${base}-files`}>
              <h3 id={`${base}-files`} className="what">
                {t("review.files")}
              </h3>
              <ul className="plain-list">
                {proposal.files.map((f, i) => (
                  <li key={i}>{t("review.file_line", { name: f.name, size: size(f.size) })}</li>
                ))}
              </ul>
            </section>
          )}
          {proposal.previews.some((p) => IMAGE_TYPES.has(p.media_type) || p.media_type === "text/plain") && (
            <section aria-labelledby={`${base}-previews`} className="previews">
              <h3 id={`${base}-previews`} className="what">
                {t("review.previews")}
              </h3>
              {proposal.previews.map((p, i) => (
                <Preview key={i} item={p} />
              ))}
            </section>
          )}
          {proposal.notes.length > 0 && (
            <section aria-labelledby={`${base}-notes`}>
              <h3 id={`${base}-notes`} className="what">
                {t("review.notes")}
              </h3>
              <ul className="plain-list">
                {proposal.notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onClose}>
          {t("action.cancel")}
        </button>
        {error && (
          <button type="button" className="btn" onClick={again}>
            {t(error.applying ? "review.run_again" : "action.try_again")}
          </button>
        )}
        <button type="button" className="btn primary" disabled={!proposal || busy || applying || !!error} onClick={() => void apply()}>
          {t(applying ? "review.applying" : "review.apply")}
        </button>
      </div>
    </ModalPanel>
  );
}

/** A picture or plain text the action rendered. Nothing else is ever shown, and nothing is rendered as markup. */
function Preview(props: { item: S["ActionPreviewItem"] }) {
  const { item } = props;
  const label = item.caption || item.name;
  if (IMAGE_TYPES.has(item.media_type)) {
    return (
      <figure className="preview">
        <img src={`data:${item.media_type};base64,${item.data_base64}`} alt={label} />
        {item.caption && <figcaption aria-hidden="true">{item.caption}</figcaption>}
      </figure>
    );
  }
  if (item.media_type === "text/plain") {
    return (
      <figure className="preview">
        <div className="preview-text" tabIndex={0} role="region" aria-label={label}>
          <SafeText text={decodeText(item.data_base64)} />
        </div>
        {item.caption && <figcaption aria-hidden="true">{item.caption}</figcaption>}
      </figure>
    );
  }
  return null;
}
