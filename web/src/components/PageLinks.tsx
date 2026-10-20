// The person's own pages (design 7.9), in Settings → Appearance: a name and a web address each, shown in the header's "Your
// pages" menu. A page is added from a name and an address and removed from its row; both are saved at once with Undo, like
// every other setting. The server checks the list (how many, how long, a web address); this checks the address first so
// the person is told in plain words before anything is sent.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { api, ApiError } from "../lib/api";
import { problemText } from "../lib/problem";
import { knownFingerprint, useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { pageLinks, type PageLink } from "../shell/HeaderLinks";
import { Button } from "../ui/Button";

const WEB = /^https?:\/\/\S+$/i;

export function PageLinks() {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const base = useId();
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [problem, setProblem] = useState("");
  const item = settings.data?.items.find((i) => i.key === "ui.links");
  // Without the setting there is nothing to edit (an older server): the section says nothing.
  if (!item) return null;
  const links = pageLinks(item.value);
  const locked = item.locked || !item.editable;

  const save = async (next: PageLink[], message: string): Promise<boolean> => {
    const fingerprint = knownFingerprint(client, settings.data?.fingerprint);
    if (!fingerprint) return false;
    try {
      const saved = await api.saveSettings({ changes: { "ui.links": next }, reset: [], fingerprint });
      setProblem("");
      await afterSave(saved, { message });
      return true;
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      return false;
    }
  };

  const add = async () => {
    const entry = { name: name.trim(), address: address.trim() };
    if (!entry.name || !entry.address) return;
    if (!WEB.test(entry.address)) {
      setProblem(t("pages.bad_address", { name: entry.name }));
      return;
    }
    if (await save([...links, entry], t("pages.added", { name: entry.name }))) {
      setName("");
      setAddress("");
    }
  };

  return (
    <section className="settings-group" aria-labelledby={`${base}-title`}>
      <h3 id={`${base}-title`}>{t("pages.title")}</h3>
      <p className="hint">{t("pages.intro")}</p>
      {links.length > 0 && (
        <ul className="plain-list" aria-label={t("pages.list")}>
          {links.map((l, i) => (
            <li key={`${i}:${l.address}`} className="row-pair">
              <span className="title">{l.name}</span> <span className="meta">{l.address}</span>
              {!locked && (
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={t("pages.remove_named", { name: l.name })}
                  onClick={() => void save(links.filter((_, k) => k !== i), t("pages.removed", { name: l.name }))}
                >
                  {t("pages.remove")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!locked && (
        <form
          className="answer-form"
          onSubmit={(e) => {
            e.preventDefault();
            void add();
          }}
        >
          <div className="field">
            <label htmlFor={`${base}-name`}>{t("pages.name")}</label>
            <input id={`${base}-name`} type="text" maxLength={40} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor={`${base}-address`}>{t("pages.address")}</label>
            <input id={`${base}-address`} type="url" inputMode="url" value={address} onChange={(e) => setAddress(e.target.value)} aria-describedby={problem ? `${base}-problem` : undefined} />
          </div>
          {problem && (
            <p className="problem-note" id={`${base}-problem`} role="alert">
              {problem}
            </p>
          )}
          <div className="row-end">
            <Button type="submit" variant="primary" disabled={!name.trim() || !address.trim()}>
              {t("pages.add")}
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
