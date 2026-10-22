// A reply the person owes (design 6.35, 7.7): one Today line, "Reply to Ana: Interior proofs", with the drafted reply under it
// marked as a draft until the person has copied, edited or written it. Copy reply is the one button (copying marks the draft
// reviewed, with Undo); No reply needed, Answered another way and Edit are in the row's menu. Each is the person's own change
// with Undo, and No reply needed is a correction the assistant learns from.
import { useId, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { copyMessage } from "../lib/copy";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { useMessageActs } from "./MessageActs";
import type { MenuAction } from "./RowMenu";

type Line = S["QueueLineView"];
type T = (key: string, vars?: Record<string, string | number>) => string;

/** The words of a reply line: who it is to and what the message was about. */
export function replyTitle(line: Line, t: T): string {
  const name = line.person_name ?? line.sender ?? t("queue.title.someone");
  return t("queue.reply.title", { name, subject: line.subject ?? "" });
}

export interface ReplyChoices {
  primary: { label: string; run: () => void } | null;
  menu: MenuAction[];
  /** The form a choice opened (the words of a different answer, the person's own reply), shown under the row. */
  form: ReactNode;
}

/** The choices for a reply line; for any other kind of line it holds nothing. The hook is always called, so a row can be any
 * kind. `onClosed` runs when a form goes, so the row can take the cursor back. */
export function useReplyChoices(line: Line, onClosed?: () => void): ReplyChoices {
  const { t } = useWords();
  const act = useAct();
  const { push } = useToasts();
  const [asking, setAsking] = useState<"answered" | "edit" | null>(null);
  const action = line.kind === "reply" ? ((line.actions ?? [])[0] ?? "") : "";
  // What the account the message came in on can do about it: when it can act, the reply goes after the person's yes.
  const message = useMessageActs(action || null, line.subject ?? "", !!action);
  if (line.kind !== "reply" || !action) return { primary: null, menu: [], form: null };

  const close = () => {
    setAsking(null);
    onClosed?.();
  };
  const draft = line.reply ?? "";
  const copy = async () => {
    if ((await copyMessage(draft)) === "blocked") {
      push({ message: t("toast.copy_blocked") });
      return;
    }
    // The copy is kept as it was copied, so the message that is sent can be matched to it; a failure to keep it never
    // stops the copy.
    void api.replyCopied(action).catch(() => undefined);
    // Copying is what approves the draft as it is; one already reviewed has nothing more to approve.
    if (line.reply_reviewed) {
      push({ message: t("queue.reply.copied_toast") });
      return;
    }
    await act(
      () => api.reviewReply(action, {}),
      (result) => ({ message: t("queue.reply.copied_toast"), undo: () => api.undo(result.changeset) }),
    );
  };
  const noReply: MenuAction = {
    id: "no-reply-needed",
    label: t("queue.reply.no_reply_needed"),
    run: () =>
      void act(
        () => api.dropAction(action, t("queue.reply.no_reply_reason")),
        (result) => ({ message: t("queue.reply.dropped_toast"), undo: () => api.undo(result.changeset) }),
      ),
  };
  const another: MenuAction = { id: "answered-another-way", label: t("queue.reply.answered_another_way"), run: () => setAsking("answered") };
  const edit: MenuAction = { id: "edit-reply", label: t("queue.reply.edit"), run: () => setAsking("edit") };

  const form =
    asking === "answered" ? (
      <AnsweredForm
        onSave={(note) =>
          void act(
            () => api.answeredAnotherWay(action, note ? { note } : {}),
            (result) => ({ message: t("queue.reply.answered_toast"), undo: () => api.undo(result.changeset) }),
          ).then((done) => done && close())
        }
        onCancel={close}
      />
    ) : asking === "edit" ? (
      <EditForm
        value={draft}
        onSave={(text) =>
          void act(
            () => api.reviewReply(action, { text }),
            (result) => ({ message: t("queue.reply.saved_toast"), undo: () => api.undo(result.changeset) }),
          ).then((done) => done && close())
        }
        onCancel={close}
      />
    ) : null;
  const shown = (
    <>
      {form}
      {message.form}
    </>
  );
  const toMessage = message.menu(["reply"]);
  const copyEntry: MenuAction = { id: "copy-reply", label: t("queue.reply.copy"), run: () => void copy() };
  if (draft && message.canAct) {
    return { primary: { label: t("queue.reply.send"), run: () => void message.replyNow(draft) }, menu: [copyEntry, ...toMessage, noReply, another, edit], form: shown };
  }
  return draft
    ? { primary: { label: t("queue.reply.copy"), run: () => void copy() }, menu: [...toMessage, noReply, another, edit], form: shown }
    : { primary: { label: t("queue.reply.write"), run: () => setAsking("edit") }, menu: [...toMessage, noReply, another], form: shown };
}

/** The draft under the line, marked as a draft until the person has reviewed it; with none, why there is none. */
export function ReplyDraft(props: { line: Line }) {
  const { t } = useWords();
  const draft = props.line.reply;
  return (
    <div className="reply-draft" data-reply-draft={(props.line.actions ?? [])[0]}>
      {draft ? (
        <>
          <span className="hint">{t(props.line.reply_reviewed ? "queue.reply.reviewed" : "queue.reply.draft")}</span>
          <p className="reply-text">{draft}</p>
        </>
      ) : (
        <span className="hint">{t("queue.reply.no_draft")}</span>
      )}
    </div>
  );
}

/** A short form for how it was answered, with the cursor in the words; the words are optional. */
function AnsweredForm(props: { onSave: (note: string) => void; onCancel: () => void }) {
  const { t } = useWords();
  const id = useId();
  const [note, setNote] = useState("");
  return (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        props.onSave(note.trim());
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
    >
      <label className="hint" htmlFor={id}>
        {t("queue.reply.answered_label")}
      </label>
      <input id={id} type="text" autoFocus value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onCancel}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary">
          {t("queue.reply.answered_go")}
        </button>
      </div>
    </form>
  );
}

/** The person's own reply, starting from the draft, with the cursor in it. */
function EditForm(props: { value: string; onSave: (text: string) => void; onCancel: () => void }) {
  const { t } = useWords();
  const id = useId();
  const [text, setText] = useState(props.value);
  return (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) props.onSave(text.trim());
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
    >
      <label className="hint" htmlFor={id}>
        {t("queue.reply.edit_label")}
      </label>
      <textarea id={id} rows={5} autoFocus value={text} onChange={(e) => setText(e.target.value)} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onCancel}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!text.trim()}>
          {t("queue.reply.edit_save")}
        </button>
      </div>
    </form>
  );
}
