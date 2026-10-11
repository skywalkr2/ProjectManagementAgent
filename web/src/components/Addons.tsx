// Add-ons: where packs are found and what the ones already here do. Available lists packs the configured catalogs
// offer, each with what it does, what it adds, reaches and keeps, what its AI work would cost on the person's own
// accounts, and how to get it; Installed lists the packs this copy of the app has. Everything a catalog says is shown
// as text, and the only address that can be opened is a pack's own page, with its real domain beside it. The app
// never installs anything itself.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";
import { Heading, Tab, TabList, TabPanel, Tabs } from "react-aria-components";
import { api, ApiError, type S } from "../lib/api";
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
  type Summary,
} from "../lib/packs";
import { problemText } from "../lib/problem";
import { useAfterSave } from "../lib/settings-save";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { ModalPanel, restoreFocus } from "./ModalPanel";
import { domainOf } from "./SafeText";
import { RowMenu, type MenuAction } from "./RowMenu";

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
        <h2 id="addons-title">{t("addons.title")}</h2>
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
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };
  return { busy, problem, run };
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
  if (query.isPending) return <p className="empty">{t("loading")}</p>;
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
        ? t("addons.no_packs")
        : null;
  return (
    <div className="addons-body">
      {empty ? (
        <p className="empty">{empty}</p>
      ) : (
        <ul className="queue">
          {view.available.map((pack, i) => (
            <PackRow key={`${pack.id}-${i}`} pack={pack} index={i} onGet={() => setGetting(i)} />
          ))}
        </ul>
      )}
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

function PackRow(props: { pack: Pack; index: number; onGet: () => void }) {
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

  const actions: MenuAction[] = [];
  if (installed && update) actions.push({ id: "update", label: t("addons.get_update"), run: props.onGet });
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
              {t(pack.enabled ? "addons.state.on_version" : "addons.state.off_version", {
                version: pack.installed_version ?? "",
              })}
            </p>
          )}
          {installed && update && (
            <p className="pack-update">
              {t("addons.update", { from: pack.installed_version ?? "", to: pack.version })}
            </p>
          )}
          {power.problem && (
            <p className="problem-note" role="alert">
              {power.problem}
            </p>
          )}
          {safeHomepage && (
            <span className="sub">{t("addons.homepage_line", { domain: pack.homepage_domain ?? "" })}</span>
          )}
        </div>
        <div className="acts">
          {!installed && (
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
          <>
            <p>{t("addons.demo_intro")}</p>
            <CopyLine text={demo} label={t("addons.copy_demo")} />
          </>
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
    try {
      await navigator.clipboard.writeText(props.text);
    } catch {
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

function Catalog(props: { feeds: Feed[] }) {
  const { t } = useWords();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
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
          <FeedLine key={`${feed.domain}-${i}`} feed={feed} />
        ))}
      </ul>
    </section>
  );
}

function FeedLine(props: { feed: Feed }) {
  const { t, tn } = useWords();
  const { feed } = props;
  const read = feed.read_at ? when(feed.read_at) : "";
  return (
    <li className="feed">
      <span className="hint">
        {read ? t("addons.feed.read", { domain: feed.domain, when: read }) : t("addons.feed.never", { domain: feed.domain })}
      </span>
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
  const isOn = item.enabled;
  const status =
    item.state === "enabled"
      ? t("addons.state.running")
      : item.reason
        ? t("addons.state.because", { reason: item.reason })
        : t("addons.state.off");
  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={`${base}-name`}>
      <div className="row pair">
        <div className="text pack">
          <strong id={`${base}-name`}>{item.name}</strong>
          {item.version && <span className="sub">{t("addons.version", { version: item.version })}</span>}
          {item.description && <p className="pack-summary">{item.description}</p>}
          <p className="sub">{status}</p>
          {power.problem && (
            <p className="problem-note" role="alert">
              {power.problem}
            </p>
          )}
          <WhatLines what={item.what} base={base} />
        </div>
        <div className="acts">
          <SwitchButton on={isOn} label={item.name} busy={power.busy} onRun={() => void power.run(!isOn)} />
        </div>
      </div>
    </li>
  );
}
