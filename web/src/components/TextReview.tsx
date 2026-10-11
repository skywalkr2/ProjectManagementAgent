// Reviewing a pending version of a long text, change by change: each change is accepted or the current text kept;
// where the text moved on after a copy went out, a passage both sides changed is marked as a conflict. The choices go
// back as one step, with Undo (design 7.2).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useId, useState } from "react";
import { Heading } from "react-aria-components";
import { ApiError, api, type S } from "../lib/api";
import { problemText } from "../lib/problem";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { ModalPanel, restoreFocus } from "./ModalPanel";
import { RowMenu } from "./RowMenu";
import { SafeText } from "./SafeText";

type Choice = "accept" | "reject";

interface Opened {
  version: string;
  opener: () => HTMLElement | null | undefined;
}

/** Open the review of a pending version from anywhere. Render `dialog` once; call `open` from a button. */
export function useTextReview() {
  const [opened, setOpened] = useState<Opened | null>(null);
  const open = useCallback((version: string, returnTo?: () => HTMLElement | null | undefined) => {
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setOpened({ version, opener: returnTo ?? (() => (active?.isConnected ? active : null)) });
  }, []);
  const close = useCallback(() => {
    setOpened((current) => {
      if (current) restoreFocus(current.opener);
      return null;
    });
  }, []);
  const dialog = opened ? <TextReview version={opened.version} onClose={close} /> : null;
  return { open, dialog };
}

export function TextReview(props: { version: string; onClose: () => void }) {
  const { t, tn } = useWords();
  const client = useQueryClient();
  const { push } = useToasts();
  const base = useId();
  const titleId = `${base}-title`;
  const review = useQuery({
    queryKey: ["text-review", props.version],
    queryFn: () => api.textReview(props.version),
    gcTime: 0,
    staleTime: 0,
  });
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; stale: boolean } | null>(null);

  const data = review.data;
  useEffect(() => {
    setChoices({});
  }, [data?.version.version]);

  const done = async (result: S["Applied"], message: string) => {
    await client.invalidateQueries();
    push({
      message,
      undo: async () => {
        const report = await api.undo(result.changeset);
        await client.invalidateQueries();
        if (!report.restored.length) throw new Error("not undone");
      },
    });
    props.onClose();
  };

  const submit = async (kind: "accept" | "discard") => {
    if (!data) return;
    setBusy(true);
    setError(null);
    const changes = data.regions.filter((r) => r.id);
    try {
      if (kind === "accept") {
        const picked = Object.fromEntries(changes.map((r) => [r.id, choices[r.id] ?? "accept"]));
        const result = await api.acceptText(props.version, { read_version: data.version.version, choices: picked });
        await done(result, t("text_review.applied"));
      } else {
        const result = await api.discardText(props.version, { read_version: data.version.version, choices: {} });
        await done(result, t("text_review.discarded"));
      }
    } catch (err) {
      setError({ text: problemText(err, t), stale: err instanceof ApiError && err.status === 409 });
      setBusy(false);
    }
  };

  const reload = () => {
    setError(null);
    setChoices({});
    void review.refetch();
  };

  const changes = data?.regions.filter((r) => r.id) ?? [];
  const kept = data?.regions.filter((r) => !r.id) ?? [];
  const questions = data?.version.questions ?? [];
  const unmapped = data?.version.unmapped ?? [];

  return (
    <ModalPanel titleId={titleId} onClose={props.onClose}>
      <Heading slot="title" id={titleId}>
        {t("text_review.title")}
      </Heading>
      {review.isPending && (
        <p className="hint" role="status">
          {t("text_review.loading")}
        </p>
      )}
      {review.isError && (
        <p className="problem-note" role="alert">
          {problemText(review.error, t)}{" "}
          <button type="button" className="btn" onClick={reload}>
            {t("action.try_again")}
          </button>
        </p>
      )}
      {error && (
        <div className="problem-note" role="alert">
          <p>{error.text}</p>
          {error.stale && (
            <p>
              {t("text_review.reload_hint")}{" "}
              <button type="button" className="btn" onClick={reload}>
                {t("text_review.reload")}
              </button>
            </p>
          )}
        </div>
      )}
      {data && (
        <div className="review-body review-wide">
          {data.version.note && (
            <div className="hint">
              <SafeText text={data.version.note} />
            </div>
          )}
          {questions.length > 0 && (
            <section aria-labelledby={`${base}-questions`}>
              <h3 id={`${base}-questions`} className="what">
                {t("text_review.questions")}
              </h3>
              <ul className="plain-list">
                {questions.map((q, i) => (
                  <li key={i}>
                    <SafeText text={q} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {unmapped.length > 0 && (
            <section aria-labelledby={`${base}-unmapped`}>
              <h3 id={`${base}-unmapped`} className="what">
                {t("text_review.unmapped")}
              </h3>
              <ul className="plain-list">
                {unmapped.map((u, i) => (
                  <li key={i}>
                    <SafeText text={u} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section aria-labelledby={`${base}-changes`}>
            <h3 id={`${base}-changes`} className="what">
              {t("text_review.changes")}
            </h3>
            {changes.length === 0 ? (
              <p className="hint">{t("text_review.no_changes")}</p>
            ) : (
              <p className="hint">{tn("text_review.count", changes.length)}</p>
            )}
            <div className="changes">
              {changes.map((region, i) => (
                <Change
                  key={region.id}
                  region={region}
                  number={i + 1}
                  total={changes.length}
                  threeWay={data.three_way}
                  value={choices[region.id] ?? "accept"}
                  onChange={(value) => setChoices((all) => ({ ...all, [region.id]: value }))}
                />
              ))}
            </div>
          </section>
          {kept.length > 0 && (
            <section aria-labelledby={`${base}-kept`}>
              <h3 id={`${base}-kept`} className="what">
                {t("text_review.kept")}
              </h3>
              <p className="hint">{t("text_review.kept_hint")}</p>
              <ul className="plain-list">
                {kept.map((region, i) => (
                  <li key={i}>
                    <SafeText text={region.current || region.pending || t("text_review.nothing")} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onClose}>
          {t("action.cancel")}
        </button>
        {data && (
          <RowMenu
            label={t("text_review.title")}
            actions={[{ id: "discard", label: t("text_review.discard"), run: () => void submit("discard") }]}
          />
        )}
        <button type="button" className="btn primary" disabled={!data || busy} onClick={() => void submit("accept")}>
          {t(busy ? "text_review.applying" : "text_review.apply")}
        </button>
      </div>
    </ModalPanel>
  );
}

function Passage(props: { label: string; text: string }) {
  const { t } = useWords();
  return (
    <div className="passage">
      <span className="what">{props.label}</span>
      {props.text.trim() ? <SafeText text={props.text} /> : <p className="hint">{t("text_review.nothing")}</p>}
    </div>
  );
}

function Change(props: {
  region: S["TextRegion"];
  number: number;
  total: number;
  threeWay: boolean;
  value: Choice;
  onChange: (value: Choice) => void;
}) {
  const { t } = useWords();
  const { region } = props;
  const name = useId();
  const conflict = region.side === "both";
  return (
    <fieldset className="change" data-conflict={conflict ? "true" : undefined}>
      <legend>
        {t("text_review.change_n", { n: props.number, total: props.total })}
        {conflict && (
          <span className="pill k-risk">
            <span aria-hidden="true">⚠ </span>
            {t("text_review.conflict")}
          </span>
        )}
      </legend>
      {conflict && <p className="hint">{t("text_review.conflict_hint")}</p>}
      {props.threeWay && <Passage label={t("text_review.original")} text={region.base} />}
      <Passage label={t("text_review.current")} text={region.current} />
      <Passage label={t("text_review.proposed")} text={region.pending} />
      <div className="choice-row" role="radiogroup" aria-label={t("text_review.choose", { n: props.number })}>
        {(["accept", "reject"] as const).map((value) => (
          <label key={value} className="check-line">
            <input
              type="radio"
              name={name}
              value={value}
              checked={props.value === value}
              onChange={() => props.onChange(value)}
            />
            <span>{t(value === "accept" ? "text_review.accept" : "text_review.keep")}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
