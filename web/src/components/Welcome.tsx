// The setup guide (design 7.8): one section per step, in the order the server gives, each saying in words whether it is
// done or skipped, with its own controls and a way to skip it or come back to it. The core's steps have fixed controls;
// a plugin's step shows its own words and starts its action.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { problemText } from "../lib/problem";
import { useRestart } from "../lib/restart";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { useActionReview } from "./ActionReview";
import { WelcomeAi } from "./WelcomeAi";
import { WelcomeBackup } from "./WelcomeBackup";

type Step = S["SetupStepView"];

/** The id of a step's section, so Today can open the guide at one step. */
export const stepSlug = (id: string) => `guide-${id.replace(/[^a-z0-9]+/gi, "-")}`;

export interface FocusStep {
  id: string;
  n: number;
}

export function Welcome(props: { focusStep: FocusStep | null; onOpenPeople: () => void; onHandIn: () => void }) {
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
            const label = step.label || (has(`setup_step.${step.id}`) ? t(`setup_step.${step.id}`) : step.id);
            const why = step.explanation || (has(`setup_step.${step.id}.explanation`) ? t(`setup_step.${step.id}.explanation`) : "");
            return (
              <StepSection key={step.id} step={step} label={label} explanation={why}>
                {step.id === "workspace" ? (
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
                ) : step.id === "first_note" ? (
                  <div className="row-end">
                    <button type="button" className="btn" onClick={props.onHandIn}>
                      {t("handin.open")}
                    </button>
                  </div>
                ) : step.action ? (
                  <div className="row-end">
                    <button
                      type="button"
                      className="btn"
                      onClick={() => start({ name: step.action!, label, on: null }, null)}
                    >
                      {label}
                    </button>
                  </div>
                ) : null}
              </StepSection>
            );
          })}
        </ol>
      )}
      {review}
    </section>
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
const FULL_NAME = "workspace.user.full_name";
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
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  if (!settings.data) return <p className="empty">{t(settings.isError ? "welcome.failed" : "loading")}</p>;

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
  for (const key of [NAME, FULL_NAME, TIMEZONE]) {
    const found = item(key);
    if (found && found.editable && !found.locked && shown(key).trim() !== stored(key)) changes[key] = shown(key).trim();
  }
  const empty = Object.values(changes).some((v) => v === "");

  const save = async () => {
    setBusy(true);
    setProblem("");
    try {
      const saved = await api.saveSettings({ changes, reset: [], fingerprint: settings.data!.fingerprint });
      setEdits({});
      await afterSave(saved);
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
        if (Object.keys(changes).length && !empty) void save();
      }}
    >
      {field(NAME, "welcome.workspace.name", null)}
      {field(FULL_NAME, "welcome.workspace.full_name", "welcome.workspace.full_name_hint")}
      {field(TIMEZONE, "welcome.workspace.timezone", "welcome.workspace.timezone_hint")}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <div className="row-end">
        <button type="submit" className="btn primary" disabled={busy || empty || Object.keys(changes).length === 0}>
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
    if (done?.restarts) restart.begin();
  };
  return (
    <ul className="queue">
      {templates.data.map((tpl) => (
        <li key={tpl.id} className="line">
          <div className="row pair">
            <div className="text">
              <strong>{tpl.name}</strong>
              {tpl.description && <span className="sub">{tpl.description}</span>}
            </div>
            <div className="acts">
              <button
                type="button"
                className="btn"
                disabled={busy}
                aria-label={t("welcome.template.apply_named", { name: tpl.name })}
                onClick={() => void apply(tpl)}
              >
                {t("welcome.template.apply")}
              </button>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
