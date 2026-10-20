// Add-ons: where packs are found and what the ones already here do. Available lists packs the configured catalogs
// offer, each with what it does, what it adds, reaches and keeps, what its AI work would cost on the person's own
// accounts, and how to get it; Installed lists the packs this copy of the app has. Everything a catalog says is shown
// as text, and the only address that can be opened is a pack's own page, with its real domain beside it. A listed pack
// with a release the app can install has an Install button; one the app installed can be removed once it is off. Both
// need a restart before the app uses the change, and neither turns anything on.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Heading, Tab, TabList, TabPanel, Tabs } from "react-aria-components";
import { api, ApiError, type S } from "../lib/api";

import { copyPlain } from "../lib/copy";
import { whenText as when } from "../lib/dates";
import { useSmallMoney, useTotal } from "../lib/money";
import {
  SAFE_ID,
  addsLines,
  costText,
  keepsText,
  priceText,
  reachesLines,
  updateOffered,
  waitsForRestart,
  type Summary,
} from "../lib/packs";
import { problemText } from "../lib/problem";
import { useRestart } from "../lib/restart";
import { asReference } from "../lib/secret-ref";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { ModalPanel, restoreFocus } from "./ModalPanel";
import { domainOf } from "./SafeText";
import { SecretField } from "./SecretField";
import { AddonSecrets } from "./KeptSecrets";
import { RowMenu, type MenuAction } from "./RowMenu";
import { Skeleton } from "../ui/Skeleton";

type Pack = S["PackView"];
type Feed = S["PackFeedView"];
type Installed = S["InstalledPackView"];

export function Addons(props: { onBack: () => void }) {
  const { t } = useWords();
  const packs = useQuery({ queryKey: ["packs"], queryFn: api.packs });
  const [tab, setTab] = useState("available");
  return (
    <section className="panel-section" aria-labelledby="addons-title">
      <div className="heading">
        <h1 id="addons-title">{t("addons.title")}</h1>
        <button type="button" className="btn" onClick={props.onBack}>
          {t("addons.back")}
        </button>
      </div>
      <p className="hint">{t("addons.intro")}</p>
      <Tabs selectedKey={tab} onSelectionChange={(key) => setTab(String(key))} className="addon-tabs">
        <TabList aria-label={t("addons.tabs")} className="tablist">
          <Tab id="available" className="tab">
            {t("addons.tab.available")}
          </Tab>
          <Tab id="installed" className="tab">
            {t("addons.tab.installed")}
          </Tab>
        </TabList>
        <TabPanel id="available" className="tab-panel">
          <Loaded query={packs}>{(view) => <Available view={view} />}</Loaded>
        </TabPanel>
        <TabPanel id="installed" className="tab-panel">
          <Loaded query={packs}>{(view) => <InstalledList items={view.installed} />}</Loaded>
        </TabPanel>
      </Tabs>
    </section>
  );
}

/** Turning an add-on on or off: acts at once and reads back with Undo, then the restart question if one is needed (never a
 * restart by itself). A refusal is kept for the row to show in the server's own words. */
function useSwitch(name: string, label: string) {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const run = async (on: boolean) => {
    setBusy(true);
    setProblem("");
    try {
      // The settings as they are now, so a change made meanwhile is noticed rather than overwritten.
      const current = await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 });
      const saved = await (on ? api.packOn : api.packOff)(name, current.fingerprint);
      await afterSave(saved, { message: t(on ? "addons.switched_on" : "addons.switched_off", { name: label }) });
      // The list reads which add-ons are on from the saved settings: read it again so the row says what was just saved.
      await client.refetchQueries({ queryKey: ["packs"] });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };
  return { busy, problem, run };
}

/** Installing, updating or removing an add-on from the screen: acts at once, then the row says a restart is needed until
 * the app has restarted. A refusal is kept for the row to show in the server's own words; `note` is what the row says
 * after a success. */
function usePackChange(packId: string, name: string, focusRow: () => void) {
  const { t } = useWords();
  const client = useQueryClient();
  const [busy, setBusy] = useState<"install" | "remove" | null>(null);
  const [problem, setProblem] = useState("");
  // The refusal says a read token for the release's host would fix it: the row asks for one in place.
  const [needsToken, setNeedsToken] = useState(false);
  const [tokenSaved, setTokenSaved] = useState(false);
  const restarts = useRestart().restarts;
  // What was done, and how many restarts had happened by then: once another has, the restart it asked for is over.
  const [last, setLast] = useState<{ what: "installed" | "removed"; at: number } | null>(null);
  const done = last && last.at === restarts ? last.what : null;
  useEffect(() => {
    if (last && last.at !== restarts) {
      setLast(null);
      void client.invalidateQueries({ queryKey: ["packs"] });
      void client.invalidateQueries({ queryKey: ["status"] });
    }
  }, [last, restarts, client]);
  const run = async (what: "install" | "remove") => {
    setBusy(what);
    setProblem("");
    setNeedsToken(false);
    setTokenSaved(false);
    try {
      await (what === "install" ? api.installPack : api.removePack)(packId);
      setLast({ what: what === "install" ? "installed" : "removed", at: restarts });
      await Promise.all([
        client.invalidateQueries({ queryKey: ["packs"] }),
        client.invalidateQueries({ queryKey: ["status"] }),
      ]);
      focusRow();
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      setNeedsToken(err instanceof ApiError && err.needs === "read-token");
    } finally {
      setBusy(null);
    }
  };
  return {
    busy,
    problem,
    needsToken,
    tokenSaved,
    /** The token is kept: the refusal is over, and Install can be pressed again. */
    gotToken: () => {
      setNeedsToken(false);
      setProblem("");
      setTokenSaved(true);
    },
    note: done ? t(done === "installed" ? "addons.installed_note" : "addons.removed_note", { name }) : "",
    installed: done === "installed",
    install: () => run("install"),
    remove: () => run("remove"),
  };
}

/** What a row says once an install or removal needs the restart, with the same Restart now the other rows have. */
function RestartLine(props: { text: string }) {
  return (
    <p className="sub pack-restart" role="status">
      {props.text}
      <RestartNowButton />
    </p>
  );
}

/** The row's own Restart now, offered whenever the app can restart itself. Asking is the person's choice: nothing
 * restarts until it is pressed. */
function RestartNowButton() {
  const { t } = useWords();
  const restart = useRestart();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  if (!status.data?.can_restart) return null;
  return (
    <>
      {" "}
      <button type="button" className="btn quiet small" disabled={restart.busy || restart.waiting} onClick={() => void restart.now()}>
        {t("restart.now")}
      </button>
    </>
  );
}

/** The row's one primary action for an installed add-on: Turn on when it is off, Turn off when it is on. */
function SwitchButton(props: { on: boolean; label: string; busy: boolean; id?: string; onRun: () => void }) {
  const { t } = useWords();
  return (
    <button
      type="button"
      id={props.id}
      className="btn primary"
      data-key="primary"
      disabled={props.busy}
      aria-label={t(props.on ? "addons.switch_off_named" : "addons.switch_on_named", { name: props.label })}
      onClick={props.onRun}
    >
      {t(props.on ? "addons.switch_off" : "addons.switch_on")}
    </button>
  );
}

function Loaded(props: {
  query: { isPending: boolean; isError: boolean; data?: S["PacksView"]; refetch: () => unknown };
  children: (view: S["PacksView"]) => ReactNode;
}) {
  const { t } = useWords();
  const { query } = props;
  if (query.isPending) return <Skeleton />;
  if (query.isError || !query.data) {
    return (
      <p className="empty">
        {t("addons.load_failed")}{" "}
        <button type="button" className="btn" onClick={() => void query.refetch()}>
          {t("action.try_again")}
        </button>
      </p>
    );
  }
  return <>{props.children(query.data)}</>;
}

function Available(props: { view: S["PacksView"] }) {
  const { t } = useWords();
  const { view } = props;
  const [getting, setGetting] = useState<number | null>(null);
  const empty = !view.enabled
    ? t("addons.off")
    : view.feeds.length === 0
      ? t("addons.no_catalog")
      : view.available.length === 0
        ? // A catalog that couldn't be read is not an empty one: say so, and the reason is listed below.
          view.feeds.every((feed) => feed.error)
          ? t("addons.no_packs_failed")
          : t("addons.no_packs")
        : null;
  return (
    <div className="addons-body">
      {empty ? (
        <p className="empty">{empty}</p>
      ) : (
        <ul className="queue">
          {view.available.map((pack, i) => (
            <PackRow
              key={`${pack.id}-${i}`}
              pack={pack}
              index={i}
              restartNeeded={restartNeeded(pack, view.installed)}
              onGet={() => setGetting(i)}
            />
          ))}
        </ul>
      )}
      {view.enabled && view.feeds.length === 0 && <AddCatalog first />}
      {view.enabled && view.feeds.length > 0 && <Catalog feeds={view.feeds} />}
      {getting !== null && view.available[getting] && (
        <GetIt
          pack={view.available[getting]}
          onClose={() => {
            const index = getting;
            setGetting(null);
            restoreFocus(() => document.getElementById(`pack-get-${index}`) ?? document.getElementById(`pack-row-${index}`));
          }}
        />
      )}
    </div>
  );
}

/** What a pack adds, reaches and keeps, as three short labelled lists. Used by both tabs. */
function WhatLines(props: { what: Summary; base: string }) {
  const { t, tn } = useWords();
  const adds = addsLines(props.what.adds, t, tn);
  const reaches = reachesLines(props.what.reaches, t);
  const part = (key: string, label: string, body: ReactNode) => (
    <div className="pack-part">
      <p className="what" id={`${props.base}-${key}`}>
        {label}
      </p>
      {body}
    </div>
  );
  const list = (key: string, items: string[]) => (
    <ul className="plain-list" aria-labelledby={`${props.base}-${key}`}>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
  return (
    <div className="pack-what">
      {part("adds", t("addons.adds"), list("adds", adds.length ? adds : [t("addons.adds.nothing")]))}
      {part("reaches", t("addons.reaches"), list("reaches", reaches))}
      {part("keeps", t("addons.keeps"), <p>{keepsText(props.what.keeps, t)}</p>)}
    </div>
  );
}

function PackRow(props: { pack: Pack; index: number; restartNeeded: boolean; onGet: () => void }) {
  const { t } = useWords();
  const total = useTotal();
  const small = useSmallMoney();
  const { pack, index } = props;
  const base = `pack-${index}`;
  const installed = pack.installed_version != null;
  const update = updateOffered(pack);
  const amount = (value: number, currency: string) =>
    !currency || currency.toUpperCase() === "USD" ? total(value) : t("money.other", { amount: value.toFixed(2), currency });
  const compat = pack.compatible === true ? t("addons.compatible.yes") : pack.compatible === false ? t("addons.compatible.no") : "";
  const facts = [
    t(pack.maintainers ? "addons.by_maintainers" : "addons.third_party"),
    pack.publisher,
    pack.updated ? t("addons.updated", { updated: pack.updated }) : "",
    compat,
  ].filter(Boolean);
  const safeHomepage = pack.homepage && pack.homepage_domain && domainOf(pack.homepage) ? pack.homepage : null;
  const size = (n: number) => n.toLocaleString();
  const power = useSwitch(pack.id, pack.name);
  const change = usePackChange(pack.id, pack.name, () =>
    restoreFocus(() => document.getElementById(`pack-row-${index}`)),
  );
  const problem = change.problem || power.problem;

  const actions: MenuAction[] = [];
  if (installed && update && pack.installable) {
    actions.push({ id: "update", label: t("addons.update_now"), run: () => void change.install() });
  } else if (installed && update) {
    actions.push({ id: "update", label: t("addons.get_update"), run: props.onGet });
  }
  if (installed && !pack.enabled && pack.removable) {
    actions.push({ id: "remove", label: t("addons.remove"), run: () => void change.remove() });
  }
  if (safeHomepage) {
    actions.push({
      id: "homepage",
      label: t("addons.homepage_named", { domain: pack.homepage_domain ?? "" }),
      href: safeHomepage,
    });
  }
  return (
    <li className="line" id={`pack-row-${index}`} data-row tabIndex={-1} aria-labelledby={`${base}-name`}>
      <div className="row pair">
        <div className="text pack">
          <strong id={`${base}-name`}>{pack.name}</strong>
          <span className="sub">{facts.join(" · ")}</span>
          <span className="sub pack-price">{priceText(pack.price, amount, t)}</span>
          {pack.summary && <p className="pack-summary">{pack.summary}</p>}
          <WhatLines what={pack.what} base={base} />
          {pack.costs.length > 0 && (
            <div className="pack-part">
              <p className="what" id={`${base}-costs`}>
                {t("addons.costs")}
              </p>
              <ul className="plain-list" aria-labelledby={`${base}-costs`}>
                {pack.costs.map((cost, i) => (
                  <li key={`${cost.label}-${i}`}>{costText(cost, t, small, size)}</li>
                ))}
              </ul>
              <p className="hint">{t("addons.costs_hint")}</p>
            </div>
          )}
          {installed && (
            <p className="sub" id={`${base}-state`}>
              {t(props.restartNeeded ? "addons.state.restart_version" : pack.enabled ? "addons.state.on_version" : "addons.state.off_version", {
                version: pack.installed_version ?? "",
              })}
              {props.restartNeeded && !change.note && <RestartNowButton />}
            </p>
          )}
          {installed && update && (
            <p className="pack-update">
              {t("addons.update", { from: pack.installed_version ?? "", to: pack.version })}
            </p>
          )}
          {change.note && <RestartLine text={change.note} />}
          {problem && (
            <p className="problem-note" role="alert">
              {problem}
            </p>
          )}
          {change.needsToken && pack.release_host && (
            <ReadToken pack={pack} base={base} host={pack.release_host} onSaved={change.gotToken} />
          )}
          {change.tokenSaved && (
            <p className="sub" role="status">
              {t("addons.token.saved_note")}
            </p>
          )}
          {safeHomepage && (
            <span className="sub">{t("addons.homepage_line", { domain: pack.homepage_domain ?? "" })}</span>
          )}
        </div>
        <div className="acts">
          {!installed && pack.installable && !change.installed && (
            <button
              type="button"
              id={`pack-install-${index}`}
              className="btn primary"
              data-key="primary"
              disabled={change.busy !== null}
              aria-label={t("addons.install_named", { name: pack.name })}
              onClick={() => void change.install()}
            >
              {t(change.busy === "install" ? "addons.installing" : "addons.install")}
            </button>
          )}
          {!installed && !pack.installable && (
            <button
              type="button"
              id={`pack-get-${index}`}
              className="btn primary"
              data-key="primary"
              aria-label={t("addons.get_named", { name: pack.name })}
              onClick={props.onGet}
            >
              {t("addons.get")}
            </button>
          )}
          {installed && !pack.enabled && (
            <SwitchButton on={false} label={pack.name} busy={power.busy} id={`pack-switch-${index}`} onRun={() => void power.run(true)} />
          )}
          <RowMenu label={pack.name} actions={actions} />
        </div>
      </div>
    </li>
  );
}

/** How to get a pack: the publisher's install text as something to copy, and how to try it on made-up data first. */
function GetIt(props: { pack: Pack; onClose: () => void }) {
  const { t } = useWords();
  const { pack } = props;
  const titleId = useId();
  const demo = pack.demo && SAFE_ID.test(pack.id) ? t("addons.demo_command", { id: pack.id }) : null;
  return (
    <ModalPanel titleId={titleId} onClose={props.onClose}>
      <Heading slot="title" id={titleId}>
        {t("addons.get_title", { name: pack.name })}
      </Heading>
      <div className="get-it">
        <p>{pack.install ? t("addons.install_intro") : t("addons.install_none")}</p>
        {pack.install && <CopyLine text={pack.install} label={t("addons.copy_install")} />}
        {pack.install && <p className="hint">{t("addons.install_check")}</p>}
        {demo && (
          <details className="more-options">
            <summary>{t("addons.for_developers")}</summary>
            <p>{t("addons.demo_intro")}</p>
            <CopyLine text={demo} label={t("addons.copy_demo")} />
          </details>
        )}
      </div>
      <div className="row-end">
        <button type="button" className="btn primary" onClick={props.onClose}>
          {t("action.close")}
        </button>
      </div>
    </ModalPanel>
  );
}

function CopyLine(props: { text: string; label: string }) {
  const { t } = useWords();
  const { push } = useToasts();
  const [blocked, setBlocked] = useState(false);
  const copy = async () => {
    if ((await copyPlain(props.text)) === "blocked") {
      setBlocked(true);
      return;
    }
    setBlocked(false);
    push({ message: t("addons.copied") });
  };
  return (
    <div className="copy-line">
      <div className="copy-row">
        <code className="command">{props.text}</code>
        <button type="button" className="btn" aria-label={props.label} onClick={() => void copy()}>
          {t("addons.copy")}
        </button>
      </div>
      {blocked && (
        <p className="problem-note" role="alert">
          {t("addons.copy_blocked")}
        </p>
      )}
    </div>
  );
}

/** Where a catalog address is read from, for a message: its host, or the address itself when it isn't one. */
const hostOf = (address: string) => {
  try {
    return new URL(address).hostname || address;
  } catch {
    return address;
  }
};

/** The form that lists a catalog by its address: shown in place when none is listed, and from "Add another catalog". */
function AddCatalog(props: { first?: boolean; onDone?: () => void }) {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const id = useId();
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const add = async () => {
    setBusy(true);
    setProblem("");
    try {
      const saved = await api.addCatalog(address.trim(), await fingerprint());
      // The catalog is read at once, so its add-ons are listed when the form goes.
      client.setQueryData(["packs"], await api.refreshPacks());
      await afterSave(saved, { message: t("addons.catalog_added", { domain: hostOf(address.trim()) }) });
      props.onDone?.();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      setBusy(false);
    }
  };
  return (
    <form
      className="panel catalog-add"
      aria-labelledby={`${id}-title`}
      onSubmit={(e) => {
        e.preventDefault();
        if (address.trim() && !busy) void add();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape" && props.onDone) props.onDone();
      }}
    >
      <h3 id={`${id}-title`}>{t("addons.catalog_add_title")}</h3>
      <div className="field">
        <label htmlFor={`${id}-address`}>{t("addons.catalog_address")}</label>
        <input
          id={`${id}-address`}
          type="text"
          inputMode="url"
          autoComplete="off"
          autoFocus
          value={address}
          disabled={busy}
          aria-describedby={`${id}-hint`}
          onChange={(e) => setAddress(e.target.value)}
        />
        <p className="hint" id={`${id}-hint`}>
          {t("addons.catalog_address_hint")}
        </p>
      </div>
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <div className="row-end">
        {!props.first && props.onDone && (
          <button type="button" className="btn quiet" onClick={props.onDone}>
            {t("action.cancel")}
          </button>
        )}
        <button type="submit" className="btn primary" disabled={!address.trim() || busy}>
          {t(busy ? "addons.catalog_adding" : "addons.catalog_add")}
        </button>
      </div>
    </form>
  );
}

/** The row's way to give the read token for the place an add-on's files are kept: typed here on a local app, where the
 * app keeps it on this computer, or as where it is kept. It goes only to that host. Saved, Install can be pressed again. */
function ReadToken(props: { pack: Pack; base: string; host: string; onSaved: () => void }) {
  const { t } = useWords();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  const local = setup.data?.local ?? true;
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [reference, setReference] = useState("");
  const [how, setHow] = useState<"type" | "where" | "held">("type");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const { base, host } = props;
  const byReference = !local || how === "where";
  const ready = byReference ? reference.trim() !== "" : typed.trim() !== "";
  const save = async () => {
    setBusy(true);
    setProblem("");
    try {
      const fp = await fingerprint();
      const saved = await api.giveReadToken(props.pack.id, byReference ? { reference: asReference(reference), fingerprint: fp } : { token: typed.trim(), fingerprint: fp });
      await afterSave(saved, { message: t("addons.token.saved", { host }) });
      props.onSaved();
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      setBusy(false);
    }
  };
  if (!open) {
    return (
      <div>
        <button type="button" className="btn small" aria-label={t("addons.token.add_named", { name: props.pack.name })} onClick={() => setOpen(true)}>
          {t("addons.token.add")}
        </button>
      </div>
    );
  }
  return (
    <form
      className="token-prompt"
      aria-labelledby={`${base}-token-title`}
      onSubmit={(e) => {
        e.preventDefault();
        if (ready && !busy) void save();
      }}
    >
      <p className="what" id={`${base}-token-title`}>
        {t("addons.token.title", { host })}
      </p>
      <p className="hint" id={`${base}-token-hint`}>
        {t("addons.token.intro", { host })}
      </p>
      <div className="field">
        <span className="setting-label" id={`${base}-token-label`}>
          {t("addons.token.label")}
        </span>
        <SecretField
          id={`${base}-token`}
          labelId={`${base}-token-label`}
          label={t("addons.token.label")}
          local={local}
          held={null}
          reference={reference}
          onReference={setReference}
          pasted={typed}
          onPaste={setTyped}
          disabled={busy}
          describedBy={`${base}-token-hint`}
          autoFocus
          onMode={setHow}
        />
      </div>
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" disabled={busy} onClick={() => setOpen(false)}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!ready || busy}>
          {t(busy ? "addons.token.saving" : "addons.token.save")}
        </button>
      </div>
    </form>
  );
}

function Catalog(props: { feeds: Feed[] }) {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [problem, setProblem] = useState("");
  const addButton = useRef<HTMLButtonElement>(null);
  const take = async (feed: Feed) => {
    if (!feed.address) return;
    setBusy(true);
    setProblem("");
    try {
      const saved = await api.removeCatalog(feed.address, await fingerprint());
      client.setQueryData(["packs"], await api.refreshPacks());
      await afterSave(saved, { message: t("addons.catalog_removed", { domain: feed.domain }) });
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    }
    setBusy(false);
  };
  const refresh = async () => {
    setBusy(true);
    setProblem("");
    try {
      client.setQueryData(["packs"], await api.refreshPacks());
    } catch (err) {
      setProblem(problemText(err, t));
    }
    setBusy(false);
  };
  return (
    <section className="catalog" aria-labelledby="catalog-title">
      <div className="heading">
        <h3 id="catalog-title">{t("addons.catalog")}</h3>
        <button type="button" className="btn" disabled={busy} onClick={() => void refresh()}>
          {t(busy ? "addons.refreshing" : "addons.refresh")}
        </button>
      </div>
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <ul className="catalog-list">
        {props.feeds.map((feed, i) => (
          <FeedLine key={`${feed.domain}-${i}`} feed={feed} busy={busy} onRemove={() => void take(feed)} />
        ))}
      </ul>
      {adding ? (
        <AddCatalog
          onDone={() => {
            setAdding(false);
            restoreFocus(() => addButton.current);
          }}
        />
      ) : (
        <button type="button" className="btn quiet" ref={addButton} onClick={() => setAdding(true)}>
          {t("addons.catalog_add_another")}
        </button>
      )}
    </section>
  );
}

function FeedLine(props: { feed: Feed; busy: boolean; onRemove: () => void }) {
  const { t, tn } = useWords();
  const { feed } = props;
  const read = feed.read_at ? when(feed.read_at) : "";
  return (
    <li className="feed">
      <span className="hint">
        {read ? t("addons.feed.read", { domain: feed.domain, when: read }) : t("addons.feed.never", { domain: feed.domain })}
      </span>
      {feed.removable && (
        <button type="button" className="btn quiet small" disabled={props.busy} aria-label={t("addons.catalog_remove_named", { domain: feed.domain })} onClick={props.onRemove}>
          {t("addons.catalog_remove")}
        </button>
      )}
      {feed.error && <p className="problem-note">{t("addons.feed.error", { error: feed.error })}</p>}
      {feed.notes.length > 0 && (
        <details className="feed-notes">
          <summary>{tn("addons.feed.notes", feed.notes.length)}</summary>
          <ul className="plain-list">
            {feed.notes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

/** The same for a pack in the Available list, read from the installed add-on of that name. */
const restartNeeded = (pack: Pack, installed: Installed[]) => {
  const running = installed.find((i) => i.name === pack.id);
  return pack.enabled && running !== undefined && waitsForRestart(running);
};

function InstalledList(props: { items: Installed[] }) {
  const { t } = useWords();
  if (props.items.length === 0) return <p className="empty">{t("addons.installed.empty")}</p>;
  return (
    <ul className="queue">
      {props.items.map((item, i) => (
        <InstalledRow key={`${item.name}-${i}`} item={item} index={i} />
      ))}
    </ul>
  );
}

function InstalledRow(props: { item: Installed; index: number }) {
  const { t } = useWords();
  const { item } = props;
  const base = `installed-${props.index}`;
  const power = useSwitch(item.name, item.name);
  const change = usePackChange(item.name, item.name, () =>
    restoreFocus(() => document.getElementById(`${base}-row`)),
  );
  const problem = change.problem || power.problem;
  const actions: MenuAction[] = [];
  if (!item.enabled && item.removable) {
    actions.push({ id: "remove", label: t("addons.remove"), run: () => void change.remove() });
  }
  const isOn = item.enabled;
  const pending = waitsForRestart(item);
  const statusText = pending
    ? t(isOn ? "addons.state.after_restart" : "addons.state.off_after_restart")
    : item.state === "enabled"
      ? t("addons.state.running")
      : item.reason
        ? t("addons.state.because", { reason: item.reason })
        : t("addons.state.off");
  return (
    <li className="line" id={`${base}-row`} data-row tabIndex={-1} aria-labelledby={`${base}-name`}>
      <div className="row pair">
        <div className="text pack">
          <strong id={`${base}-name`}>{item.name}</strong>
          {item.version && <span className="sub">{t("addons.version", { version: item.version })}</span>}
          {item.description && <p className="pack-summary">{item.description}</p>}
          <p className="sub">
            {statusText}
            {pending && <RestartNowButton />}
          </p>
          {change.note && <RestartLine text={change.note} />}
          {problem && (
            <p className="problem-note" role="alert">
              {problem}
            </p>
          )}
          <WhatLines what={item.what} base={base} />
          {item.state === "enabled" && <AddonSecrets plugin={item.name} />}
        </div>
        <div className="acts">
          <SwitchButton on={isOn} label={item.name} busy={power.busy} onRun={() => void power.run(!isOn)} />
          <RowMenu label={item.name} actions={actions} />
        </div>
      </div>
    </li>
  );
}
