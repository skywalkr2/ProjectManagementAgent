// What waits to go out (design 6.12, 7.4): the outward acts as the screen and Today's lines read them. An act is one thing
// that will leave on the person's behalf (a message, a calendar entry, a file): its exact content, its target, its state.
// The words for them are the sheet's; the person never sees the word "act".
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { ApiError, api, type S } from "./api";
import { useAct } from "./act";
import { copyMessage, type CopyResult } from "./copy";
import { revealOrKeep } from "./reveal";
import { useToasts } from "./toasts";
import { toHash } from "./views";
import { useWords } from "./wording";

export type Act = S["ActView"];
export type ActState = Act["status"];
export type ActRecipient = S["ActRecipientView"];
type T = (key: string, vars?: Record<string, string | number>) => string;

/** The states Waiting to go out lists: what still needs the person or the app before it has gone (design 6.12). */
export const WAITING: readonly ActState[] = ["draft", "approved", "sending", "stale", "failed", "uncertain"];
/** The states a person may take back (the engine's own list: a draft, an approved one, one gone stale or one that failed). */
const TAKE_BACK: readonly ActState[] = ["draft", "approved", "stale", "failed"];
/** The states a yes may be given from. */
const APPROVABLE: readonly ActState[] = ["draft", "stale", "failed"];

export const canTakeBack = (a: Act): boolean => TAKE_BACK.includes(a.status);
export const canApprove = (a: Act): boolean => APPROVABLE.includes(a.status);
/** Whether the person carries this one out themselves: the copy channel, whose send is their own. */
export const isByHand = (a: Act): boolean => a.channel === "copy";

/** Every outward act, newest first; callers pick the states they show. */
export function useActs() {
  return useQuery({ queryKey: ["acts"], queryFn: api.acts, select: (r) => r.acts });
}

/** The acts that wait: draft, approved, sending, stale, failed and uncertain. */
export function useWaitingActs() {
  return useQuery({ queryKey: ["acts"], queryFn: api.acts, select: (r) => r.acts.filter((a) => WAITING.includes(a.status)) });
}

/** The acts that went out, newest first, with those taken back after: what Waiting to go out lists under what waits. */
export function useSentActs() {
  return useQuery({
    queryKey: ["acts"],
    queryFn: api.acts,
    select: (r) => r.acts.filter((a) => a.status === "sent" || a.status === "undone").slice(0, SENT_SHOWN),
  });
}

/** How many of the acts that went out the list shows. */
const SENT_SHOWN = 10;

/** Open an act in Waiting to go out: the list there opens its row, or, from another screen, the screen opens with it. */
export function showInOutgoing(id: string): void {
  if (!revealOrKeep("act", id)) window.location.hash = toHash("work/outgoing");
}

/** What can be done about a saved message, a calendar entry or a reply owed (its action's id): the account it came in on,
 * whether acting is on for it, and what that account does. `enabled` false asks nothing. */
export function useActOptions(record: string | null, enabled = true) {
  return useQuery({
    queryKey: ["act-options", record],
    queryFn: () => api.actOptions(record ?? ""),
    enabled: enabled && !!record,
    staleTime: 30_000,
  });
}

/** The person drafts an act and it opens in Waiting to go out for their yes, with Undo taking the draft back. A refusal says
 * why (the account can't do it, the message has no one to reply to). Returns the act, or nothing when it was refused. */
export function useDraftAct() {
  const { t } = useWords();
  const run = useAct();
  return useCallback(
    async (body: S["ActDraftIn"]): Promise<Act | undefined> => {
      const made = await run(
        () => api.draftAct(body),
        (a) => ({
          key: `act:${a.id}`,
          message: t(a.copied_because ? "acts.drafted_copy" : "acts.drafted", { what: actPhrase(a, t) }),
          undo: () => api.withdrawAct(a.id),
        }),
      );
      if (made) showInOutgoing(made.id);
      return made;
    },
    [run, t],
  );
}

// ---- words -----------------------------------------------------------------------------------------------------------

function list(words: string[]): string {
  return new Intl.ListFormat(undefined, { style: "long", type: "conjunction" }).format(words);
}

/** Who a message goes to, by name (the people it is addressed to, not those copied). */
export function recipientNames(a: Act, t: T): string {
  const to = (a.recipients ?? []).filter((r) => r.role === "to").map((r) => r.name);
  return to.length > 0 ? list(to) : t("queue.title.someone");
}

const vars = (a: Act, t: T) => ({
  names: recipientNames(a, t),
  calendar: a.calendar ?? "",
  folder: a.folder ?? "",
  label: a.label ?? "",
  title: a.title ?? "",
  n: (a.about ?? []).length,
  event: (a.about ?? []).find((x) => x.kind === "event")?.title ?? "",
});

const REPLIES = ["reply", "reply_all", "forward"];
const MAIL_CHANGES = ["archive", "move", "label", "mark_read"];

/** The sheet's key for what this act does: its own words for a reply, a change to the mail or an answer to an invitation, else
 * the kind's. */
function wordsKey(a: Act, family: "title" | "what"): string {
  if (a.kind === "message" && REPLIES.includes(a.action)) return `outgoing.${family}.message.${a.action}`;
  if (a.kind === "mailbox" && MAIL_CHANGES.includes(a.action) && family === "title") {
    return `outgoing.title.mailbox.${a.action}.${(a.about ?? []).length === 1 ? "one" : "other"}`;
  }
  if (a.kind === "calendar" && a.action === "create") return `outgoing.${family}.calendar.create`;
  if (a.kind === "calendar" && a.action === "answer" && a.answer) {
    return family === "title" ? `outgoing.title.calendar.answer.${a.answer}` : "outgoing.what.calendar.answer";
  }
  return `outgoing.${family}.${a.kind}`;
}

/** A line's title: what the act does ("Archive 3 messages", "Answer to <event>: accept", "Message to <person>"). */
export function actTitle(a: Act, t: T): string {
  return t(wordsKey(a, "title"), vars(a, t));
}

/** The act inside a sentence: "the message to" and the recipient. */
export function actPhrase(a: Act, t: T): string {
  return t(wordsKey(a, "what"), vars(a, t));
}

/** One of the saved messages a mailbox act is about, on a line: who sent it, what it says and when. */
export function messageLine(about: S["ActAboutView"], t: T): string {
  const sender = about.sender || t("outgoing.unknown_sender");
  const subject = about.title || t("outgoing.no_subject");
  return about.when ? t("outgoing.message_line.date", { sender, subject, when: about.when }) : t("outgoing.message_line", { sender, subject });
}

/** What about it is different now, in words ("who it goes to and what will be sent"), from what the yes covered. */
export function changedWords(a: Act, t: T): string {
  const known = (a.why ?? []).filter((code) => ["channel", "target", "about", "account", "content", "template"].includes(code));
  return known.length > 0 ? list(known.map((code) => t(`outgoing.changed.${code}`))) : t("outgoing.changed.unknown");
}

/** The name of a part of the content ("Subject", "Message"): the sheet's when it has one, else the part's own name. */
export function partLabel(name: string, t: T, has: (key: string) => boolean): string {
  const key = `outgoing.part.${name}`;
  if (has(key)) return t(key);
  const plain = name.replace(/[-_]+/g, " ").trim();
  return plain.charAt(0).toUpperCase() + plain.slice(1);
}

/** The recipients the person must acknowledge by name before their yes. */
export const calledOut = (a: Act): ActRecipient[] => (a.recipients ?? []).filter((r) => (r.reasons ?? []).length > 0);

/** What Copy puts on the clipboard: every part as written, the parts one after another; an act with no content of its own (a
 * change to the mail, an answer) is carried by what it does and what it is about. */
export function copyText(a: Act, t: T): string {
  const parts = Object.values(a.parts);
  if (parts.some((p) => p.trim())) return parts.join("\n\n");
  const lines = [actTitle(a, t), ...(a.about ?? []).filter((x) => x.kind === "message").map((x) => messageLine(x, t))];
  if (a.proposed_start && a.proposed_end) lines.push(t("outgoing.proposed_line", { start: a.proposed_start, end: a.proposed_end }));
  return lines.join("\n");
}

/** The act's first part that reads as a subject, for a line's second row. */
export const subjectOf = (a: Act): string => a.parts.subject ?? a.parts.title ?? "";

// ---- Today's lines ---------------------------------------------------------------------------------------------------

export type ActLineGroup = "decide" | "risk";
export interface ActLine {
  act: Act;
  group: ActLineGroup;
}

/** One Today line for each act that failed, can't be told apart from sent, or went stale. Failed and unsure ones are at risk;
 * a stale one is a decision (look again, then say yes). */
export function useActToday() {
  const acts = useActs();
  const lines: ActLine[] = (acts.data ?? []).flatMap((act): ActLine[] =>
    act.status === "failed" || act.status === "uncertain" ? [{ act, group: "risk" }] : act.status === "stale" ? [{ act, group: "decide" }] : [],
  );
  return { count: lines.length, lines, in: (group: ActLineGroup) => lines.filter((l) => l.group === group) };
}

// ---- the person's choices --------------------------------------------------------------------------------------------

/** What each choice does, with its toast: say yes and send, copy, mark sent, answer for one the app can't confirm, take back.
 * Each is the person's own click on that act; the server checks what the screen showed against what is there now. */
export function useOutgoing() {
  const { t } = useWords();
  const run = useAct();
  const { push } = useToasts();
  const client = useQueryClient();

  const said = useCallback(
    (a: Act, r: S["ActResultView"]): string => {
      const what = actPhrase(a, t);
      switch (r.status) {
        case "sent":
          return t("outgoing.toast.sent", { what });
        case "failed":
          return t("outgoing.toast.failed", { reason: r.reason ?? t("outgoing.toast.no_reason") });
        case "stale":
          return t("outgoing.toast.stale", { what });
        case "sending":
          return t("outgoing.toast.sending", { what });
        case "uncertain":
          return t("outgoing.toast.uncertain", { what });
        default:
          return t("outgoing.toast.approved", { what });
      }
    },
    [t],
  );

  /** Take back a sent act where its channel can: the toast says it is done, or why it is not. */
  const takeBack = useCallback(
    async (a: Act) => {
      const what = actPhrase(a, t);
      try {
        const r = await api.takeBackAct(a.id);
        push({ message: r.status === "undone" ? t("outgoing.take_back.done", { what }) : t("outgoing.take_back.failed", { reason: r.reason ?? t("outgoing.toast.no_reason") }) });
      } catch (err) {
        push({ message: t("outgoing.take_back.failed", { reason: err instanceof ApiError && err.detail ? err.detail : t("outgoing.toast.no_reason") }) });
      }
      await client.invalidateQueries();
    },
    [t, push, client],
  );

  /** Approve and send: the yes on the fingerprint the screen showed with the recipients acknowledged, then the send. An act
   * that already has the yes is only sent. A send that went out and can be taken back says so, with Undo in its toast. */
  const send = useCallback(
    (a: Act, acknowledged: string[]) =>
      run(
        async () => {
          const body = { fingerprint: a.fingerprint, acknowledged };
          if (a.status !== "approved") await api.approveAct(a.id, body);
          const result = await api.sendAct(a.id, body);
          const fresh = result.status === "sent" ? await api.readAct(a.id).catch(() => null) : null;
          return { result, undoable: !!fresh?.undoable };
        },
        ({ result, undoable }) => ({ key: `act:${a.id}`, message: said(a, result), undo: undoable ? () => takeBack(a) : undefined }),
      ),
    [run, said, takeBack],
  );

  /** Copy: the yes (when not given yet), then the exact content on the clipboard, for an act the person sends themselves. */
  const copy = useCallback(
    async (a: Act, acknowledged: string[]): Promise<CopyResult | undefined> => {
      const approved = await run(async () => {
        if (a.status !== "approved") await api.approveAct(a.id, { fingerprint: a.fingerprint, acknowledged });
        return true;
      });
      if (!approved) return undefined;
      const result = await copyMessage(copyText(a, t));
      push({ message: t(result === "blocked" ? "outgoing.toast.copy_blocked" : "outgoing.toast.copied") });
      return result;
    },
    [run, push, t],
  );

  /** "It was sent" (and Mark sent for one the person carried out): Undo takes it back. */
  const markSent = useCallback(
    (a: Act) =>
      run(
        () => api.settleAct(a.id, "sent"),
        (r) => {
          const cs = r.changeset;
          return { message: t("outgoing.toast.marked_sent", { what: actPhrase(a, t) }), undo: cs ? () => api.undo(cs) : undefined };
        },
      ),
    [run, t],
  );

  /** "Send it again": approves it again as it is and sends it; what changed since makes it stale instead. */
  const sendAgain = useCallback(
    (a: Act) =>
      run(
        () => api.settleAct(a.id, "again"),
        (r) => ({ message: said(a, r) }),
      ),
    [run, said],
  );

  /** Take it back: it will not go, and Undo brings it back as it was. */
  const withdraw = useCallback(
    (a: Act) =>
      run(
        () => api.withdrawAct(a.id),
        (r) => {
          const cs = r.changeset;
          return { message: t("outgoing.toast.withdrawn", { what: actPhrase(a, t) }), undo: cs ? () => api.undo(cs) : undefined };
        },
      ),
    [run, t],
  );

  return { send, copy, markSent, sendAgain, withdraw, takeBack };
}
