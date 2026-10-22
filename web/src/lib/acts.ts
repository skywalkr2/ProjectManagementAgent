// What waits to go out (design 6.12, 7.4): the outward acts as the screen and Today's lines read them. An act is one thing
// that will leave on the person's behalf (a message, a calendar entry, a file): its exact content, its target, its state.
// The words for them are the sheet's; the person never sees the word "act".
import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, type S } from "./api";
import { useAct } from "./act";
import { copyMessage, type CopyResult } from "./copy";
import { useToasts } from "./toasts";
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

// ---- words -----------------------------------------------------------------------------------------------------------

function list(words: string[]): string {
  return new Intl.ListFormat(undefined, { style: "long", type: "conjunction" }).format(words);
}

/** Who a message goes to, by name (the people it is addressed to, not those copied). */
export function recipientNames(a: Act, t: T): string {
  const to = (a.recipients ?? []).filter((r) => r.role === "to").map((r) => r.name);
  return to.length > 0 ? list(to) : t("queue.title.someone");
}

const vars = (a: Act, t: T) => ({ names: recipientNames(a, t), calendar: a.calendar ?? "", folder: a.folder ?? "" });

/** A line's title: "Message to" and the recipient. */
export function actTitle(a: Act, t: T): string {
  return t(`outgoing.title.${a.kind}`, vars(a, t));
}

/** The act inside a sentence: "the message to" and the recipient. */
export function actPhrase(a: Act, t: T): string {
  return t(`outgoing.what.${a.kind}`, vars(a, t));
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

/** What Copy puts on the clipboard: every part as written, the parts one after another. */
export function copyText(a: Act): string {
  return Object.values(a.parts).join("\n\n");
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

  /** Approve and send: the yes on the fingerprint the screen showed with the recipients acknowledged, then the send. An act
   * that already has the yes is only sent. */
  const send = useCallback(
    (a: Act, acknowledged: string[]) =>
      run(
        async () => {
          const body = { fingerprint: a.fingerprint, acknowledged };
          if (a.status !== "approved") await api.approveAct(a.id, body);
          return api.sendAct(a.id, body);
        },
        (r) => ({ message: said(a, r) }),
      ),
    [run, said],
  );

  /** Copy: the yes (when not given yet), then the exact content on the clipboard, for an act the person sends themselves. */
  const copy = useCallback(
    async (a: Act, acknowledged: string[]): Promise<CopyResult | undefined> => {
      const approved = await run(async () => {
        if (a.status !== "approved") await api.approveAct(a.id, { fingerprint: a.fingerprint, acknowledged });
        return true;
      });
      if (!approved) return undefined;
      const result = await copyMessage(copyText(a));
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

  return { send, copy, markSent, sendAgain, withdraw };
}
