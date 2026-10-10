// The first-run card on Today (design 7.7): three steps for a workspace nothing has been handed in to yet, each
// saying in words whether it is done. It can be hidden; that is remembered in this browser only.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { useWords } from "../lib/wording";

const KEY = "start-here-hidden";

function hidden(workspace: string): boolean {
  try {
    return window.localStorage.getItem(`${KEY}:${workspace}`) === "1";
  } catch {
    return false;
  }
}

function remember(workspace: string) {
  try {
    window.localStorage.setItem(`${KEY}:${workspace}`, "1");
  } catch {
    // Storage can be blocked; the card then comes back next time, which is harmless.
  }
}

export function StartHere(props: { workspace: string; onHandIn: () => void; onOpenSetup: () => void }) {
  const { t } = useWords();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const changes = useQuery({ queryKey: ["changes"], queryFn: api.changes });
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [gone, setGone] = useState(() => hidden(props.workspace));
  if (gone || !status.data || !changes.data || !people.data) return null;
  // Stage tasks and scheduled work have neither a note nor a source; only something the PM handed in does.
  if (changes.data.some((c) => c.note || c.source)) return null;

  const steps = [
    { id: "ai", done: status.data.ai.state === "ok", label: t("start.step_ai"), action: null },
    {
      id: "people",
      done: people.data.length > 1,
      label: t("start.step_people"),
      action: (
        <button type="button" className="btn" onClick={props.onOpenSetup}>
          {t("start.people_link")}
        </button>
      ),
    },
    {
      id: "handin",
      done: false,
      label: t("start.step_handin"),
      action: (
        <button type="button" className="btn primary" onClick={props.onHandIn}>
          {t("handin.open")}
        </button>
      ),
    },
  ];
  return (
    <section className="panel start" aria-labelledby="start-title">
      <div className="heading">
        <h2 id="start-title">{t("start.title")}</h2>
        <button
          type="button"
          className="btn quiet"
          onClick={() => {
            remember(props.workspace);
            setGone(true);
          }}
        >
          {t("start.dismiss")}
        </button>
      </div>
      <p className="hint">{t("start.intro")}</p>
      <ol className="steps">
        {steps.map((step) => (
          <li key={step.id} data-step={step.id} data-done={step.done}>
            <span className={`pill ${step.done ? "k-done" : "k-wait"}`}>
              <span aria-hidden="true">{step.done ? "✓ " : "○ "}</span>
              {t(step.done ? "start.done" : "start.not_done")}
            </span>
            <span className="step-label">{step.label}</span>
            {step.action}
          </li>
        ))}
      </ol>
    </section>
  );
}
