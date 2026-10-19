// Choosing a project, by name, ending with "Add a project…": the form opens in a drawer and the project it adds is the one
// picked, so nobody leaves the screen to file something under a project that does not exist yet (open promise P14).
import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { api } from "../lib/api";
import { useWords } from "../lib/wording";
import { restoreFocus } from "./ModalPanel";
import { ProjectDrawer } from "./ProjectForm";

/** The choice that opens the add form; no project id can look like it. */
const ADD = "\u0001add";

export function ProjectPicker(props: {
  label: string;
  value: string;
  onChange: (project: string) => void;
  /** The text of the empty choice, which says nothing is picked yet. */
  empty?: string;
  required?: boolean;
  id?: string;
  describedBy?: string;
  autoFocus?: boolean;
}) {
  const { t } = useWords();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const own = useId();
  const id = props.id ?? own;
  const select = useRef<HTMLSelectElement>(null);
  const [adding, setAdding] = useState(false);
  const rows = [...(projects.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  const close = () => {
    setAdding(false);
    restoreFocus(() => select.current);
  };
  return (
    <div className="field">
      <label htmlFor={id}>{props.label}</label>
      <select
        id={id}
        ref={select}
        value={props.value}
        required={props.required}
        autoFocus={props.autoFocus}
        aria-describedby={props.describedBy}
        onChange={(e) => (e.target.value === ADD ? setAdding(true) : props.onChange(e.target.value))}
      >
        <option value="">{props.empty ?? t("project.choose")}</option>
        {rows.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
        <option value={ADD}>{t("project.add_option")}</option>
      </select>
      {adding && <ProjectDrawer onClose={close} onSaved={(projectId) => props.onChange(projectId)} />}
    </div>
  );
}
