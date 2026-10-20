// Sign-ins: the services an add-on signs in to, one row each with where the sign-in stands in words and one action.
// Signing in leaves the app for the service's own page in this tab; the service sends the person back afterwards
// (see lib/sign-in-return.ts). The address the service's app registration must allow is always shown, since the
// person needs it when registering the app.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { problemText } from "../lib/problem";
import { useStartSignIn } from "../lib/sign-in-start";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SafeLink } from "./SafeText";

type SignIn = S["SignInView"];
type Account = S["SignInAccount"];

/** The add-on a sign-in belongs to: the part of its name before the "/", or none when the name has no such part. */
export const addonOfSignIn = (name: string): string | null => (name.includes("/") ? name.split("/", 1)[0] : null);

export function SignIns(props: {
  onOpenAddons: () => void;
  /** Opens the form that adds a source, on the kinds of this add-on (null: all kinds). */
  onChooseSource: (plugin: string | null) => void;
}) {
  const { t } = useWords();
  const signIns = useQuery({ queryKey: ["sign-ins"], queryFn: api.signIns });
  // A list that didn't load says so quietly.
  if (signIns.isPending) return null;
  if (signIns.isError) return <p className="hint">{t("sign_in.load_failed")}</p>;
  // Until an add-on signs in to a service there is nothing to list; the way to turn one on is offered instead.
  if (signIns.data.length === 0) {
    return (
      <section className="panel-section" aria-labelledby="sign-ins-title">
        <div className="heading">
          <h3 id="sign-ins-title">{t("sign_in.title")}</h3>
        </div>
        <p className="hint">{t("sign_in.none")}</p>
        <div className="row-end">
          <button type="button" className="btn" onClick={props.onOpenAddons}>
            {t("sign_in.open_addons")}
          </button>
        </div>
      </section>
    );
  }
  return (
    <section className="panel-section" aria-labelledby="sign-ins-title">
      <div className="heading">
        <h3 id="sign-ins-title">{t("sign_in.title")}</h3>
      </div>
      <p className="hint">{t("sign_in.intro")}</p>
      <ul className="queue">
        {signIns.data.map((item) => (
          <SignInRow key={item.name} item={item} onChooseSource={props.onChooseSource} />
        ))}
      </ul>
    </section>
  );
}

/** One sign-in: where it stands in words, with its actions. Once signed in, the next step is the primary action
 * (choosing what to read); signing out and signing in again are in the menu. */
export function SignInRow(props: { item: SignIn; onChooseSource: (plugin: string | null) => void }) {
  const { t } = useWords();
  const act = useAct();
  const [signingOut, setSigningOut] = useState(false);
  const [outProblem, setOutProblem] = useState("");
  // The paste form: open by itself on a row with no registration yet, until the person closes it; elsewhere only when asked for.
  const [formChoice, setFormChoice] = useState<boolean | null>(null);
  const { item } = props;
  const base = `sign-in-${item.name.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  const signedIn = item.status === "signed_in";

  const { start, busy: starting, problem: startProblem } = useStartSignIn(item.name);
  const busy = starting || signingOut;
  const problem = startProblem || outProblem;

  const signOut = async () => {
    setSigningOut(true);
    setOutProblem("");
    await act(
      () => api.signOut(item.name),
      () => ({ message: t("sign_in.signed_out_toast", { label: item.label }) }),
    );
    setSigningOut(false);
  };

  // A service that names its accounts lists each one with its own Sign out; signing in again adds another.
  const several = Boolean(item.several);
  const accounts = several ? (item.accounts ?? []) : [];
  const signOutAccount = async (a: Account) => {
    setSigningOut(true);
    setOutProblem("");
    const who = a.address ?? t("sign_in.account_unnamed");
    await act(
      () => api.signOut(item.name, a.key),
      () => ({ message: t("sign_in.signed_out_account_toast", { account: who, label: item.label }) }),
    );
    setSigningOut(false);
  };

  const again = item.status === "expired";
  const notReading = signedIn ? (item.not_reading ?? []) : [];
  const label = notReading.length > 0
    ? t("sign_in.start_reading")
    : signedIn
    ? t("sign_in.choose_source")
    : busy
      ? t("sign_in.working")
      : t(again ? "sign_in.sign_in_again" : "sign_in.sign_in");
  const named = notReading.length > 0
    ? t("sign_in.start_reading_named", { label: item.label })
    : signedIn
    ? t("sign_in.choose_source_named", { label: item.label })
    : t(again ? "sign_in.sign_in_again_named" : "sign_in.sign_in_named", { label: item.label });
  const notReady = !signedIn && !item.ready;
  const formOpen = item.can_paste && (formChoice ?? item.app === "none");
  const pasted = item.app === "pasted";
  const allows = signedIn ? [] : (item.allows ?? []);
  const missing = signedIn ? (item.missing ?? []) : [];
  const showHint = notReady && !formOpen;
  const describedBy = [
    problem && `${base}-problem`,
    showHint && `${base}-not-ready`,
    notReading.length > 0 && `${base}-not-reading`,
  ]
    .filter(Boolean)
    .join(" ");
  const menuId = `${base}-menu`;

  const openForm = () => {
    setFormChoice(true);
    window.requestAnimationFrame(() => document.getElementById(`${base}-client-id`)?.focus());
  };
  const closeForm = () => {
    setFormChoice(false);
    setOutProblem("");
    window.requestAnimationFrame(() => (document.getElementById(menuId) ?? document.getElementById(`${base}-title`))?.focus());
  };

  const stopUsing = () =>
    void act(
      () => api.setAsideSignInApp(item.name),
      () => ({
        message: t("sign_in.own.stopped_toast", { label: item.label }),
        undo: () => api.bringBackSignInApp(item.name),
      }),
    );
  const bringBack = () =>
    void act(
      () => api.bringBackSignInApp(item.name),
      () => ({
        message: t("sign_in.own.brought_back_toast", { label: item.label }),
        undo: () => api.setAsideSignInApp(item.name),
      }),
    );

  const startReading = () =>
    void act(
      () => api.startSignInSources(item.name),
      () => ({ message: t("sign_in.started_reading_toast", { list: notReading.join(", ") }) }),
    );

  const actions: MenuAction[] = [];
  if (signedIn && notReading.length > 0) {
    actions.push({ id: "choose", label: t("sign_in.choose_source"), run: () => props.onChooseSource(addonOfSignIn(item.name)), disabled: busy });
  }
  if (signedIn && !several) {
    actions.push({ id: "sign-out", label: t("sign_in.sign_out"), run: () => void signOut(), disabled: busy });
    actions.push({ id: "sign-in-again", label: t("sign_in.sign_in_again"), run: () => void start(), disabled: busy || !item.ready });
  }
  if (item.can_paste && !formOpen && !pasted && (item.app === "add-on" || item.app === "none")) {
    actions.push({ id: "use-own", label: t("sign_in.own.use"), run: openForm, disabled: busy });
  }
  if (pasted) actions.push({ id: "stop", label: t("sign_in.own.stop"), run: stopUsing, disabled: busy });
  if (item.set_aside && !pasted) actions.push({ id: "bring-back", label: t("sign_in.own.bring_back"), run: bringBack, disabled: busy });

  const callbackField = (
    <div className="field">
      <label htmlFor={`${base}-callback`}>{t("sign_in.callback")}</label>
      <input
        id={`${base}-callback`}
        type="text"
        readOnly
        value={item.callback}
        aria-describedby={`${base}-callback-hint`}
        onFocus={(e) => e.currentTarget.select()}
      />
      <p className="hint" id={`${base}-callback-hint`}>
        {t("sign_in.callback_hint")}
      </p>
    </div>
  );

  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={`${base}-title`}>
      <div className="row pair">
        <div className="text">
          <strong id={`${base}-title`}>{item.label}</strong>
          {accounts.length > 0 ? (
            <ul className="plain-list" aria-label={t("sign_in.accounts")}>
              {accounts.map((a) => {
                const who = a.address ?? t("sign_in.account_unnamed");
                return (
                  <li key={a.key} className="row pair">
                    <span className="sub">
                      {who}
                      {a.status === "expired" && <> · {t("sign_in.status.expired")}</>}
                    </span>
                    <span className="acts">
                      {a.status === "expired" && (
                        <button
                          type="button"
                          className="btn quiet"
                          disabled={busy || !item.ready}
                          aria-label={t("sign_in.sign_in_again_account", { account: who })}
                          onClick={() => void start()}
                        >
                          {t("sign_in.sign_in_again")}
                        </button>
                      )}
                      <button
                        type="button"
                        className="btn quiet"
                        disabled={busy}
                        aria-label={t("sign_in.sign_out_account", { account: who })}
                        onClick={() => void signOutAccount(a)}
                      >
                        {t("sign_in.sign_out")}
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <span className="sub">
              {signedIn && item.account
                ? t("sign_in.status.signed_in_as", { account: item.account })
                : t(`sign_in.status.${item.status}`)}
            </span>
          )}
          {several && accounts.length > 0 && (
            <div className="row-end">
              <button
                type="button"
                className="btn quiet"
                disabled={busy || !item.ready}
                aria-label={t("sign_in.add_account_named", { label: item.label })}
                onClick={() => void start()}
              >
                {t("sign_in.add_account")}
              </button>
            </div>
          )}
          {allows.length > 0 && (
            <div className="field">
              <span className="what" id={`${base}-allows`}>
                {t("sign_in.allows")}
              </span>
              <ul className="plain-list" aria-labelledby={`${base}-allows`}>
                {allows.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </div>
          )}
          {notReading.length > 0 && (
            <p className="hint" id={`${base}-not-reading`}>
              {t("sign_in.not_reading", { list: notReading.join(", ") })}
            </p>
          )}
          {missing.length > 0 && (
            <div className="field">
              <p className="hint" id={`${base}-missing`}>
                {t("sign_in.missing", { list: missing.join(", ") })}
              </p>
              <div className="row-end">
                <button
                  type="button"
                  className="btn"
                  disabled={busy || !item.ready}
                  aria-label={t("sign_in.sign_in_again_named", { label: item.label })}
                  aria-describedby={`${base}-missing`}
                  onClick={() => void start()}
                >
                  {t("sign_in.sign_in_again")}
                </button>
              </div>
            </div>
          )}
          {item.app === "add-on" && item.app_note && <p className="hint">{item.app_note}</p>}
          {item.default_unusable && !pasted && (
            <p className="hint" id={`${base}-unusable`}>
              {t("sign_in.default_unusable")}
            </p>
          )}
          {pasted && <p className="hint">{t("sign_in.own.using")}</p>}
          {showHint && (
            <p className="hint" id={`${base}-not-ready`}>
              {t("sign_in.not_ready")}
            </p>
          )}
          {problem && (
            <p className="problem-note" id={`${base}-problem`} role="alert">
              {problem}
            </p>
          )}
          {formOpen ? (
            <OwnAppForm
              item={item}
              base={base}
              callbackField={callbackField}
              onClose={closeForm}
              onProblem={setOutProblem}
              onSaved={closeForm}
              disabled={busy}
            />
          ) : (
            callbackField
          )}
        </div>
        <div className="acts">
          <button
            type="button"
            className="btn primary"
            data-key="primary"
            disabled={busy || notReady}
            aria-label={named}
            aria-describedby={describedBy || undefined}
            onClick={() =>
              notReading.length > 0
                ? startReading()
                : signedIn
                  ? props.onChooseSource(addonOfSignIn(item.name))
                  : void start()
            }
          >
            {label}
          </button>
          <RowMenu label={item.label} actions={actions} buttonId={menuId} />
        </div>
      </div>
    </li>
  );
}

/** The person's own app registration, pasted in place: how to make one, the address it must allow, and its details. */
function OwnAppForm(props: {
  item: SignIn;
  base: string;
  callbackField: ReactNode;
  disabled: boolean;
  onClose: () => void;
  onProblem: (text: string) => void;
  onSaved: () => void;
}) {
  const { t } = useWords();
  const client = useQueryClient();
  const { push } = useToasts();
  const { item, base } = props;
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const id = clientId.trim();
  const key = secret.trim();
  const filled = id !== "" && (!item.needs_secret || key !== "");
  const steps = item.own_app_steps ?? [];

  const save = async () => {
    if (!filled || saving || props.disabled) return;
    setSaving(true);
    props.onProblem("");
    try {
      await api.saveSignInApp(item.name, item.needs_secret ? { client_id: id, client_secret: key } : { client_id: id });
      await client.invalidateQueries();
      push({ message: t("sign_in.own.saved_toast", { label: item.label }) });
      props.onSaved();
    } catch (err) {
      props.onProblem(problemText(err, t));
      if (mounted.current) setSaving(false);
    }
  };

  return (
    <form
      className="field"
      aria-label={t("sign_in.own.form", { label: item.label })}
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <p className="hint">{t("sign_in.own.lead")}</p>
      {steps.length > 0 && (
        <div className="field">
          <h4 id={`${base}-steps`}>{t("sign_in.own.steps_title")}</h4>
          <ol className="own-steps" aria-labelledby={`${base}-steps`}>
            {steps.map((step, i) => (
              <li key={i}>{step.link ? <SafeLink label={step.text} url={step.link} /> : step.text}</li>
            ))}
          </ol>
        </div>
      )}
      {props.callbackField}
      <div className="field">
        <label htmlFor={`${base}-client-id`}>{t("sign_in.own.client_id")}</label>
        <input
          id={`${base}-client-id`}
          type="text"
          value={clientId}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => setClientId(e.target.value)}
        />
      </div>
      {item.needs_secret && (
        <div className="field">
          <label htmlFor={`${base}-client-secret`}>{t("sign_in.own.client_secret")}</label>
          <input
            id={`${base}-client-secret`}
            type="password"
            value={secret}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => setSecret(e.target.value)}
          />
        </div>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" aria-label={t("sign_in.own.cancel_named", { label: item.label })} onClick={props.onClose}>
          {t("action.cancel")}
        </button>
        <button
          type="submit"
          className="btn"
          disabled={!filled || saving || props.disabled}
          aria-label={t("sign_in.own.save_named", { label: item.label })}
        >
          {saving ? t("sign_in.own.saving") : t("sign_in.own.save")}
        </button>
      </div>
    </form>
  );
}

/** Signed-in accounts whose add-on reads something by default (the inbox, the calendar) that nothing reads yet, one
 * line each with Start reading: how a source the person removed comes back without filling in a form. */
export function NotReadingLines() {
  const { t } = useWords();
  const act = useAct();
  const signIns = useQuery({ queryKey: ["sign-ins"], queryFn: api.signIns });
  const waiting = (signIns.data ?? []).filter((s) => s.status === "signed_in" && (s.not_reading ?? []).length > 0);
  if (waiting.length === 0) return null;
  return (
    <ul className="plain-list" aria-label={t("sign_in.start_reading")}>
      {waiting.map((item) => {
        const list = (item.not_reading ?? []).join(", ");
        const id = `not-reading-${item.name.replace(/[^A-Za-z0-9_-]/g, "-")}`;
        return (
          <li key={item.name} className="row pair">
            <p className="hint" id={id}>
              {t("sources.signed_in_not_reading", { label: item.label, list })}
            </p>
            <button
              type="button"
              className="btn primary"
              aria-label={t("sign_in.start_reading_named", { label: item.label })}
              aria-describedby={id}
              onClick={() =>
                void act(
                  () => api.startSignInSources(item.name),
                  () => ({ message: t("sign_in.started_reading_toast", { list }) }),
                )
              }
            >
              {t("sign_in.start_reading")}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
