// Adding a file (design 5.3): pick the file, say what it's for, and answer the questions that kind of file asks. Size
// and type are checked here for a quick answer; the server's refusal is shown as it says it. Adding a file is not a
// change that can be undone, so there is no Undo toast.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useMemo, useState } from "react";
import { Heading } from "react-aria-components";
import { api, type S } from "../lib/api";
import { buildDetails, detailFields, initialValue, type DetailField, type FormValues } from "../lib/details-form";
import { useTypeWords } from "../lib/files";
import { problemText } from "../lib/problem";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { ModalPanel } from "./ModalPanel";

const DEFAULT_KIND = "attachment";

export function AddFile(props: { onClose: () => void }) {
  const { t } = useWords();
  const client = useQueryClient();
  const { push } = useToasts();
  const typeWords = useTypeWords();
  const base = useId();
  const kinds = useQuery({ queryKey: ["file-kinds"], queryFn: api.fileKinds });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [file, setFile] = useState<File | null>(null);
  const [kindName, setKindName] = useState("");
  const [project, setProject] = useState("");
  const [values, setValues] = useState<FormValues>({});
  const [problem, setProblem] = useState("");

  const kind: S["FileKindView"] | undefined =
    kinds.data?.find((k) => k.name === kindName) ?? kinds.data?.find((k) => k.name === DEFAULT_KIND) ?? kinds.data?.[0];
  const fields = useMemo(() => (kind ? detailFields(kind.details_schema) : []), [kind]);

  const tooBig = file && kind && file.size > kind.max_mb * 1024 * 1024;
  const wrongType = file && kind && file.type !== "" && !kind.accept.includes(file.type);
  const checked = tooBig
    ? t("addfile.too_big", { name: file.name, max: kind.max_mb })
    : wrongType
      ? t("addfile.wrong_type", { type: file.type })
      : "";
  const shown = checked || problem;

  const add = useMutation({
    mutationFn: async () => {
      if (!file || !kind || !fields) return;
      const built = buildDetails(fields, values);
      if ("missing" in built) {
        setProblem(t("addfile.need", { field: built.missing }));
        return;
      }
      setProblem("");
      try {
        const added = await api.uploadFile(file, { kind: kind.name, project: project || null, meta: built.meta });
        await client.invalidateQueries();
        push({ message: t("toast.added", { name: added.name }) });
        props.onClose();
      } catch (err) {
        setProblem(problemText(err, t));
      }
    },
  });

  const titleId = `${base}-title`;
  const ready = !!file && !!kind && fields !== null && !checked && !add.isPending;
  return (
    <ModalPanel titleId={titleId} onClose={props.onClose}>
      <Heading slot="title" id={titleId}>
        {t("addfile.title")}
      </Heading>
      {kinds.isPending ? (
        <p className="hint" role="status">
          {t("loading")}
        </p>
      ) : kinds.isError || !kind ? (
        <p className="problem-note" role="alert">
          {t("addfile.kinds_failed")}{" "}
          <button type="button" className="btn" onClick={() => void kinds.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : (
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) add.mutate();
          }}
        >
          <div className="field">
            <label htmlFor={`${base}-kind`}>{t("addfile.kind")}</label>
            <select
              id={`${base}-kind`}
              value={kind.name}
              aria-describedby={`${base}-kind-help`}
              onChange={(e) => {
                setKindName(e.target.value);
                setValues({});
                setProblem("");
              }}
            >
              {kinds.data.map((k) => (
                <option key={k.name} value={k.name}>
                  {k.label}
                </option>
              ))}
            </select>
            <span id={`${base}-kind-help`} className="hint">
              {t("addfile.accepts", { types: typeWords(kind.accept), max: kind.max_mb })}
            </span>
          </div>
          <div className="field">
            <label htmlFor={`${base}-file`}>{t("addfile.file")}</label>
            <input
              id={`${base}-file`}
              type="file"
              accept={kind.accept.join(",")}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setProblem("");
              }}
            />
          </div>
          <div className="field">
            <label htmlFor={`${base}-project`}>
              {t("addfile.project")} <span className="hint">{t("addfile.optional")}</span>
            </label>
            <select id={`${base}-project`} value={project} onChange={(e) => setProject(e.target.value)}>
              <option value="">{t("addfile.no_project")}</option>
              {(projects.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          {fields === null ? (
            <p className="hint">{t("addfile.unsupported")}</p>
          ) : (
            fields.length > 0 && (
              <fieldset className="details">
                <legend>{t("addfile.details")}</legend>
                {fields.map((f) => (
                  <DetailInput
                    key={`${kind.name}/${f.key}`}
                    field={f}
                    id={`${base}-d-${f.key}`}
                    value={values[f.key] ?? initialValue(f)}
                    onChange={(v) => {
                      setValues((all) => ({ ...all, [f.key]: v }));
                      setProblem("");
                    }}
                  />
                ))}
              </fieldset>
            )
          )}
          {shown && (
            <p className="problem-note" role="alert">
              {shown}
            </p>
          )}
          <div className="row-end">
            <button type="button" className="btn quiet" onClick={props.onClose}>
              {t("action.cancel")}
            </button>
            <button type="submit" className="btn primary" disabled={!ready}>
              {t(add.isPending ? "addfile.adding" : "addfile.go")}
            </button>
          </div>
        </form>
      )}
    </ModalPanel>
  );
}

function DetailInput(props: { field: DetailField; id: string; value: string | boolean; onChange: (v: string | boolean) => void }) {
  const { t } = useWords();
  const { field: f, id, value } = props;
  const help = f.help ? `${id}-help` : undefined;
  const hint = f.help && (
    <span id={help} className="hint">
      {f.help}
    </span>
  );
  if (f.type === "boolean") {
    return (
      <div className="field">
        <label className="check-line" htmlFor={id}>
          <input id={id} type="checkbox" checked={value === true} aria-describedby={help} onChange={(e) => props.onChange(e.target.checked)} />
          <span>{f.label}</span>
        </label>
        {hint}
      </div>
    );
  }
  const label = (
    <label htmlFor={id}>
      {f.label} {!f.required && <span className="hint">{t("addfile.optional")}</span>}
    </label>
  );
  if (f.type === "choice") {
    return (
      <div className="field">
        {label}
        <select id={id} value={String(value)} aria-describedby={help} required={f.required} onChange={(e) => props.onChange(e.target.value)}>
          {!f.required && <option value="">{t("addfile.not_chosen")}</option>}
          {f.choices.map((c) => (
            <option key={String(c.value)} value={String(c.value)}>
              {c.label}
            </option>
          ))}
        </select>
        {hint}
      </div>
    );
  }
  return (
    <div className="field">
      {label}
      {f.type === "text" ? (
        <input
          id={id}
          type="text"
          value={String(value)}
          maxLength={f.maxLength}
          minLength={f.minLength}
          required={f.required}
          aria-describedby={help}
          onChange={(e) => props.onChange(e.target.value)}
        />
      ) : (
        <input
          id={id}
          type="number"
          step={f.type === "integer" ? 1 : "any"}
          min={f.min}
          max={f.max}
          value={String(value)}
          required={f.required}
          aria-describedby={help}
          onChange={(e) => props.onChange(e.target.value)}
        />
      )}
      {hint}
    </div>
  );
}
