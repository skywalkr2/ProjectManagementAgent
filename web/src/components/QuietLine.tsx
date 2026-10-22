// What the person can do about a line for a promise that has gone quiet (design 6.32, 7.7): send a follow-up to whoever owes
// it, which drafts the message as an act that opens in Waiting to go out for the person's yes, or snooze the line to a day
// from a list, with Undo. Nothing is sent from here.
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { useDraftAct, useSendOptions } from "../lib/acts";
import { day } from "../lib/dates";
import { useWords } from "../lib/wording";
import type { MenuGroup } from "../ui/MenuButton";
import type { QueueLine } from "../lib/today";
import type { MenuAction } from "./RowMenu";

export interface QuietChoices {
  menu: MenuAction[];
  groups: MenuGroup[];
}

/** The menu of a quiet-promise line; empty for any other line. */
export function useQuietChoices(line: QueueLine): QuietChoices {
  const { t, tn } = useWords();
  const act = useAct();
  const draft = useDraftAct();
  const quiet = line.kind === "quiet_promise";
  const action = (line.actions ?? [])[0] ?? "";
  // A follow-up is for a promise someone owes the person; one the person made has none.
  const owed = quiet && line.state === "from";
  const sending = useSendOptions(owed).data;
  if (!quiet) return { menu: [], groups: [] };

  const followUp = async () => {
    const written = await api.quietFollowUp(action).catch(() => null);
    if (!written) return;
    await draft({
      kind: "message",
      action: "send",
      account: sending?.can_act ? (sending.account ?? undefined) : undefined,
      recipients: [{ person: written.person, kind: "email", role: "to", called_out: false, from_text: false }],
      parts: written.parts,
    });
  };
  const snooze = (until: string) =>
    void act(
      () => api.snoozeQuietPromise(action, until),
      (done) => ({ message: t("queue.quiet.snoozed", { date: day(until) }), undo: () => api.undoNotNowSuggestion(done.signal) }),
    );
  return {
    menu: owed ? [{ id: "follow-up", label: t("queue.quiet.follow_up"), run: () => void followUp() }] : [],
    groups: [
      {
        id: "snooze",
        title: t("queue.quiet.snooze"),
        entries: (line.snooze_days ?? []).map((choice) => ({
          id: `snooze-${choice.days}`,
          label: tn("queue.quiet.snooze_days", choice.days, { date: day(choice.on) }),
          run: () => snooze(choice.on),
        })),
      },
    ],
  };
}
