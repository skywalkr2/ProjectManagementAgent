// The setup guide (design 7.8): one section per step, in the order the server gives, each saying in words whether it is
// done or skipped, with its own controls and a way to skip it or come back to it. The core's steps have fixed controls;
// a plugin's step shows its own words and starts its action.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { problemText } from "../lib/problem";
import { useRestart } from "../lib/restart";
import { useStartSignIn } from "../lib/sign-in-start";
import { addonLabel, formatValue, labelOf } from "../lib/settings";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { useActionReview } from "./ActionReview";
import { SignInRow } from "./SignIns";
import { WelcomeAi } from "./WelcomeAi";
import { WelcomeBackup } from "./WelcomeBackup";

type Step = S["SetupStepView"];

/** The id of a step's section, so Today can open the guide at one step. */
export const stepSlug = (id: string) => `guide-${id.replace(/[^a-z0-9]+/gi, "-")}`;

export interface FocusStep {
  id: string;
  n: number;
}

export function Welcome(props: {
  focusStep: FocusStep | null;
  onOpenPeople: () => void;
  onOpenAddons: () => void;
  onHandIn: () => void;
  onChooseSource: (plugin: string | null) => void;
}) {
  const { t, has } = useWords();
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  const { start, review } = useActionReview();
  const focused = useRef<number | null>(null);
  const loaded = !!setup.data;

  // Opening the guide at a step scrolls to it and puts focus on its heading.
  useEffect(() => {
    const want = props.focusStep;
    if (!want || !loaded || focused.current === want.n) return;
    const heading = document.getElementById(`${stepSlug(want.id)}-title`);
    if (!heading) return;
    focused.current = want.n;
    heading.scrollIntoView?.({ block: "start" });
    heading.focus();
  }, [props.focusStep, loaded]);

  return (
    <section className="panel-section" aria-labelledby="welcome-title">
      <div className="heading">
        <h2 id="welcome-title">{t("welcome.title")}</h2>
      </div>
      <p className="hint">{t("welcome.intro")}</p>
      {setup.isPending ? (
        <p className="empty">{t("loading")}</p>
      ) : setup.isError ? (
        <p className="empty">{t("welcome.failed")}</p>
      ) : (
        <ol className="guide">
          {setup.data.steps.map((step) => {
            // A sign-in's step is worded by the guide from the service's label; its explanation lists what is asked.
            const label = step.sign_in
              ? t("welcome.sign_in.title", { label: step.label || step.sign_in })
              : step.label || (has(`setup_step.${step.id}`) ? t(`setup_step.${step.id}`) : step.id);
            const why = step.sign_in
              ? step.explanation
                ? t("welcome.sign_in.explanation", { allows: step.explanation })
                : ""
              : step.explanation || (has(`setup_step.${step.id}.explanation`) ? t(`setup_step.${step.id}.explanation`) : "");
            return (
              <StepSection key={step.id} step={step} label={label} explanation={why}>
                {step.sign_in ? (
                  <SignInStep name={step.sign_in} label={step.label || step.sign_in} done={step.done} onChooseSource={props.onChooseSource} />
                ) : step.id === "workspace" ? (
                  <WorkspaceStep />
                ) : step.id === "template" ? (
                  <TemplateStep />
                ) : step.id === "ai" ? (
                  <WelcomeAi local={setup.data.local} done={step.done} />
                ) : step.id === "backup" ? (
                  <WelcomeBackup local={setup.data.local} />
                ) : step.id === "people" ? (
                  <div className="row-end">
                    <button type="button" className="btn" onClick={props.onOpenPeople}>
                      {t("welcome.people.open")}
                    </button>
                  </div>
                ) : step.id === "addons" ? (
                  <AddonsStep onOpen={props.onOpenAddons} />
                ) : step.id === "first_note" ? (
                  <div className="row-end">
                    <button type="button" className="btn" onClick={props.onHandIn}>
                      {t("handin.open")}
                    </button>
                  </div>
                ) : (
                  <>
                    {hasSettings(step) && <SuggestedSettings step={step} />}
                    {step.action && (
                      <div className="row-end">
                        <button
                          type="button"
                          className="btn"
                          onClick={() => start({ name: step.action!, label, on: null }, null)}
                        >
                          {label}
                        </button>
                      </div>
                    )}
                  </>
                )}
              </StepSection>
            );
          })}
        </ol>
      )}
      {review}
    </section>
  );
}

/** A sign-in's step: one button that starts the sign-in, as the Sign-ins row does. Once signed in, the row itself, with
 * the actions it has there (choose what to read, sign out, sign in again). */
function SignInStep(props: { name: string; label: string; done: boolean; onChooseSource: (plugin: string | null) => void }) {
  const { t } = useWords();
  const { start, busy, problem } = useStartSignIn(props.name);
  const signIns = useQuery({ queryKey: ["sign-ins"], queryFn: api.signIns, enabled: props.done });
  if (props.done) {
    const row = signIns.data?.find((item) => item.name === props.name);
    return row ? (
      <ul className="queue">
        <SignInRow item={row} onChooseSource={props.onChooseSource} />
      </ul>
    ) : null;
  }
  return (
    <>
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <div className="row-end">
        <button
          type="button"
          className="btn"
          disabled={busy}
          aria-label={t("sign_in.sign_in_named", { label: props.label })}
          onClick={() => void start()}
        >
          {busy ? t("sign_in.working") : t("sign_in.sign_in")}
        </button>
      </div>
    </>
  );
}

/** The add-ons installed here and turned off, by name, with one button that opens the Add-ons screen. */
function AddonsStep(props: { onOpen: () => void }) {
  const { t, has } = useWords();
  const act = useAct();
  const [busy, setBusy] = useState(false);
  const leaveOff = async () => {
    setBusy(true);
    await act(
      () => api.leaveAddonsOff(),
      () => ({ message: t("welcome.addons.left_off_toast") }),
    );
    setBusy(false);
  };
  const packs = useQuery({ queryKey: ["packs"], queryFn: api.packs });
  const off = (packs.data?.installed ?? []).filter((p) => !p.enabled);
  return (
    <>
      {off.length > 0 && (
        <div className="field">
          <span className="what" id="guide-addons-off">
            {t("welcome.addons.off_title")}
          </span>
          <ul className="plain-list" aria-labelledby="guide-addons-off">
            {off.map((p) => (
              <li key={p.name}>{addonLabel(p.name, t, has)}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="row-end">
        {off.length > 0 && (
          <button type="button" className="btn" disabled={busy} onClick={() => void leaveOff()}>
            {t("welcome.addons.leave_off")}
          </button>
        )}
        <button type="button" className="btn" onClick={props.onOpen}>
          {t("welcome.addons.open")}
        </button>
      </div>
    </>
  );
}

const hasSettings = (step: Step) => Object.keys(step.settings ?? {}).length > 0;

/** The settings a step suggests, in words, with one button that applies them all and reads the result back. */
function SuggestedSettings(props: { step: Step }) {
  const { t, has } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const { step } = props;
  const label = (key: string) => {
    const item = settings.data?.items.find((i) => i.key === key);
    return item ? labelOf(item, t, has) : has(`settings.key.${key}`) ? t(`settings.key.${key}`) : key;
  };

  const apply = async () => {
    setBusy(true);
    setProblem("");
    try {
      // The fingerprint of the settings as they are now, so a change made meanwhile is noticed rather than overwritten.
      const current = await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 });
      const saved = await api.applyStepSettings(step.id, current.fingerprint);
      await afterSave(saved);
    } catch (err) {
      setProblem(problemText(err, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="field">
      <span className="what" id={`${stepSlug(step.id)}-settings`}>
        {t("welcome.settings.title")}
      </span>
      <ul className="plain-list" aria-labelledby={`${stepSlug(step.id)}-settings`}>
        {Object.entries(step.settings ?? {}).map(([key, value]) => (
          <li key={key}>{t("welcome.settings.line", { label: label(key), value: formatValue(value, t) })}</li>
        ))}
      </ul>
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <div className="row-end">
        <button type="button" className="btn" disabled={busy} onClick={() => void apply()}>
          {t("welcome.settings.apply")}
        </button>
      </div>
    </div>
  );
}

function StepSection(props: { step: Step; label: string; explanation: string; children: ReactNode }) {
  const { t, has } = useWords();
  const act = useAct();
  const { step, label } = props;
  const slug = stepSlug(step.id);
  const state = step.done ? "done" : step.skipped ? "skipped" : "todo";
  const skipWords = has(`welcome.skip.${step.id}`) ? t(`welcome.skip.${step.id}`) : t("welcome.skip");
  const toggle = () =>
    step.skipped
      ? void act(
          () => api.reopenStep(step.id),
          () => ({ message: t("welcome.reopened", { label }), undo: () => api.skipStep(step.id) }),
        )
      : void act(
          () => api.skipStep(step.id),
          () => ({ message: t("welcome.skipped_toast", { label }), undo: () => api.reopenStep(step.id) }),
        );
  return (
    <li id={slug} className="panel guide-step" data-step={step.id} data-state={state} aria-labelledby={`${slug}-title`}>
      <div className="heading">
        <h3 id={`${slug}-title`} tabIndex={-1}>
          {label}
        </h3>
        <span className={`pill state-${state}`}>
          <span aria-hidden="true">{state === "done" ? "✓ " : state === "skipped" ? "– " : "○ "}</span>
          {t(state === "done" ? "start.done" : state === "skipped" ? "welcome.state_skipped" : "start.not_done")}
        </span>
      </div>
      {props.explanation && <p className="hint">{props.explanation}</p>}
      {props.children}
      {!step.done && (
        <div className="row-end">
          <button
            type="button"
            className="btn quiet"
            aria-label={t(step.skipped ? "welcome.reopen_named" : "welcome.skip_named", { label, skip: skipWords })}
            onClick={toggle}
          >
            {step.skipped ? t("welcome.reopen") : skipWords}
          </button>
        </div>
      )}
    </li>
  );
}

// ---- workspace -----------------------------------------------------------------------------------------------------

const NAME = "workspace.name";
const TIMEZONE = "workspace.user.timezone";

function browserZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

function WorkspaceStep() {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  // The person's name lives on their person record only; the settings hold the workspace's own values.
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [nameEdit, setNameEdit] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  if (!settings.data || !me.data) {
    return <p className="empty">{t(settings.isError || me.isError ? "welcome.failed" : "loading")}</p>;
  }
  const fullName = nameEdit ?? me.data.full_name;
  const nameChanged = fullName.trim() !== me.data.full_name;

  const item = (key: string) => settings.data.items.find((i) => i.key === key);
  const current = (key: string): string => {
    const found = item(key);
    const value = found?.value == null ? "" : String(found.value);
    // The time zone is offered from this browser while it is still the default.
    if (key === TIMEZONE && found && found.source === "default" && found.value === found.default) return browserZone() || value;
    return value;
  };
  const shown = (key: string) => edits[key] ?? current(key);
  const stored = (key: string) => (item(key)?.value == null ? "" : String(item(key)?.value));
  const changes: Record<string, string> = {};
  for (const key of [NAME, TIMEZONE]) {
    const found = item(key);
    if (found && found.editable && !found.locked && shown(key).trim() !== stored(key)) changes[key] = shown(key).trim();
  }
  const empty = Object.values(changes).some((v) => v === "") || (nameChanged && !fullName.trim());
  const pending = Object.keys(changes).length > 0 || nameChanged;

  const save = async () => {
    setBusy(true);
    setProblem("");
    try {
      if (nameChanged) {
        await api.saveMe(fullName.trim());
        setNameEdit(null);
        await client.invalidateQueries({ queryKey: ["me"] });
        await client.invalidateQueries({ queryKey: ["people"] });
      }
      if (Object.keys(changes).length) {
        const fresh = nameChanged ? await api.settings() : settings.data!;
        const saved = await api.saveSettings({ changes, reset: [], fingerprint: fresh.fingerprint });
        setEdits({});
        await afterSave(saved);
      } else {
        await client.invalidateQueries({ queryKey: ["setup"] });
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };

  const field = (key: string, labelKey: string, hintKey: string | null) => {
    const found = item(key);
    const off = !found || found.locked || !found.editable;
    const id = `workspace-${key.replace(/\./g, "-")}`;
    return (
      <div className="field">
        <label htmlFor={id}>{t(labelKey)}</label>
        <input
          id={id}
          type="text"
          value={shown(key)}
          disabled={off}
          autoComplete="off"
          aria-describedby={hintKey ? `${id}-hint` : undefined}
          onChange={(e) => setEdits({ ...edits, [key]: e.target.value })}
        />
        {hintKey && (
          <p className="hint" id={`${id}-hint`}>
            {t(hintKey)}
          </p>
        )}
        {found?.locked && <p className="hint">{t(found.source === "env" ? "settings.locked_env" : "settings.locked_flag")}</p>}
      </div>
    );
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (pending && !empty) void save();
      }}
    >
      {field(NAME, "welcome.workspace.name", null)}
      <div className="field">
        <label htmlFor="workspace-full-name">{t("welcome.workspace.full_name")}</label>
        <input
          id="workspace-full-name"
          type="text"
          value={fullName}
          autoComplete="name"
          aria-describedby="workspace-full-name-hint"
          onChange={(e) => setNameEdit(e.target.value)}
        />
        <p className="hint" id="workspace-full-name-hint">
          {t("welcome.workspace.full_name_hint")}
        </p>
      </div>
      {field(TIMEZONE, "welcome.workspace.timezone", "welcome.workspace.timezone_hint")}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <div className="row-end">
        <button type="submit" className="btn primary" disabled={busy || empty || !pending}>
          {t("welcome.workspace.save")}
        </button>
      </div>
    </form>
  );
}

// ---- template ------------------------------------------------------------------------------------------------------

function TemplateStep() {
  const { t } = useWords();
  const act = useAct();
  const restart = useRestart();
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.templates });
  const [busy, setBusy] = useState(false);
  if (templates.isPending) return <p className="empty">{t("loading")}</p>;
  if (templates.isError || !templates.data.length) return <p className="empty">{t("welcome.template.none")}</p>;
  const apply = async (template: S["TemplateView"]) => {
    setBusy(true);
    const done = await act(
      () => api.applyTemplate(template.id),
      () => ({ message: t("welcome.template.applied", { name: template.name }) }),
    );
    setBusy(false);
    if (done?.needs_restart) restart.offer();
  };
  return (
    <ul className="queue">
      {templates.data.map((tpl) => {
        const adds = tpl.adds ?? [];
        const addsId = `template-${tpl.id.replace(/[^A-Za-z0-9_-]/g, "-")}-adds`;
        return (
          <li key={tpl.id} className="line">
            <div className="row pair">
              <div className="text">
                <strong>{tpl.name}</strong>
                {tpl.description && <span className="sub">{tpl.description}</span>}
                {adds.length > 0 && (
                  <div className="template-adds">
                    <span className="what" id={addsId}>
                      {t("welcome.template.adds")}
                    </span>
                    <ul className="plain-list" aria-labelledby={addsId}>
                      {adds.map((add) => (
                        <li key={add.name}>
                          <strong>{add.name}</strong>
                          {(add.fields.length > 0 || add.stages.length > 0) && (
                            <ul className="plain-list">
                              {add.fields.length > 0 && <li>{t("welcome.template.fields", { list: add.fields.join(", ") })}</li>}
                              {add.stages.length > 0 && (
                                <li>{t("welcome.template.steps", { list: add.stages.join(t("welcome.template.step_join")) })}</li>
                              )}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              <div className="acts">
                {tpl.set_up ? (
                  <span className="template-set-up">
                    <span aria-hidden="true">✓ </span>
                    {t("welcome.template.set_up")}
                  </span>
                ) : (
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    aria-label={t("welcome.template.apply_named", { name: tpl.name })}
                    onClick={() => void apply(tpl)}
                  >
                    {t("welcome.template.apply")}
                  </button>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
