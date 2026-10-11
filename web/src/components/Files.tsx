// Files (design 5.3): what has been added, one row each, with Open as the row's one primary action. Plugins' actions
// for a file are in its menu; actions for the whole workspace are buttons above the list.
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { day } from "../lib/dates";
import { useSize } from "../lib/files";
import { usePluginActions } from "../lib/plugin-actions";
import { useWords } from "../lib/wording";
import { useActionReview } from "./ActionReview";
import { AddFile } from "./AddFile";
import { restoreFocus } from "./ModalPanel";
import { RowMenu, type MenuAction } from "./RowMenu";

export function Files() {
  const { t } = useWords();
  const files = useQuery({ queryKey: ["files"], queryFn: api.files });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const workspace = usePluginActions();
  const { start, review } = useActionReview();
  const [adding, setAdding] = useState(false);
  const addButton = useRef<HTMLButtonElement>(null);
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));

  return (
    <section className="panel-section" aria-labelledby="files-title">
      <div className="heading">
        <h2 id="files-title">{t("files.title")}</h2>
        <div className="acts wrap" role="group" aria-label={t("files.actions_label")}>
          {(workspace.data ?? []).map((action) => (
            <button
              key={action.name}
              type="button"
              className="btn"
              onClick={(e) => {
                const button = e.currentTarget;
                start(action, null, () => button);
              }}
            >
              {action.label}
            </button>
          ))}
          <button ref={addButton} type="button" className="btn primary" onClick={() => setAdding(true)}>
            {t("files.add")}
          </button>
        </div>
      </div>
      {files.isPending ? (
        <p className="empty">{t("loading")}</p>
      ) : files.isError ? (
        <p className="empty">
          {t("files.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void files.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : files.data.length === 0 ? (
        <p className="empty">{t("files.empty")}</p>
      ) : (
        <ul className="queue">
          {files.data.map((file) => (
            <FileRow key={file.id} file={file} project={file.project ? names.get(file.project) : undefined} />
          ))}
        </ul>
      )}
      {adding && (
        <AddFile
          onClose={() => {
            setAdding(false);
            restoreFocus(() => addButton.current);
          }}
        />
      )}
      {review}
    </section>
  );
}

function FileRow(props: { file: S["FileView"]; project?: string }) {
  const { t } = useWords();
  const size = useSize();
  const { file } = props;
  const ref = useRef<HTMLLIElement>(null);
  const actions = usePluginActions("file", file.id);
  const { start, review } = useActionReview();
  const titleId = `file-${file.id}`;
  const menu: MenuAction[] = (actions.data ?? []).map((action) => ({
    id: action.name,
    label: action.label,
    run: () => start(action, { kind: "file", id: file.id }, () => ref.current?.querySelector<HTMLElement>("button.more")),
  }));
  const facts = [
    size(file.size),
    ...(props.project ? [t("files.in_project", { project: props.project })] : []),
    t("files.added_on", { when: day(file.added_at) }),
  ];
  return (
    <li className="line" data-row tabIndex={-1} ref={ref} aria-labelledby={titleId}>
      <div className="row">
        <span className="kind k-review">{file.kind_label}</span>
        <div className="text">
          <div id={titleId} className="name">
            {file.name}
          </div>
          <span className="sub">{facts.join(" · ")}</span>
          {file.origin === "tool" && <span className="pill k-held untrusted">{t("files.untrusted")}</span>}
        </div>
        <div className="acts">
          <a
            className="btn primary"
            data-key="primary"
            href={api.fileContent(file.id)}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t("files.open_named", { name: file.name })}
          >
            {t("files.open")}
          </a>
          <RowMenu label={file.name} actions={menu} />
        </div>
      </div>
      {review}
    </li>
  );
}

