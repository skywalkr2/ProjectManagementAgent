// What the assistant learned (design 7.18): the line under a correction's card, and the parts the review lists share.
// The line says what was learned in plain words, with the reach it will have (narrowest by default, widened by a pick
// from a list) and the one click each of Keep, Just this time, Edit and Discard. Keep shows the restatement and its
// reach, with the words it came from beside it, marked when they came from outside. Learning from the person's own
// words is already kept and shows Undo instead; while the assistant is still learning the line says so.
import { useQuery } from "@tanstack/react-query";
import { useId, useMemo, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { reachWords } from "../lib/knowledge";
import { reachChoices, useReachNames, useReachWords, type ReachChoice } from "../lib/reach";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Drawer } from "../ui/Drawer";
import { entryHref } from "./Because";
import styles from "./Learned.module.css";

export type Proposal = S["ProposalView"];

/** A project's name for a line of words; a project that is gone reads as "a project". */
export function useProjectNames(): (id: string) => string {
  const { t } = useWords();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  return (id) => names.get(id) ?? t("reach.unknown_project");
}

export function useLearned() {
  return useQuery({ queryKey: ["learned"], queryFn: api.learned });
}

/** Everything a proposal's controls need: the reach to pick and its words, the four acts, and whether the edit form or
 * the discard form is open. Each act goes through at once and offers Undo. */
export function useProposal(p: Proposal) {
  const wording = useWords();
  const { t } = wording;
  const act = useAct();
  const names = useProjectNames();
  const words = useReachWords(names);
  const reach = useReachNames();
  const choices = useMemo(() => reachChoices(p.applies_to), [p.applies_to]);
  const [chosen, setChosen] = useState<ReachChoice["id"]>("proposed");
  const [editing, setEditing] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const scope = choices.find((c) => c.id === chosen)?.scope ?? p.applies_to;
  // The chosen reach in plain words, with the projects it leaves out.
  const reachSaid = reachWords(scope, reach.names, wording);

  const keep = (text?: string) =>
    act(
      () =>
        api.keepKnowledge(p.id, {
          read_version: p.version,
          ...(chosen !== "proposed" ? { applies_to: scope } : {}),
          ...(text !== undefined && text !== p.text ? { text } : {}),
        }),
      (done) => ({ message: t("toast.learned_kept"), undo: () => api.undo(done.changeset) }),
    );
  const justThisTime = () =>
    act(
      () => api.justThisTime(p.id, p.version),
      (done) => ({ message: t("toast.learned_just_this_time"), undo: () => api.undo(done.changeset) }),
    );
  const discard = (reason: string) =>
    act(
      () => api.discardKnowledge(p.id, p.version, reason.trim()),
      (done) => ({ message: t("toast.learned_discarded"), undo: () => api.undo(done.changeset) }),
    );
  return {
    choices,
    chosen,
    setChosen,
    words,
    reachNow: words(choices.find((c) => c.id === chosen) ?? choices[0]),
    reachSaid,
    keep,
    justThisTime,
    discard,
    editing,
    setEditing,
    discarding,
    setDiscarding,
  };
}

/** The reach to keep it for, as a list to pick from. */
export function ReachPicker(props: {
  choices: ReachChoice[];
  value: ReachChoice["id"];
  onChange: (id: ReachChoice["id"]) => void;
  words: (choice: ReachChoice) => string;
  /** The chosen reach in plain words, shown beside the list. */
  said: string;
}) {
  const { t } = useWords();
  const id = useId();
  const saidId = `${id}-said`;
  return (
    <span className={styles.reach}>
      <label htmlFor={id}>{t("learned.keep_for")}</label>
      <select
        id={id}
        value={props.value}
        aria-describedby={saidId}
        onChange={(e) => props.onChange(e.target.value as ReachChoice["id"])}
      >
        {props.choices.map((c) => (
          <option key={c.id} value={c.id}>
            {props.words(c)}
          </option>
        ))}
      </select>
      <span id={saidId} className={styles.reachSaid} data-reach-said="">
        {props.said}
      </span>
    </span>
  );
}

/** The words a proposal was learned from, beside it, marked when they came from outside. */
export function ProposalEvidence(props: { p: Proposal }) {
  const { t } = useWords();
  const { p } = props;
  const quote = p.evidence?.quote;
  if (!quote) return null;
  return (
    <p className={styles.evidence}>
      {t("learned.evidence")} <q>{quote}</q>
      {p.trust === "untrusted" && (
        <>
          {" "}
          <span className="tag">{t("learned.from_outside")}</span>
        </>
      )}
    </p>
  );
}

/** The entry a proposal would merge with, as a link to it with whether it is kept or still waiting. Nothing when it
 * overlaps nothing. */
export function ProposalOverlap(props: { p: Proposal }) {
  const { t } = useWords();
  const twin = props.p.overlaps_with;
  if (!twin) return null;
  return (
    <p className={styles.evidence} data-overlaps={twin.id}>
      {t("learned.overlaps")} <a href={entryHref(twin)}>{twin.text}</a> · {t(twin.status === "active" ? "learned.overlaps.kept" : "learned.overlaps.waiting")}
    </p>
  );
}

/** The wording of a proposal in a box, with the reach beside it; Keep keeps what is shown as the person's own words. */
function EditForm(props: { p: Proposal; state: ReturnType<typeof useProposal>; onClose: () => void }) {
  const { t } = useWords();
  const { p, state } = props;
  const id = useId();
  const [text, setText] = useState(p.text);
  return (
    <form
      className={styles.form}
      onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim()) return;
        void state.keep(text.trim()).then((done) => done && props.onClose());
      }}
    >
      <label htmlFor={id}>{t("learned.edit_label")}</label>
      <textarea id={id} autoFocus value={text} onChange={(e) => setText(e.target.value)} />
      <ReachPicker choices={state.choices} value={state.chosen} onChange={state.setChosen} words={state.words} said={state.reachSaid} />
      <ProposalEvidence p={p} />
      <div className={styles.formActs}>
        <Button onClick={props.onClose}>{t("action.cancel")}</Button>
        <Button type="submit" variant="primary" disabled={!text.trim()}>
          {t("learned.keep")}
        </Button>
      </div>
    </form>
  );
}

/** Why it was wrong, if the person says; Discard keeps the proposal with that reason. */
function DiscardForm(props: { onDiscard: (reason: string) => Promise<unknown>; onClose: () => void }) {
  const { t } = useWords();
  const id = useId();
  const [reason, setReason] = useState("");
  return (
    <form
      className={styles.form}
      onSubmit={(e) => {
        e.preventDefault();
        void props.onDiscard(reason).then((done) => done && props.onClose());
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onClose();
      }}
    >
      <label htmlFor={id}>{t("learned.discard_label")}</label>
      <input id={id} type="text" autoFocus value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className={styles.formActs}>
        <Button onClick={props.onClose}>{t("action.cancel")}</Button>
        <Button type="submit" variant="primary">
          {t("learned.discard")}
        </Button>
      </div>
    </form>
  );
}

/** The forms a proposal's Edit and Discard open, shown where the proposal is. */
export function ProposalForms(props: { p: Proposal; state: ReturnType<typeof useProposal> }) {
  const { state, p } = props;
  return (
    <>
      {state.editing && <EditForm p={p} state={state} onClose={() => state.setEditing(false)} />}
      {state.discarding && <DiscardForm onDiscard={state.discard} onClose={() => state.setDiscarding(false)} />}
    </>
  );
}

/** The line for a proposal under its card. Edit opens a drawer. */
function ProposalLine(props: { p: Proposal }) {
  const { t, tn } = useWords();
  const { p } = props;
  const state = useProposal(p);
  return (
    <div className={styles.line} data-learned={p.id}>
      <p className={styles.said}>
        <span className={styles.label}>{t("learned.label")}</span> {p.text}
      </p>
      <ProposalEvidence p={p} />
      <ProposalOverlap p={p} />
      {p.just_this_time_before > 0 && <p className={styles.hint}>{tn("learned.said_just_this_time", p.just_this_time_before)}</p>}
      <div className={styles.acts}>
        <ReachPicker choices={state.choices} value={state.chosen} onChange={state.setChosen} words={state.words} said={state.reachSaid} />
        <Button size="sm" variant="primary" onClick={() => void state.keep()}>
          {t("learned.keep")}
        </Button>
        <Button size="sm" onClick={() => void state.justThisTime()}>
          {t("learned.just_this_time")}
        </Button>
        <Button size="sm" onClick={() => state.setEditing(true)}>
          {t("learned.edit")}
        </Button>
        <Button size="sm" onClick={() => state.setDiscarding(true)}>
          {t("learned.discard")}
        </Button>
      </div>
      {state.discarding && <DiscardForm onDiscard={state.discard} onClose={() => state.setDiscarding(false)} />}
      <Drawer open={state.editing} title={t("learned.edit_title")} onClose={() => state.setEditing(false)}>
        <EditForm p={p} state={state} onClose={() => state.setEditing(false)} />
      </Drawer>
    </div>
  );
}

/** The person's own words, already kept: what was learned, and Undo. */
function KeptLine(props: { line: S["LearnedLine"] }) {
  const { t } = useWords();
  const act = useAct();
  const { line } = props;
  const undo = line.undo;
  return (
    <div className={styles.line} data-learned={line.proposal?.id}>
      <p className={styles.said}>
        <span className={styles.label}>{t("learned.label")}</span> {line.proposal?.text}
      </p>
      {undo && (
        <div className={styles.acts}>
          <Button size="sm" onClick={() => void act(() => api.undo(undo), () => ({ message: t("toast.learned_undone") }))}>
            {t("learned.undo")}
          </Button>
        </div>
      )}
    </div>
  );
}

function LearningLine(props: { line: S["LearnedLine"] }) {
  const { t } = useWords();
  return (
    <div className={styles.line} role="status">
      <p className={styles.said}>{t("learned.learning")}</p>
      {props.line.waiting && <p className={styles.hint}>{props.line.waiting}</p>}
    </div>
  );
}

/** What was learned from the corrections on a card: those about its changes (a send-back, a routed answer, a change
 * asked for) and those about its records. Nothing is drawn while there is nothing to show. */
export function LearnedLines(props: { changesets?: Array<string | null | undefined>; records?: string[] }) {
  const { t } = useWords();
  const learned = useLearned();
  const changesets = (props.changesets ?? []).filter((c): c is string => !!c);
  const records = props.records ?? [];
  const found = (learned.data?.lines ?? []).filter(
    (line) => (line.changeset && changesets.includes(line.changeset)) || records.some((r) => (line.refs ?? []).includes(r)),
  );
  if (!found.length) return null;
  return (
    <ul className={styles.lines} aria-label={t("learned.lines")}>
      {found.map((line) => (
        <li key={line.signal}>
          {line.state === "learning" ? (
            <LearningLine line={line} />
          ) : line.state === "kept" ? (
            <KeptLine line={line} />
          ) : line.proposal ? (
            <ProposalLine p={line.proposal} />
          ) : null}
        </li>
      ))}
    </ul>
  );
}
