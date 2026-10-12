// Add-on files: the data files an add-on lets the person edit through a form (its templates, lists, profiles). Each file
// comes from one of three places: with the add-on, the person's own copy, or a copy for one project. A save never
// touches the one that comes with the add-on; it writes the person's copy (or the chosen project's), with Undo, and
// removing a copy brings back the one underneath.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { problemText } from "../lib/problem";
import { projectChoices } from "../lib/project-choices";
import { addonLabel, changedValues, type Draft } from "../lib/settings";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { restoreFocus } from "./ModalPanel";
import { RowMenu, type MenuAction } from "./RowMenu";
import { ItemFields } from "./SettingRow";
import { Skeleton } from "../ui/Skeleton";
import { Icon } from "../ui/Icon";

type Form = S["DataFormView"];
type DataFile = S["DataFile"];

/** A file's name as the person types it: the ".yaml" is added, so a name with it is taken as it is. */
export function fileNameOf(typed: string): string {
  return typed.trim().replace(/\.yaml$/i, "");
}

const VALID_NAME = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export function DataForms() {
  const { t } = useWords();
  const forms = useQuery({ queryKey: ["data-forms"], queryFn: api.dataForms });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [project, setProject] = useState("");
  const base = useId();
  // Nothing to show until some add-on offers a form.
  if (!forms.data || forms.data.length === 0) return null;
  const choices = projectChoices(projects.data ?? [], (parent, name) => t("handin.project.path", { parent, name }));
  return (
    <section className="panel-section" aria-labelledby={`${base}-title`}>
      <div className="heading">
        <h3 id={`${base}-title`}>{t("dataform.title")}</h3>
      </div>
      <p className="hint">{t("dataform.intro")}</p>
      {choices.length > 0 && (
        <div className="field">
          <label htmlFor={`${base}-project`}>{t("dataform.project")}</label>
          <select id={`${base}-project`} value={project} onChange={(e) => setProject(e.target.value)} aria-describedby={`${base}-project-hint`}>
            <option value="">{t("dataform.no_project")}</option>
            {choices.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
          <p className="hint" id={`${base}-project-hint`}>
            {t("dataform.project_hint")}
          </p>
        </div>
      )}
      {forms.data.map((form) => (
        <FormFiles key={`${form.name}:${project}`} form={form} project={project} />
      ))}
    </section>
  );
}

function FormFiles(props: { form: Form; project: string }) {
  const { t, has } = useWords();
  const { form, project } = props;
  const base = useId();
  const files = useQuery({
    queryKey: ["data-forms", form.name, "files", project],
    queryFn: () => api.dataFiles(form.name, project || undefined),
  });
  // The file being edited, and whether it is a new one; and whether the name of a new one is being asked for.
  const [editor, setEditor] = useState<{ file: string; isNew: boolean } | null>(null);
  const [naming, setNaming] = useState(false);
  const newButton = `${base}-new`;
  const titleId = `${base}-title`;
  const names = (files.data ?? []).map((f) => f.file);

  return (
    <section className="data-forms-kind" aria-labelledby={titleId}>
      <h4 id={titleId}>{t("dataform.form_title", { addon: addonLabel(form.plugin, t, has), label: form.label })}</h4>
      {form.description && <p className="hint">{form.description}</p>}
      {files.isPending ? (
        <Skeleton />
      ) : files.isError ? (
        <p className="empty">
          {t("dataform.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void files.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : files.data.length === 0 ? (
        <p className="empty">{t("dataform.none")}</p>
      ) : (
        <ul className="queue">
          {files.data.map((file) => (
            <FileRow
              key={file.file}
              form={form}
              file={file}
              project={project}
              editing={editor?.file === file.file && !editor.isNew}
              onOpen={() => setEditor({ file: file.file, isNew: false })}
              onClose={() => setEditor(null)}
            />
          ))}
        </ul>
      )}
      {editor?.isNew && (
        <FileEditor
          form={form}
          file={editor.file}
          project={project}
          isNew
          onClose={() => {
            setEditor(null);
            restoreFocus(() => document.getElementById(newButton));
          }}
        />
      )}
      {naming && (
        <NewFileName
          taken={names}
          onCancel={() => {
            setNaming(false);
            restoreFocus(() => document.getElementById(newButton));
          }}
          onStart={(file) => {
            setNaming(false);
            setEditor({ file, isNew: true });
          }}
        />
      )}
      <div className="row-end">
        <button
          type="button"
          id={newButton}
          className="btn"
          aria-expanded={naming}
          aria-label={t("dataform.new_named", { label: form.label })}
          onClick={() => setNaming(true)}
        >
          {t("dataform.new")}
        </button>
      </div>
    </section>
  );
}

function FileRow(props: { form: Form; file: DataFile; project: string; editing: boolean; onOpen: () => void; onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const { form, file, project } = props;
  const titleId = `data-file-${form.name.replace(/[^A-Za-z0-9_-]/g, "-")}-${file.file.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  const openId = `${titleId}-open`;

  const remove = (layer: "workspace" | "project") =>
    void act(
      () => api.removeDataFile(form.name, { file: file.file, layer, project: layer === "project" ? project : null }),
      (done) => ({
        message: t(layer === "project" ? "dataform.removed_project_toast" : "dataform.removed_toast", { file: file.file }),
        undo: () =>
          api.restoreDataFile(form.name, {
            file: file.file,
            layer,
            project: layer === "project" ? project : null,
            before: done.before,
          }),
      }),
    );

  const actions: MenuAction[] = [];
  if (project && file.layers.includes("project")) {
    actions.push({ id: "remove-project", label: t("dataform.remove_project"), run: () => remove("project") });
  }
  if (file.layers.includes("workspace")) {
    actions.push({ id: "remove", label: t("dataform.remove"), run: () => remove("workspace") });
  }

  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={titleId}>
      <div className="row pair">
        <div className="text">
          <strong id={titleId}>{file.file}</strong>
          {file.layer && <span className="sub">{t(`dataform.layer.${file.layer}`)}</span>}
          {file.problem && (
            <p className="problem-note">
              <Icon name="alert" size={16} />
              {t("dataform.problem", { problem: file.problem })}
            </p>
          )}
        </div>
        <div className="acts">
          <button
            type="button"
            id={openId}
            className="btn primary"
            data-key="primary"
            aria-expanded={props.editing}
            aria-label={t("dataform.open_named", { file: file.file })}
            onClick={props.onOpen}
          >
            {t("dataform.open")}
          </button>
          <RowMenu label={file.file} actions={actions} />
        </div>
      </div>
      {props.editing && (
        <FileEditor
          form={form}
          file={file.file}
          project={project}
          isNew={false}
          onClose={() => {
            props.onClose();
            restoreFocus(() => document.getElementById(openId));
          }}
        />
      )}
    </li>
  );
}

/** Asks for the name of a new file: lowercase letters, digits, - or _, with ".yaml" added. */
function NewFileName(props: { taken: string[]; onCancel: () => void; onStart: (file: string) => void }) {
  const { t } = useWords();
  const base = useId();
  const input = useRef<HTMLInputElement>(null);
  const [typed, setTyped] = useState("");
  useEffect(() => input.current?.focus(), []);
  const name = fileNameOf(typed);
  const file = `${name}.yaml`;
  const problem = !typed.trim() ? "" : !VALID_NAME.test(name) ? t("dataform.name_bad") : props.taken.includes(file) ? t("dataform.name_taken", { file }) : "";
  const ready = typed.trim() !== "" && problem === "";
  return (
    <form
      className="panel"
      aria-label={t("dataform.new_form")}
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) props.onStart(file);
      }}
    >
      <div className="field">
        <label htmlFor={`${base}-name`}>{t("dataform.name")}</label>
        <input
          id={`${base}-name`}
          ref={input}
          type="text"
          value={typed}
          autoComplete="off"
          spellCheck={false}
          aria-invalid={problem ? true : undefined}
          aria-describedby={`${base}-hint${problem ? ` ${base}-bad` : ""}`}
          onChange={(e) => setTyped(e.target.value)}
        />
        <p className="hint" id={`${base}-hint`}>
          {t("dataform.name_hint")}
        </p>
        {problem && (
          <p className="problem-note" id={`${base}-bad`}>
            {problem}
          </p>
        )}
      </div>
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onCancel}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!ready}>
          {t("dataform.start")}
        </button>
      </div>
    </form>
  );
}

/** One file as a form. Saving writes the person's copy, or the chosen project's; a new file starts from the defaults. */
function FileEditor(props: { form: Form; file: string; project: string; isNew: boolean; onClose: () => void }) {
  const { t } = useWords();
  const client = useQueryClient();
  const { push } = useToasts();
  const { form, file, project, isNew } = props;
  const base = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const view = useQuery({
    queryKey: ["data-forms", form.name, "file", file, project],
    queryFn: () => api.dataFile(form.name, file, project || undefined),
    // A form is read fresh each time it is opened, so it shows what is on disk now.
    staleTime: 0,
    gcTime: 0,
  });
  const [edits, setEdits] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const loaded = !!view.data;
  useEffect(() => {
    if (!loaded) return;
    heading.current?.focus();
    heading.current?.scrollIntoView?.({ block: "nearest" });
  }, [loaded]);

  const items = view.data?.items ?? [];
  const { changes, bad } = changedValues(items, edits);
  const layer = project ? "project" : "workspace";
  const canSave = loaded && !busy && bad.length === 0 && (isNew || !!view.data?.problem || Object.keys(changes).length > 0);

  const save = async () => {
    if (!canSave) return;
    setBusy(true);
    setProblem("");
    try {
      const saved = await api.saveDataFile(form.name, { file, layer, project: project || null, changes });
      await client.invalidateQueries();
      push({
        message: t(project ? "dataform.saved_project_toast" : "dataform.saved_toast", { file }),
        undo: async () => {
          await api.restoreDataFile(form.name, { file, layer, project: project || null, before: saved.before });
          await client.invalidateQueries();
        },
      });
      props.onClose();
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      setBusy(false);
    }
  };

  const titleId = `${base}-title`;
  return (
    <form
      className="panel data-file-form"
      aria-labelledby={titleId}
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <h5 id={titleId} tabIndex={-1} ref={heading}>
        {t(isNew ? "dataform.new_title" : "dataform.editing", { file })}
      </h5>
      <p className="hint">{t(project ? "dataform.saves_project" : "dataform.saves_workspace")}</p>
      {view.isPending ? (
        <p className="hint">{t("loading")}</p>
      ) : view.isError ? (
        <p className="problem-note">{t("dataform.load_failed")}</p>
      ) : (
        <>
          {view.data.problem && (
            <p className="problem-note">
              <Icon name="alert" size={16} />
              {t("dataform.problem_form", { problem: view.data.problem })}
            </p>
          )}
          <ItemFields items={items} edits={edits} onEdit={(key, draft) => setEdits((all) => ({ ...all, [key]: draft }))} disabled={busy} idPrefix={`${base}-`} />
        </>
      )}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onClose}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!canSave} aria-label={t("dataform.save_named", { file })}>
          {t(busy ? "sources.saving" : "settings.save")}
        </button>
      </div>
    </form>
  );
}
