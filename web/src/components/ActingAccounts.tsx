// Letting the assistant act (design 6.12, 7.9): one switch for each account, "Let {assistant} act after your yes", off until the
// person turns it on. On a signed-in account it starts that account's own sign-in with the wider access, so the person sees the
// service's page; on a plain mailbox it just saves. Turning it off saves at once, with Undo. What isn't switched on still gets
// drafts, which the person carries out with Copy. Only the person's own click changes it; nothing the assistant reads proposes it.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { problemText } from "../lib/problem";
import { rememberReturn } from "../lib/sign-in-return";
import { rememberFingerprint, useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { Skeleton } from "../ui/Skeleton";

const KEY = "watch.acting";
type Account = S["ActAccountView"];

const sameAccount = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

export function ActingAccounts() {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const base = useId();
  const accounts = useQuery({ queryKey: ["act-accounts"], queryFn: api.actAccounts });
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState("");

  const change = async (account: Account, on: boolean) => {
    setBusy(account.id);
    setProblem("");
    try {
      // What the setting holds now, not what the list shows: an account signed out since is still named in it.
      const settings = await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 });
      const held = settings.items.find((i) => i.key === KEY)?.value;
      const current = Array.isArray(held) ? held.map(String) : [];
      const next = on ? [...current.filter((x) => !sameAccount(x, account.id)), account.id] : current.filter((x) => !sameAccount(x, account.id));
      // A signed-in account asks the service for the wider access first, so a refusal leaves nothing changed.
      const started = on && account.sign_in ? await api.startSignIn(account.sign_in, true) : null;
      const saved = await api.saveSettings({ changes: { [KEY]: next }, reset: [], fingerprint: settings.fingerprint ?? (await fingerprint()) });
      if (started) {
        rememberFingerprint(client, saved.fingerprint);
        rememberReturn();
        // The service's own page replaces this one; coming back opens Settings again.
        window.location.assign(started.url);
        return;
      }
      await afterSave(saved, { message: t(on ? "acting.on_toast" : "acting.off_toast", { account: account.label }) });
      await client.invalidateQueries({ queryKey: ["act-accounts"] });
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section aria-labelledby={`${base}-title`} data-acting-accounts="">
      <h3 id={`${base}-title`}>{t("acting.heading")}</h3>
      <p className="hint">{t("acting.intro")}</p>
      {accounts.isPending ? (
        <Skeleton />
      ) : accounts.isError ? (
        <p className="problem-note">{t("acting.load_failed")}</p>
      ) : (accounts.data?.accounts ?? []).length === 0 ? (
        <p className="hint">{t("acting.none")}</p>
      ) : (
        <ul className="plain-list" aria-label={t("acting.list")}>
          {(accounts.data?.accounts ?? []).map((a) => {
            const id = `${base}-${a.id}`.replace(/[^A-Za-z0-9_-]/g, "-");
            return (
              <li key={a.id} className="row pair" data-account={a.id}>
                <span className="text">
                  <strong id={`${id}-name`}>{a.label}</strong>
                  {!a.can_act && <span className="sub">{t("acting.cant", { label: a.label })}</span>}
                  {a.can_act && !a.acting && a.sign_in && <span className="sub">{t("acting.on_hint")}</span>}
                </span>
                <label className="check-line" htmlFor={id}>
                  <input
                    id={id}
                    type="checkbox"
                    checked={a.acting}
                    disabled={busy !== null || (!a.can_act && !a.acting)}
                    aria-describedby={`${id}-name`}
                    onChange={(e) => void change(a, e.target.checked)}
                  />
                  <span>{t("acting.switch")}</span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
    </section>
  );
}
