// Mail set aside as not work (design 6.5): the corrections the screens offer, shared by Today's Came in, What changed and
// the Set aside folder. Each acts at once with an undo toast; the toast also offers a sorting rule for the sender or the
// domain, written through the settings save path as the person's own change with a read-back and Undo.
import { useCallback } from "react";
import { api, type S } from "./api";
import { useAct } from "./act";
import { undoBody } from "./settings";
import { useAfterSave, useFreshFingerprint } from "./settings-save";
import { useWords } from "./wording";

export type Section = S["SetAsideIn"]["section"];
type Choice = S["SortingRuleIn"]["choice"];
/** What the screen needs of a message to correct it: its id in the app and its title for the toast. */
export interface MailRef {
  id: string;
  title: string;
}

export function useSetAside() {
  const { t, tn, has } = useWords();
  const act = useAct();
  const afterSave = useAfterSave();
  const fresh = useFreshFingerprint();

  const what = useCallback((section: Section | null) => (section && has(`setaside.what.${section}`) ? t(`setaside.what.${section}`) : t("setaside.what.mixed")), [t, has]);

  /** Always set aside (or keep) mail from a sender or a domain: one saved rule, read back with Undo. */
  const always = useCallback(
    async (choice: Choice, senders: string[], domains: string[], message: string) => {
      const fingerprint = await fresh();
      const saved = await act(() => api.sortingRule({ fingerprint, choice, senders, domains }));
      if (saved) await afterSave(saved, { message });
    },
    [act, afterSave, fresh],
  );

  /** The toast's choices for a sender and a domain: a rule that sets mail aside in `choice`, or keeps it. */
  const offers = useCallback(
    (choice: Choice, who: { address: string; domain: string }, words: string) => {
      const keep = choice === "never";
      const sender = who.address
        ? {
            label: t("setaside.always_sender"),
            run: () => always(choice, [who.address], [], t(keep ? "setaside.rule_keep_sender" : "setaside.rule_sender", { sender: who.address, what: words })),
          }
        : undefined;
      const domain = who.domain
        ? {
            label: t("setaside.always_domain"),
            run: () => always(choice, [], [who.domain], t(keep ? "setaside.rule_keep_domain" : "setaside.rule_domain", { domain: who.domain, what: words })),
          }
        : undefined;
      return { action: sender ?? domain, more: sender && domain ? [domain] : [] };
    },
    [always, t],
  );

  /** "Set aside: personal" or "Set aside: sales" on a message in Came in or What changed. */
  const setAside = useCallback(
    (mail: MailRef, section: Section) =>
      act(
        () => api.setAsideMail(mail.id, section),
        (done) => ({
          message: t("setaside.done", { title: mail.title, what: what(section) }),
          undo: () => api.putBack(done.id, done.version),
          ...offers(section, done, what(section)),
        }),
      ),
    [act, offers, t, what],
  );

  /** "This is work" on a message in the folder: handed in after all. Undo sets it aside again. */
  const isWork = useCallback(
    (mail: MailRef & { version: number }) =>
      act(
        () => api.isWork(mail.id, mail.version),
        (done) => ({
          message: t("setaside.work_done", { title: mail.title }),
          undo: () => api.setAsideMail(done.id, done.section),
          ...offers("never", done, ""),
        }),
      ),
    [act, offers, t],
  );

  /** Confirm: a sorting rule for each sender, and the messages leave the folder to be deleted from the app after the
   * undo time. One save and one Undo for everything confirmed together. */
  const confirm = useCallback(
    (ids: string[]) =>
      act(
        async () => api.confirmSetAside(await fresh(), ids),
        (done) => {
          const words = what(done.section ?? null);
          const message = done.senders.length
            ? done.senders.length === 1
              ? t("setaside.rule_sender", { sender: done.senders[0], what: words })
              : tn("setaside.confirmed_senders", done.senders.length, { what: words })
            : tn("setaside.confirmed_none", done.confirmed);
          const domains = done.domain_offers.map((o) => ({
            label: t("setaside.always_domain_named", { domain: o.domain }),
            run: () => always(o.section, [], [o.domain], t("setaside.rule_domain", { domain: o.domain, what: what(o.section) })),
          }));
          return {
            message,
            undo: async () => {
              await api.unconfirmSetAside(done.ids);
              if (done.saved.changes.length) await api.saveSettings(undoBody(done.saved.changes, await fresh()));
            },
            action: domains[0],
            more: domains.slice(1),
          };
        },
      ),
    [act, always, fresh, t, tn, what],
  );

  return { setAside, isWork, confirm, always };
}
