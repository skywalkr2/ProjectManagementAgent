// The first-run card on Today (design 7.7, 7.8): the setup steps still to do, each saying in words that it is not done
// and opening the setup guide at that step. It goes away when every step is done or skipped, and it can be hidden;
// that is remembered in this browser only.
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

export function StartHere(props: { workspace: string; onOpenGuide: (step: string) => void }) {
  const { t, has } = useWords();
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  const [gone, setGone] = useState(() => hidden(props.workspace));
  if (gone || !setup.data || setup.data.finished) return null;

  const todo = setup.data.steps.filter((s) => !s.done && !s.skipped);
  if (!todo.length) return null;
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
        {todo.map((step) => {
          const label = step.label || (has(`setup_step.${step.id}`) ? t(`setup_step.${step.id}`) : step.id);
          return (
            <li key={step.id} data-step={step.id} data-done="false">
              <span className="pill k-wait">
                <span aria-hidden="true">○ </span>
                {t("start.not_done")}
              </span>
              <span className="step-label">{label}</span>
              <button
                type="button"
                className="btn"
                aria-label={t("start.open_step_named", { label })}
                onClick={() => props.onOpenGuide(step.id)}
              >
                {t("start.open_step")}
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
