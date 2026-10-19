// A person's form, in a drawer from the right so the list or screen it was opened from stays in view (design 7.14). It adds a
// person or edits one; both act at once with Undo. `onSaved` hears the new or edited person's id, so a picker can select who
// was just added without the person ever leaving the screen.
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useFirstField } from "../lib/focus";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Drawer } from "../ui/Drawer";
import { OrgSelect } from "./OrgSelect";

const list = (text: string) =>
  text
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

/** A labelled text box; the form fields of the records screens share this. */
export function Field(props: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
  type?: string;
  required?: boolean;
}) {
  return (
    <div className="field">
      <label htmlFor={props.id}>
        {props.label} {props.hint && <span className="hint">{props.hint}</span>}
      </label>
      <input
        id={props.id}
        type={props.type ?? "text"}
        value={props.value}
        required={props.required}
        autoComplete="off"
        onChange={(e) => props.onChange(e.target.value)}
      />
    </div>
  );
}

export function PersonDrawer(props: {
  person?: S["PersonView"];
  /** The name typed so far when the form opens from a picker, if any. */
  onClose: () => void;
  onSaved?: (id: string, name: string) => void;
}) {
  const { t } = useWords();
  const act = useAct();
  const p = props.person;
  const key = p?.id ?? "new";
  const [name, setName] = useState(p?.name ?? "");
  const [firstName, setFirstName] = useState(p?.first_name ?? "");
  const [role, setRole] = useState(p?.role ?? "");
  const [org, setOrg] = useState(p?.org ?? "");
  const [aliases, setAliases] = useState(p?.aliases.join(", ") ?? "");
  const [busy, setBusy] = useState(false);
  const first = useFirstField<HTMLFormElement>();
  const dirty =
    name !== (p?.name ?? "") ||
    firstName !== (p?.first_name ?? "") ||
    role !== (p?.role ?? "") ||
    org !== (p?.org ?? "") ||
    aliases !== (p?.aliases.join(", ") ?? "");
  const formId = `person-form-${key}`;

  const save = async () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    const body = {
      full_name: name.trim(),
      first_name: firstName.trim() || null,
      role: role.trim() || null,
      org: org || null,
      aliases: list(aliases),
    };
    const done = p
      ? await act(
          () => api.editPerson(p.id, body),
          () => ({
            message: t("toast.saved", { name: body.full_name }),
            undo: () =>
              api.editPerson(p.id, { full_name: p.name, first_name: p.first_name, role: p.role, org: p.org, aliases: p.aliases }),
          }),
        )
      : await act(
          () => api.addPerson(body),
          (created) => ({ message: t("toast.added", { name: body.full_name }), undo: () => api.removePerson(created.id) }),
        );
    setBusy(false);
    if (!done) return;
    props.onSaved?.(p?.id ?? (done as S["Created"]).id, body.full_name);
    props.onClose();
  };

  return (
    <Drawer
      open
      title={t(p ? "person.edit_title" : "person.add_title")}
      dirty={dirty}
      onClose={props.onClose}
      footer={
        <>
          <Button onClick={props.onClose}>{t("action.cancel")}</Button>
          <Button variant="primary" type="submit" form={formId} disabled={!name.trim() || busy} reason={t("setup.name_missing")}>
            {t(p ? "setup.save" : "setup.add_person")}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        ref={first}
        className="setup-form"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <Field id={`pn-${key}`} label={t("setup.full_name")} value={name} onChange={setName} required />
        <Field id={`pf-${key}`} label={t("setup.first_name")} value={firstName} onChange={setFirstName} hint={t("setup.first_name_hint")} />
        <Field id={`pr-${key}`} label={t("setup.role")} value={role} onChange={setRole} hint={t("setup.role_hint")} />
        <OrgSelect id={`po-${key}`} label={t("setup.org")} value={org} onChange={setOrg} hint={t("setup.org_hint")} />
        <Field id={`pa-${key}`} label={t("setup.aliases")} value={aliases} onChange={setAliases} hint={t("setup.aliases_hint")} />
      </form>
    </Drawer>
  );
}
