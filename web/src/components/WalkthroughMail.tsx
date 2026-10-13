// The mail and calendar screen of the walkthrough (design 7.8): the services the person can connect, each in the state it
// is in. One not yet installed is installed and turned on with one button; one installed but off is turned on; then the
// one restart ("Restart to connect"), never made on its own; then Sign in. Once signed in the screen says what is read now
// and that the last day's mail waits for the first Go. The core's own mail folder and calendar address are offered as
// "Another mail or calendar".
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { serviceReachLines, waitsForRestart } from "../lib/packs";
import { problemText } from "../lib/problem";
import { useRestart } from "../lib/restart";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { useStartSignIn } from "../lib/sign-in-start";
import { useWords } from "../lib/wording";
import { Skeleton } from "../ui/Skeleton";
import { addonOfSignIn } from "./SignIns";

type Pack = S["PackView"];
type Installed = S["InstalledPackView"];
type SignIn = S["SignInView"];

/** Where a service stands on the way to being read. */
export type ServiceState = "not_installed" | "off" | "restart" | "problem" | "ready";

export interface Service {
  id: string;
  name: string;
  summary: string;
  /** Who made it, when the catalog says; empty for an add-on that is here but not listed. */
  publisher: string;
  reads: Array<"mail" | "calendar">;
  state: ServiceState;
  /** Why an add-on that is on isn't running, in the app's words. */
  reason: string;
  /** The app can install it from here (the add-on is listed with a release it understands). */
  installable: boolean;
  what: S["PackSummary"];
}

/** A service is an add-on that signs in to something and reads mail or a calendar. */
const connects = (what: S["PackSummary"]) => (what.reads ?? []).length > 0 && what.reaches.sign_ins.length > 0;

/** The services to offer: the catalogs' entries, then add-ons already here that the catalogs don't list. */
export function servicesFrom(available: Pack[], installed: Installed[]): Service[] {
  const running = new Map(installed.map((i) => [i.name, i]));
  const found = new Map<string, Service>();
  const stateOf = (here: Installed | undefined): { state: ServiceState; reason: string } => {
    if (!here) return { state: "not_installed", reason: "" };
    if (!here.enabled) return { state: "off", reason: "" };
    if (waitsForRestart(here)) return { state: "restart", reason: "" };
    if (here.state === "enabled") return { state: "ready", reason: "" };
    return { state: "problem", reason: here.reason ?? "" };
  };
  for (const pack of available) {
    if (!connects(pack.what) || found.has(pack.id)) continue;
    const here = pack.installed_version != null ? running.get(pack.id) : undefined;
    found.set(pack.id, {
      id: pack.id,
      name: pack.name,
      summary: pack.summary,
      publisher: pack.publisher,
      reads: pack.what.reads ?? [],
      ...stateOf(here),
      installable: !!pack.installable,
      what: pack.what,
    });
  }
  for (const item of installed) {
    if (!connects(item.what) || found.has(item.name)) continue;
    found.set(item.name, {
      id: item.name,
      name: item.name,
      summary: item.description,
      publisher: "",
      reads: item.what.reads ?? [],
      ...stateOf(item),
      installable: false,
      what: item.what,
    });
  }
  return [...found.values()];
}

/** The setting that decides whether the assistant sorts the mail the rules can't place; it is on unless set to rules. */
const SORTING = "watch.sorting";

/** Whether the assistant sorts what the rules can't, from sender, subject and category only: a setting the running app
 *  takes in at once, saved like any other, with its read-back and Undo. */
function SortingSwitch() {
  const { t } = useWords();
  const afterSave = useAfterSave();
  const fresh = useFreshFingerprint();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [problem, setProblem] = useState("");
  const on = settings.data?.items.find((i) => i.key === SORTING)?.value !== "rules";
  const change = async (next: boolean) => {
    setProblem("");
    try {
      const saved = await api.saveSettings({ changes: { [SORTING]: next ? "ai" : "rules" }, reset: [], fingerprint: await fresh() });
      await afterSave(saved);
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    }
  };
  return (
    <div className="field" data-sorting="">
      <label className="check-line">
        <input type="checkbox" checked={on} disabled={settings.isPending} onChange={(e) => void change(e.target.checked)} />
        <span>{t("walkthrough.mail.sorting")}</span>
      </label>
      <p className="hint">{t("walkthrough.mail.sorting_hint")}</p>
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}

export function WalkthroughMail(props: { onChooseSource: (plugin: string | null) => void; onOpenAddons: () => void }) {
  const { t } = useWords();
  const client = useQueryClient();
  const restart = useRestart();
  const packs = useQuery({ queryKey: ["packs"], queryFn: api.packs });
  const signIns = useQuery({ queryKey: ["sign-ins"], queryFn: api.signIns });
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const sources = useQuery({ queryKey: ["watch"], queryFn: api.watchSources });

  // After the app comes back the add-ons that were waiting for it are running: read their state again.
  useEffect(() => {
    if (restart.phase === "done") void client.invalidateQueries();
  }, [restart.phase, client]);

  if (packs.isPending) return <Skeleton />;
  const services = packs.data ? servicesFrom(packs.data.available, packs.data.installed) : [];
  const waiting = services.some((s) => s.state === "restart");
  const canRestart = !!status.data?.can_restart;
  const read = (sources.data ?? []).filter((s) => s.enabled && (s.reads ?? []).length > 0);

  return (
    <div className="mail-step">
      {packs.isError && <p className="problem-note">{t("walkthrough.mail.load_failed")}</p>}
      {services.length > 0 ? (
        <>
          <p className="what" id="mail-services">
            {t("walkthrough.mail.services")}
          </p>
          <ul className="queue" aria-labelledby="mail-services">
            {services.map((service) => (
              <ServiceRow
                key={service.id}
                service={service}
                signIns={(signIns.data ?? []).filter((s) => addonOfSignIn(s.name) === service.id)}
                onOpenAddons={props.onOpenAddons}
              />
            ))}
          </ul>
        </>
      ) : (
        <p className="hint">{t("walkthrough.mail.none")}</p>
      )}
      {waiting && (
        <div className="restart-step" role="status">
          <p>{t(canRestart ? "walkthrough.mail.restart_why" : "walkthrough.mail.restart_manual")}</p>
          {canRestart && (
            <div className="row-end">
              <button
                type="button"
                className="btn primary"
                disabled={restart.busy || restart.waiting}
                onClick={() => void restart.now()}
              >
                {restart.waiting ? t("walkthrough.mail.restarting") : t("walkthrough.mail.restart")}
              </button>
            </div>
          )}
          {restart.phase === "refused" && restart.problem && (
            <p className="problem-note" role="alert">
              {restart.problem}
            </p>
          )}
          {restart.phase === "stuck" && (
            <p className="problem-note" role="alert">
              {t("restart.stuck")}
            </p>
          )}
        </div>
      )}
      <div className="field">
        <p className="hint" id="mail-other">
          {t("walkthrough.mail.other_hint")}
        </p>
        <div className="row-end">
          <button type="button" className="btn" aria-describedby="mail-other" onClick={() => props.onChooseSource(null)}>
            {t("walkthrough.mail.other")}
          </button>
        </div>
      </div>
      <p className="hint" data-set-aside="">
        {t("walkthrough.mail.set_aside")}
      </p>
      <SortingSwitch />
      {read.length > 0 && (
        <div className="field" data-reading="">
          <span className="what" id="mail-read">
            {t("walkthrough.mail.reading")}
          </span>
          <ul className="plain-list" aria-labelledby="mail-read">
            {read.map((source) => (
              <li key={source.id}>{source.label}</li>
            ))}
          </ul>
          <p className="hint">{t("walkthrough.mail.first_go")}</p>
        </div>
      )}
    </div>
  );
}

/** One service: what it reads, where it stands and the one button for the next thing to do. */
function ServiceRow(props: { service: Service; signIns: SignIn[]; onOpenAddons: () => void }) {
  const { t, tn } = useWords();
  const client = useQueryClient();
  const restart = useRestart();
  const { service } = props;
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [done, setDone] = useState(false);
  const base = `service-${service.id.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  // Installing and turning on are one button; a row that has just done them says so until the restart.
  const state: ServiceState = done && (service.state === "not_installed" || service.state === "off") ? "restart" : service.state;

  const connect = async () => {
    setBusy(true);
    setProblem("");
    try {
      if (service.state === "not_installed") await api.installPack(service.id);
      // The settings as they are now, so a change made meanwhile is noticed rather than overwritten.
      const current = await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 });
      const saved = await api.packOn(service.id, current.fingerprint);
      if (saved.needs_restart) restart.offer();
      setDone(true);
      await client.invalidateQueries();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };

  const reads = service.reads.map((kind) => t(`walkthrough.mail.reads.${kind}`)).join(t("walkthrough.mail.reads_join"));
  const reaches = serviceReachLines(service.what.reaches, t, tn);
  // Once the person has signed in, the row says so and what is read, and offers no Sign in.
  const signedIn = state === "ready" && props.signIns.length > 0 && props.signIns.every((item) => item.status === "signed_in");
  return (
    <li
      className="line"
      id={base}
      data-service={service.id}
      data-state={state}
      data-signed-in={signedIn ? "" : undefined}
      aria-labelledby={`${base}-name`}
    >
      <div className="row pair">
        <div className="text pack">
          <strong id={`${base}-name`}>{service.name}</strong>
          <span className="sub">{t("walkthrough.mail.reads_line", { reads })}</span>
          {service.publisher && <span className="sub">{t("walkthrough.mail.publisher", { publisher: service.publisher })}</span>}
          {service.summary && <p className="pack-summary">{service.summary}</p>}
          <details className="more-options">
            <summary>{t("walkthrough.mail.reaches")}</summary>
            <ul className="plain-list">
              {reaches.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </details>
          <p className="sub" id={`${base}-state`}>
            {state === "problem" && service.reason
              ? t("walkthrough.mail.state.problem", { reason: service.reason })
              : signedIn
                ? t("walkthrough.mail.state.signed_in", { reads })
                : t(`walkthrough.mail.state.${state}`)}
          </p>
          {problem && (
            <p className="problem-note" role="alert">
              {problem}
            </p>
          )}
          {state === "ready" &&
            props.signIns.map((item) => <ServiceSignIn key={item.name} item={item} />)}
        </div>
        <div className="acts">
          {state === "not_installed" && service.installable && (
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              aria-label={t("walkthrough.mail.connect_named", { name: service.name })}
              aria-describedby={`${base}-state`}
              onClick={() => void connect()}
            >
              {busy ? t("walkthrough.mail.connecting") : t("walkthrough.mail.connect")}
            </button>
          )}
          {state === "not_installed" && !service.installable && (
            <button type="button" className="btn" onClick={props.onOpenAddons}>
              {t("walkthrough.mail.get_it")}
            </button>
          )}
          {state === "off" && (
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              aria-label={t("walkthrough.mail.turn_on_named", { name: service.name })}
              aria-describedby={`${base}-state`}
              onClick={() => void connect()}
            >
              {busy ? t("walkthrough.mail.connecting") : t("walkthrough.mail.turn_on")}
            </button>
          )}
        </div>
      </div>
    </li>
  );
}

/** A sign-in of a running service: where it stands, and the button that sends the person to the service's own page. */
function ServiceSignIn(props: { item: SignIn }) {
  const { t } = useWords();
  const { item } = props;
  const { start, busy, problem } = useStartSignIn(item.name);
  const signedIn = item.status === "signed_in";
  const again = item.status === "expired";
  return (
    <div className="service-sign-in" data-sign-in={item.name}>
      {signedIn ? (
        <p className="sub">
          <span aria-hidden="true">✓ </span>
          {item.account ? t("walkthrough.mail.signed_in_as", { account: item.account }) : t("walkthrough.mail.signed_in")}
        </p>
      ) : (
        <>
          {(item.allows ?? []).length > 0 && (
            <p className="sub">{t("walkthrough.mail.allows", { allows: (item.allows ?? []).join("; ") })}</p>
          )}
          {problem && (
            <p className="problem-note" role="alert">
              {problem}
            </p>
          )}
          <div className="row-end">
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              aria-label={t(again ? "sign_in.sign_in_again_named" : "sign_in.sign_in_named", { label: item.label })}
              onClick={() => void start()}
            >
              {busy ? t("sign_in.working") : t(again ? "sign_in.sign_in_again" : "sign_in.sign_in")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
