// Reviewing what a plugin's action would do (design 5.3): one dialog for every action, wherever it was started. It asks
// for a proposal when it opens, asks again whenever a choice changes, and applies exactly the proposal on screen.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Heading } from "react-aria-components";
import {
  changedRequests,
  countKept,
  countKeptRequests,
  followsDroppedItem,
  itemOf,
  opsWithTicks,
  requestKept,
  ticksOf,
  type Ticks,
} from "../lib/action-items";
import { api, type S } from "../lib/api";
import { useSize } from "../lib/files";
import { problemText } from "../lib/problem";
import { readableTail } from "../lib/records";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { ModalPanel, restoreFocus } from "./ModalPanel";
import { RowMenu } from "./RowMenu";
import { SafeText } from "./SafeText";

export type ActionTarget = { kind: string; id: string } | null;
type Choices = Record<string, string | boolean>;

/** More queued work than this gets "Keep all" and "Drop all". */
const REQUESTS_BEFORE_SET_ALL = 5;

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
  const [kept, setKept] = useState<Ticks>({});
  const [keptRequests, setKeptRequests] = useState<Ticks>({});
  const latest = useRef(0);
  const sent = useRef<Choices>({});
  const token = useRef<string | null>(null);
  const ticks = useRef<Ticks>({});
  const requestTicks = useRef<Ticks>({});
  const shownRequests = useRef<S["ActionRequestView"][]>([]);
  const { name } = props.action;
  const targetKind = props.target?.kind;
  const targetId = props.target?.id;

  const setTicks = useCallback((next: Ticks) => {
    ticks.current = next;
    setKept(next);
  }, []);

  const setRequestTicks = useCallback((next: Ticks) => {
    requestTicks.current = next;
    setKeptRequests(next);
  }, []);

  // Ticking never asks the action again; a changed choice does, and the ticks go along so they carry over.
  const preview = useCallback(
    async (choices: Choices, carry: boolean) => {
      const mine = ++latest.current;
      sent.current = choices;
      setBusy(true);
      setError(null);
      try {
        const target = targetKind && targetId ? { kind: targetKind, id: targetId } : null;
        const asked = ticks.current;
        const body: S["ActionRun"] = { target, choices };
        if (Object.keys(asked).length) body.kept = asked;
        if (carry && token.current) body.previous = token.current;
        const result = await api.actionPreview(name, body);
        if (mine !== latest.current) return;
        const shown = Object.fromEntries(result.choices.map((c) => [c.id, c.value]));
        sent.current = shown;
        token.current = result.token;
        // What the action says, except a tick the person changed while it was working.
        const fresh = ticksOf(result.items);
        for (const id of Object.keys(fresh)) {
          if (id in asked && ticks.current[id] !== asked[id]) fresh[id] = ticks.current[id];
        }
        setTicks(fresh);
        // The person's own ticks on queued work carry over to a request that is still the same one.
        const sameRequest = (a: S["ActionRequestView"], b: S["ActionRequestView"]) =>
          a.id === b.id && a.task === b.task && a.label === b.label && a.item === b.item && a.about?.id === b.about?.id;
        const carried: Ticks = {};
        for (const r of result.requests ?? []) {
          const before = shownRequests.current.find((old) => sameRequest(old, r));
          if (before && r.id in requestTicks.current) carried[r.id] = requestTicks.current[r.id];
        }
        shownRequests.current = result.requests ?? [];
        setRequestTicks(carried);
        setValues(shown);
        setProposal(result);
      } catch (err) {
        if (mine === latest.current) setError({ text: problemText(err, t), applying: false });
      } finally {
        if (mine === latest.current) setBusy(false);
      }
    },
    [name, targetKind, targetId, t, setTicks, setRequestTicks],
  );

  useEffect(() => {
    token.current = null;
    ticks.current = {};
    requestTicks.current = {};
    shownRequests.current = [];
    void preview({}, false);
    return () => {
      latest.current++;
    };
  }, [preview]);

  const change = (id: string, value: string | boolean) => {
    const next = { ...sent.current, [id]: value };
    setValues(next);
    void preview(next, true);
  };

  const tick = (ids: string[], value: boolean, requestIds: string[] = []) => {
    setTicks({ ...ticks.current, ...Object.fromEntries(ids.map((id) => [id, value])) });
    if (requestIds.length) tickRequests(requestIds, value);
  };
  const tickRequests = (ids: string[], value: boolean) =>
    setRequestTicks({ ...requestTicks.current, ...Object.fromEntries(ids.map((id) => [id, value])) });

  const apply = async () => {
    if (!proposal) return;
    setApplying(true);
    try {
      const items = proposal.items ?? [];
      const itemTicks = { ...ticksOf(items), ...ticks.current };
      const done = await api.actionApply(
        proposal.token,
        items.length ? itemTicks : undefined,
        changedRequests(proposal.requests ?? [], items, itemTicks, requestTicks.current),
      );
      await client.invalidateQueries();
      if (done.applied === 0 && done.refused > 0) {
        setError({ text: t("review.all_refused"), applying: true });
        setApplying(false);
        return;
      }
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

  const again = () => void preview({ ...sent.current }, false);
  const heading = proposal?.summary ?? props.action.label;
  const items = proposal?.items ?? [];
  const groups = proposal?.groups ?? [];
  const requests = proposal?.requests ?? [];
  const itemTicks = { ...ticksOf(items), ...kept };
  const inGroup = new Set(groups.map((g) => g.id));
  const looseChoices = (proposal?.choices ?? []).filter((c) => !c.group || !inGroup.has(c.group));
  const looseItems = items.filter((i) => !i.group || !inGroup.has(i.group));
  // "Keep all" and "Drop all" leave alone a request that follows a dropped item: it is dropped with it.
  const freeRequests = requests.filter((r) => !followsDroppedItem(r, items, itemTicks));
  const shownOps = proposal ? opsWithTicks(proposal, kept) : [];

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
          {looseChoices.length > 0 && (
            <div className="review-choices" role="group" aria-label={t("review.choices")}>
              {looseChoices.map((c) => (
                <ChoiceField key={c.id} base={base} choice={c} value={values[c.id] ?? c.value} onChange={change} />
              ))}
            </div>
          )}
          {groups.map((g) => {
            const own = items.filter((i) => i.group === g.id);
            const ownChoices = proposal.choices.filter((c) => c.group === g.id);
            const ownRequests = requests.filter((r) => r.group === g.id);
            if (!own.length && !ownChoices.length && !ownRequests.length) return null;
            return (
              <ItemSection
                key={g.id}
                base={base}
                heading={g.heading}
                explanation={g.explanation ?? ""}
                items={own}
                requests={ownRequests}
                allItems={items}
                requestTicks={keptRequests}
                choices={ownChoices}
                values={values}
                ticks={kept}
                onChoice={change}
                onTick={tick}
              />
            );
          })}
          {looseItems.length > 0 && (
            <ItemSection
              base={base}
              heading={t("review.items")}
              explanation=""
              items={looseItems}
              requests={[]}
              allItems={items}
              requestTicks={keptRequests}
              choices={[]}
              values={values}
              ticks={kept}
              onChoice={change}
              onTick={tick}
            />
          )}
          {(proposal.problems ?? []).length > 0 && (
            <div className="problem-note" role="alert">
              <p>{t("review.problems")}</p>
              <ul className="plain-list">
                {(proposal.problems ?? []).map((p, i) => (
                  <li key={i}>
                    <SafeText text={p} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {/* A proposal that only adds files or shows a preview has no changes to read back: saying "it won't change
              anything" about something that creates a file would contradict it. */}
          {(shownOps.length > 0 || (proposal.files.length === 0 && proposal.previews.length === 0)) && (
            <section aria-labelledby={`${base}-changes`}>
              <h3 id={`${base}-changes`} className="what">
                {t("review.changes")}
              </h3>
              {shownOps.length > 0 ? (
                <ul className="plain-list">
                  {shownOps.map((op, i) => (
                    <li key={i}>{op.label.trim() || t("review.op_generic")}</li>
                  ))}
                </ul>
              ) : (
                <p className="hint">{t("review.no_changes")}</p>
              )}
            </section>
          )}
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
          {requests.length > 0 && (
            <section aria-labelledby={`${base}-requests`}>
              <h3 id={`${base}-requests`} className="what">
                {t("review.requests")}
              </h3>
              {requests.length > REQUESTS_BEFORE_SET_ALL && (
                <div className="review-group-head">
                  <span className="hint">
                    {t("review.kept_count", { kept: countKeptRequests(requests, items, itemTicks, keptRequests), total: requests.length })}
                  </span>
                  <RowMenu
                    label={t("review.requests")}
                    actions={[
                      { id: "keep", label: t("review.keep_all"), run: () => tickRequests(freeRequests.map((r) => r.id), true) },
                      { id: "drop", label: t("review.drop_all"), run: () => tickRequests(freeRequests.map((r) => r.id), false) },
                    ]}
                  />
                </div>
              )}
              <ul className="review-items">
                {requests.map((r) => (
                  <RequestLine
                    key={r.id}
                    request={r}
                    item={itemOf(r, items)}
                    checked={requestKept(r, items, itemTicks, keptRequests)}
                    follows={followsDroppedItem(r, items, itemTicks)}
                    onTick={(value) => tickRequests([r.id], value)}
                  />
                ))}
              </ul>
              <p className="hint" aria-live="polite">
                {tn("review.requests_count", requests.length, { kept: countKeptRequests(requests, items, itemTicks, keptRequests) })}
              </p>
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
        <img src={`data:${item.media_type};base64,${item.data_base64}`} alt={item.alt || label} />
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

/** One choice: a pick from a list, a line of text, or on or off. */
function ChoiceField(props: {
  base: string;
  choice: S["ActionChoice"];
  value: string | boolean;
  onChange: (id: string, value: string | boolean) => void;
}) {
  const { choice: c, value } = props;
  const field = `${props.base}-choice-${c.id}`;
  const help = c.help ? `${field}-help` : undefined;
  const note = c.help ? (
    <span id={help} className="hint">
      {c.help}
    </span>
  ) : null;
  if (c.options.length > 0) {
    return (
      <div className="field">
        <label htmlFor={field}>{c.label}</label>
        <select id={field} value={String(value)} aria-describedby={help} onChange={(e) => props.onChange(c.id, e.target.value)}>
          {c.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {note}
      </div>
    );
  }
  if (c.text) {
    return (
      <div className="field">
        <label htmlFor={field}>{c.label}</label>
        <TextChoice id={field} help={help} value={String(value)} maxLength={c.max_length} onCommit={(v) => props.onChange(c.id, v)} />
        {note}
      </div>
    );
  }
  return (
    <div className="field">
      <label className="check-line" htmlFor={field}>
        <input id={field} type="checkbox" checked={value === true} aria-describedby={help} onChange={(e) => props.onChange(c.id, e.target.checked)} />
        <span>{c.label}</span>
      </label>
      {note}
    </div>
  );
}

/** A typed value: the action asks again when the person presses Enter or leaves the field with a changed value. */
function TextChoice(props: { id: string; help?: string; value: string; maxLength: number; onCommit: (value: string) => void }) {
  const [draft, setDraft] = useState(props.value);
  useEffect(() => setDraft(props.value), [props.value]);
  const commit = () => {
    if (draft !== props.value) props.onCommit(draft);
  };
  return (
    <input
      id={props.id}
      type="text"
      value={draft}
      maxLength={props.maxLength}
      aria-describedby={props.help}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        }
      }}
    />
  );
}

/** A group of items to keep or drop, with its explanation, its own choices and "Keep all" / "Drop all". */
function ItemSection(props: {
  base: string;
  heading: string;
  explanation: string;
  items: S["ActionItem"][];
  /** The queued work that belongs to this group: setting the group sets it too. */
  requests: S["ActionRequestView"][];
  allItems: S["ActionItem"][];
  requestTicks: Ticks;
  choices: S["ActionChoice"][];
  values: Choices;
  ticks: Ticks;
  onChoice: (id: string, value: string | boolean) => void;
  onTick: (ids: string[], value: boolean, requestIds?: string[]) => void;
}) {
  const { t } = useWords();
  const id = useId();
  const ids = props.items.map((i) => i.id);
  const requestIds = props.requests.map((r) => r.id);
  const itemTicks = { ...ticksOf(props.allItems), ...props.ticks };
  return (
    <section className="review-group" aria-labelledby={`${id}-h`}>
      <div className="review-group-head">
        <h3 id={`${id}-h`} className="what">
          {props.heading}
        </h3>
        {(props.items.length > 0 || props.requests.length > 0) && (
          <>
            <span className="hint">
              {props.items.length > 0
                ? t("review.kept_count", { kept: countKept(props.items, props.ticks), total: props.items.length })
                : t("review.kept_count", {
                    kept: countKeptRequests(props.requests, props.allItems, itemTicks, props.requestTicks),
                    total: props.requests.length,
                  })}
            </span>
            <RowMenu
              label={props.heading}
              actions={[
                { id: "keep", label: t("review.keep_all"), run: () => props.onTick(ids, true, requestIds) },
                { id: "drop", label: t("review.drop_all"), run: () => props.onTick(ids, false, requestIds) },
              ]}
            />
          </>
        )}
      </div>
      {props.explanation && <p className="hint">{props.explanation}</p>}
      {props.choices.map((c) => (
        <ChoiceField key={c.id} base={props.base} choice={c} value={props.values[c.id] ?? c.value} onChange={props.onChoice} />
      ))}
      {props.items.length > 0 && (
        <ul className="review-items">
          {props.items.map((item) => (
            <li key={item.id}>
              <label className="check-line">
                <input
                  type="checkbox"
                  checked={props.ticks[item.id] ?? item.kept}
                  aria-describedby={item.refused ? `${id}-${item.id}-why` : undefined}
                  onChange={(e) => props.onTick([item.id], e.target.checked)}
                />
                <span>{item.label}</span>
              </label>
              {item.refused && (
                <p className="hint" id={`${id}-${item.id}-why`}>
                  {t("review.item_refused", { reason: item.refused })}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Work the action also starts: a tick, what it is and, when there is one, the record it is about. One that goes with a
 * dropped item shows dropped and can't be ticked on its own. */
function RequestLine(props: {
  request: S["ActionRequestView"];
  item: S["ActionItem"] | undefined;
  checked: boolean;
  follows: boolean;
  onTick: (value: boolean) => void;
}) {
  const { t } = useWords();
  const id = useId();
  const { request: r } = props;
  const about = r.about;
  const record = useQuery({
    queryKey: ["record", about?.kind, about?.id],
    queryFn: () => api.record(about!.kind, about!.id),
    enabled: !!about,
  });
  const fields = record.data?.fields ?? {};
  const named = [fields.title, fields.name].find((v): v is string => typeof v === "string" && !!v.trim());
  const text = about ? t("review.request_about", { label: r.label, about: named ?? readableTail(about.kind) }) : r.label;
  const hint = props.follows && props.item ? t("review.request_follows", { item: props.item.label }) : "";
  return (
    <li>
      <label className="check-line">
        <input
          type="checkbox"
          checked={props.checked}
          disabled={props.follows}
          aria-describedby={hint ? `${id}-why` : undefined}
          onChange={(e) => props.onTick(e.target.checked)}
        />
        <span>{text}</span>
      </label>
      {r.note && <p className="hint">{r.note}</p>}
      {hint && (
        <p className="hint" id={`${id}-why`}>
          {hint}
        </p>
      )}
    </li>
  );
}
