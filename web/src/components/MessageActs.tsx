// What the person can do about a saved message from outside the app (design 6.12): reply, reply to everyone, forward, archive,
// move to a folder, label, mark as read. Each one drafts an act and opens it in Waiting to go out, where the person says yes
// to exactly what it will do; nothing is sent or changed here. The account the message came in on carries it when acting is
// on for that account; otherwise Copy does, and the draft says why. A form asks only for what the act needs (the words of a
// reply, who a forward goes to, the folder, the label), with the cursor in its first field.
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useDraftAct, useActOptions } from "../lib/acts";
import { useWords } from "../lib/wording";
import { PersonPicker } from "./PersonPicker";
import type { MenuAction } from "./RowMenu";

type Asking = "reply" | "reply_all" | "forward" | "move" | "label";

/** The subject with the prefix a reply or forward carries, once: "Re: Proofs" stays "Re: Proofs". */
export function withPrefix(prefix: string, subject: string): string {
  const bare = prefix.trim().toLowerCase();
  return subject.trim().toLowerCase().startsWith(bare) ? subject.trim() : `${prefix}${subject.trim()}`;
}

export interface MessageActs {
  /** What the message's account does about it; none until it is known, or when the record isn't a saved message. */
  options: S["ActOptionsView"] | null;
  /** Whether the account carries the act after the person's yes, so the primary is "Send reply" rather than Copy. */
  canAct: boolean;
  /** Reply with these words at once: the drafted reply of a reply owed. */
  replyNow: (text: string) => Promise<unknown>;
  /** Open the form for one of the acts that asks something first. */
  ask: (what: Asking) => void;
  /** The acts the message's account does besides the primary one, as menu entries, each drafting or opening its form. */
  menu: (leave?: Asking[]) => MenuAction[];
  /** The form a choice opened, shown beside the message. */
  form: ReactNode;
}

/** The acts on one saved message, or on the message a reply owed answers (give the action's id as `record`). `subject` is the
 * message's own, for the subject of a reply. `enabled` false asks the server nothing. */
export function useMessageActs(record: string | null, subject: string, enabled = true): MessageActs {
  const { t } = useWords();
  const found = useActOptions(record, enabled);
  const draft = useDraftAct();
  const [asking, setAsking] = useState<Asking | null>(null);
  const options = found.data?.kind === "message" ? found.data : null;
  const message = options?.record ?? null;
  const offers = (what: string) => (options?.actions ?? []).includes(what);

  const reply = (action: "reply" | "reply_all" | "forward", text: string, to?: string) =>
    draft({
      kind: "message",
      action,
      in_reply_to: message,
      recipients: to ? [{ person: to, kind: "email", role: "to", called_out: false, from_text: false }] : [],
      parts: { subject: withPrefix(t(action === "forward" ? "acts.forward.prefix" : "acts.reply.prefix"), subject), body: text },
    });
  const change = (action: "archive" | "mark_read" | "move" | "label", more: Partial<S["ActDraftIn"]> = {}) =>
    draft({ kind: "mailbox", action, about: message ? [message] : [], ...more });

  const entries: Record<string, MenuAction> = {
    reply: { id: "reply", label: t("acts.reply"), run: () => setAsking("reply") },
    reply_all: { id: "reply-all", label: t("acts.reply_all"), run: () => setAsking("reply_all") },
    forward: { id: "forward", label: t("acts.forward"), run: () => setAsking("forward") },
    archive: { id: "archive", label: t("acts.archive"), run: () => void change("archive") },
    move: { id: "move", label: t("acts.move"), run: () => setAsking("move") },
    label: { id: "label", label: t("acts.label"), run: () => setAsking("label") },
    mark_read: { id: "mark-read", label: t("acts.mark_read"), run: () => void change("mark_read") },
  };

  const close = () => setAsking(null);
  const done = (made: unknown) => {
    if (made) close();
  };
  let form: ReactNode = null;
  if (options && asking === "reply") form = <TextForm label={t("acts.reply.label")} go={t("acts.reply.go")} onCancel={close} onSubmit={async (text) => done(await reply("reply", text))} />;
  if (options && asking === "reply_all") form = <TextForm label={t("acts.reply.label")} go={t("acts.reply.go")} onCancel={close} onSubmit={async (text) => done(await reply("reply_all", text))} />;
  if (options && asking === "forward") form = <ForwardForm onCancel={close} onSubmit={async (text, to) => done(await reply("forward", text, to))} />;
  if (options && asking === "move") form = <MoveForm source={options.folder_source ?? null} onCancel={close} onSubmit={async (folder) => done(await change("move", { folder }))} />;
  if (options && asking === "label") form = <LabelForm onCancel={close} onSubmit={async (label) => done(await change("label", { label }))} />;

  return {
    options,
    canAct: !!options?.can_act,
    replyNow: (text) => reply("reply", text),
    ask: setAsking,
    menu: (leave = []) =>
      (["reply", "reply_all", "forward", "archive", "move", "label", "mark_read"] as const)
        .filter((a) => offers(a) && !leave.includes(a as Asking))
        .map((a) => entries[a]),
    form,
  };
}

/** Words typed for a reply, with the cursor in them; the act is drafted on submit. */
function TextForm(props: { label: string; go: string; onCancel: () => void; onSubmit: (text: string) => Promise<void> }) {
  const { t } = useWords();
  const id = useId();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="answer-form"
      data-act-form="reply"
      onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim() || busy) return;
        setBusy(true);
        void props.onSubmit(text.trim()).finally(() => setBusy(false));
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
    >
      <label className="hint" htmlFor={id}>
        {props.label}
      </label>
      <textarea id={id} rows={5} autoFocus value={text} onChange={(e) => setText(e.target.value)} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onCancel}>
          {t("acts.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!text.trim() || busy}>
          {props.go}
        </button>
      </div>
    </form>
  );
}

/** Who a forward goes to (a person on file with an email address, from a list) and the person's own note. */
function ForwardForm(props: { onCancel: () => void; onSubmit: (text: string, to: string) => Promise<void> }) {
  const { t } = useWords();
  const id = useId();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [to, setTo] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const reachable = (people.data ?? []).filter((p) => !p.is_pm && (p.how_to_reach?.email ?? "").trim() !== "");
  return (
    <form
      className="answer-form"
      data-act-form="forward"
      onSubmit={(e) => {
        e.preventDefault();
        if (!to || !text.trim() || busy) return;
        setBusy(true);
        void props.onSubmit(text.trim(), to).finally(() => setBusy(false));
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
    >
      <PersonPicker label={t("acts.forward.to")} value={to} onChange={setTo} suggested={[]} people={reachable} noAdd autoFocus />
      <label className="hint" htmlFor={id}>
        {t("acts.forward.label")}
      </label>
      <textarea id={id} rows={4} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onCancel}>
          {t("acts.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!to || !text.trim() || busy}>
          {t("acts.forward.go")}
        </button>
      </div>
    </form>
  );
}

/** The folder to move to, from the mailbox's own folders. */
function MoveForm(props: { source: string | null; onCancel: () => void; onSubmit: (folder: string) => Promise<void> }) {
  const { t } = useWords();
  const id = useId();
  const folders = useQuery({
    queryKey: ["watch-folders", props.source],
    queryFn: () => api.watchFolders(props.source ?? ""),
    enabled: !!props.source,
    retry: false,
    staleTime: 300_000,
  });
  const [folder, setFolder] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="answer-form"
      data-act-form="move"
      onSubmit={(e) => {
        e.preventDefault();
        if (!folder || busy) return;
        setBusy(true);
        void props.onSubmit(folder).finally(() => setBusy(false));
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
    >
      <label className="hint" htmlFor={id}>
        {t("acts.move.label")}
      </label>
      <select id={id} autoFocus value={folder} onChange={(e) => setFolder(e.target.value)}>
        <option value="">{t("acts.move.choose")}</option>
        {(folders.data?.folders ?? []).map((f) => (
          <option key={f} value={f}>
            {f}
          </option>
        ))}
      </select>
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onCancel}>
          {t("acts.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!folder || busy}>
          {t("acts.move.go")}
        </button>
      </div>
    </form>
  );
}

/** The label to put on the messages: a few words typed, since a mailbox has no list of its labels to pick from. */
function LabelForm(props: { onCancel: () => void; onSubmit: (label: string) => Promise<void> }) {
  const { t } = useWords();
  const id = useId();
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="answer-form"
      data-act-form="label"
      onSubmit={(e) => {
        e.preventDefault();
        if (!label.trim() || busy) return;
        setBusy(true);
        void props.onSubmit(label.trim()).finally(() => setBusy(false));
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
    >
      <label className="hint" htmlFor={id}>
        {t("acts.label.label")}
      </label>
      <input id={id} type="text" autoFocus autoComplete="off" value={label} onChange={(e) => setLabel(e.target.value)} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onCancel}>
          {t("acts.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!label.trim() || busy}>
          {t("acts.label.go")}
        </button>
      </div>
    </form>
  );
}
