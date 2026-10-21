// Correcting what the assistant made, from the row's menu (design 6.8, 7.18). "Change this" takes a note and hands it to
// the assistant; a question's own menu changes the question itself (reword it, ask someone else, drop it, mark it as
// already sent), each at once with Undo. Both record the correction the assistant learns from.
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import { useAddOwnRequest } from "./HandIn";
import { NoteBox } from "./NoteBox";
import { PersonPicker } from "./PersonPicker";
import type { MenuAction } from "./RowMenu";

/** The kinds of item a change can be asked for: an action, a question, a decision, a calendar entry or a fact. */
export type ChangeKind = "action" | "question" | "decision" | "event" | "fact";

/** The "Change this" entry for a row's menu, and the note box it opens. `onClosed` runs when the box goes, so the row
 * can take focus back. */
export function useChangeThis(target: { kind: ChangeKind; id: string }, onClosed?: () => void): { entry: MenuAction; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const addOwn = useAddOwnRequest();
  const [open, setOpen] = useState(false);
  const send = (note: string) =>
    act(
      () => api.changeThis(target.kind, target.id, note),
      (done) => {
        // The work the note starts shows in What changed at once.
        if (done.request) addOwn(done.request);
        return { message: t("toast.change_asked") };
      },
    );
  const entry: MenuAction = { id: "change-this", label: t("change.this"), run: () => setOpen(true) };
  const form = open ? (
    <NoteBox
      sends={[{ label: t("change.send"), run: send }]}
      onClose={() => {
        setOpen(false);
        onClosed?.();
      }}
    />
  ) : null;
  return { entry, form };
}

type Mode = "reword" | "reroute" | "drop";

/** A question's menu entries and the small form each opens. "Already sent" is offered only for a question the person
 * hasn't sent yet (`canMarkSent`). */
export function useQuestionMenu(
  q: { id: string; title: string; text: string },
  options: { canMarkSent: boolean; onClosed?: () => void },
): { entries: MenuAction[]; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const [mode, setMode] = useState<Mode | null>(null);
  const close = () => {
    setMode(null);
    options.onClosed?.();
  };
  const undoing = (done: { changeset: string }) => () => api.undo(done.changeset);
  const entries: MenuAction[] = [
    { id: "reword", label: t("question.reword"), run: () => setMode("reword") },
    { id: "reroute", label: t("question.reroute"), run: () => setMode("reroute") },
    { id: "drop", label: t("question.drop"), note: t("question.drop_note"), run: () => setMode("drop") },
  ];
  if (options.canMarkSent) {
    entries.push({
      id: "sent",
      label: t("question.sent"),
      run: () =>
        void act(
          () => api.questionSent(q.id),
          (done) => ({ message: t("toast.question_sent"), undo: undoing(done) }),
        ),
    });
  }
  const form =
    mode === "reword" ? (
      <RewordForm q={q} onClose={close} />
    ) : mode === "reroute" ? (
      <RerouteForm q={q} onClose={close} />
    ) : mode === "drop" ? (
      <DropForm q={q} onClose={close} />
    ) : null;
  return { entries, form };
}

function Actions(props: { onClose: () => void; label: string; disabled: boolean }) {
  const { t } = useWords();
  return (
    <div className="row-end">
      <button type="button" className="btn quiet" onClick={props.onClose}>
        {t("action.cancel")}
      </button>
      <button type="submit" className="btn primary" disabled={props.disabled}>
        {props.label}
      </button>
    </div>
  );
}

function RewordForm(props: { q: { id: string; title: string; text: string }; onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const id = useId();
  const [title, setTitle] = useState(props.q.title);
  const [text, setText] = useState(props.q.text);
  const changed = {
    ...(title.trim() && title.trim() !== props.q.title ? { title: title.trim() } : {}),
    ...(text.trim() !== props.q.text ? { text: text.trim() } : {}),
  };
  const dirty = Object.keys(changed).length > 0;
  return (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!dirty) return;
        void act(
          () => api.rewordQuestion(props.q.id, changed),
          (done) => ({ message: t("toast.question_reworded"), undo: () => api.undo(done.changeset) }),
        ).then((done) => done && props.onClose());
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onClose();
      }}
    >
      <label className="hint" htmlFor={`${id}-title`}>
        {t("question.reword_title")}
      </label>
      <input id={`${id}-title`} type="text" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
      <label className="hint" htmlFor={`${id}-text`}>
        {t("question.reword_text")}
      </label>
      <textarea id={`${id}-text`} className="short" value={text} onChange={(e) => setText(e.target.value)} />
      <Actions onClose={props.onClose} label={t("question.reword_go")} disabled={!dirty} />
    </form>
  );
}

export function RerouteForm(props: { q: { id: string }; onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [person, setPerson] = useState("");
  const everyone = (people.data ?? []).filter((p) => p.status === "active");
  return (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!person) return;
        const name = everyone.find((p) => p.id === person)?.name ?? "";
        void act(
          () => api.rerouteQuestion(props.q.id, person),
          (done) => ({ message: t("toast.question_rerouted", { name }), undo: () => api.undo(done.changeset) }),
        ).then((done) => done && props.onClose());
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onClose();
      }}
    >
      <PersonPicker label={t("question.reroute_label")} value={person} onChange={setPerson} suggested={[]} people={everyone} autoFocus />
      <Actions onClose={props.onClose} label={t("question.reroute_go")} disabled={!person} />
    </form>
  );
}

function DropForm(props: { q: { id: string }; onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const id = useId();
  const [reason, setReason] = useState("");
  return (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!reason.trim()) return;
        void act(
          () => api.dropQuestion(props.q.id, reason.trim()),
          (done) => ({ message: t("toast.question_dropped"), undo: () => api.undo(done.changeset) }),
        ).then((done) => done && props.onClose());
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onClose();
      }}
    >
      <label className="hint" htmlFor={id}>
        {t("question.drop_label")}
      </label>
      <input id={id} type="text" autoFocus value={reason} onChange={(e) => setReason(e.target.value)} />
      <Actions onClose={props.onClose} label={t("question.drop_go")} disabled={!reason.trim()} />
    </form>
  );
}
