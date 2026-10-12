// Today's one line for the first go (design 7.8): every run waiting for it, counted, with their total estimate and one
// Go that starts them all. It is a row of the Needs you list, so it keeps that list's keys and shape.
import { useRef } from "react";
import { api } from "../lib/api";
import { useFirstGoText, type FirstGo } from "../lib/first-go";
import { useRowKeys } from "../lib/keys";
import { useRowAction } from "../lib/stages";
import { useWords } from "../lib/wording";

export function FirstGoRow(props: { first: FirstGo }) {
  const { t } = useWords();
  const text = useFirstGoText();
  const { error, busy, run } = useRowAction();
  const ref = useRef<HTMLLIElement>(null);
  const go = () => void run(api.firstGo, () => ({ message: t("toast.go") }));
  useRowKeys(ref, { primary: go });
  return (
    <li className="line first-go" data-row tabIndex={-1} ref={ref} aria-labelledby="first-go-text">
      <div className="row pair">
        <div className="text">
          <span className="kind k-held">{t("changes.state.cost_go")}</span>
          <div id="first-go-text" className="name">
            {text(props.first)}
          </div>
          <span className="sub">{t("first_go.sub")}</span>
        </div>
        <div className="acts">
          <button type="button" className="btn primary" disabled={busy} aria-describedby="first-go-text" onClick={go}>
            {t("changes.go")}
          </button>
        </div>
      </div>
      {error && (
        <div className="body">
          <p className="problem-note" role="alert">
            {error}
          </p>
        </div>
      )}
    </li>
  );
}
