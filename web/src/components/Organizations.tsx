// Organizations (design 5.1): the companies and bodies people work for, one row each with how many people work there. Adding
// and renaming happen in a drawer; removing acts at once with Undo, and an organization people still work for can't be removed.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useFirstField } from "../lib/focus";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Drawer } from "../ui/Drawer";
import { Skeleton } from "../ui/Skeleton";
import { Field } from "./PersonForm";
import { RowMenu, type MenuAction } from "./RowMenu";

export function Organizations() {
  const { t, tn } = useWords();
  const act = useAct();
  const orgs = useQuery({ queryKey: ["organizations"], queryFn: api.organizations });
  const [adding, setAdding] = useState(false);
  const [renaming, setRenaming] = useState<S["OrganizationView"] | null>(null);
  const rows = [...(orgs.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  const menu = (o: S["OrganizationView"]): MenuAction[] => [
    { id: "rename", label: t("setup.rename"), run: () => setRenaming(o) },
    {
      id: "remove",
      label: t("setup.remove"),
      disabled: o.people > 0,
      reason: t("setup.org_remove_blocked"),
      run: () =>
        void act(
          () => api.removeOrganization(o.id),
          () => ({ message: t("toast.removed", { name: o.name }), undo: () => api.restoreOrganization(o.id) }),
        ),
    },
  ];
  return (
    <section className="panel-section" aria-labelledby="organizations-title">
      <div className="heading">
        <h2 id="organizations-title">{t("setup.organizations")}</h2>
        <Button variant="primary" onClick={() => setAdding(true)}>
          {t("setup.add_organization")}
        </Button>
      </div>
      {orgs.isPending ? (
        <Skeleton />
      ) : rows.length === 0 ? (
        <p className="empty">{t("setup.no_organizations")}</p>
      ) : (
        <ul className="queue">
          {rows.map((o) => {
            const sub = [o.people > 0 ? tn("setup.org_people", o.people) : "", o.aliases.length ? t("setup.also_called", { names: o.aliases.join(", ") }) : ""]
              .filter(Boolean)
              .join(" · ");
            return (
              <li className="line" key={o.id}>
                <div className="row">
                  <div className="text">
                    <strong>{o.name}</strong>
                    <span className="sub">{sub}</span>
                  </div>
                  <div className="acts">
                    <RowMenu label={o.name} actions={menu(o)} />
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {adding && <OrganizationDrawer onClose={() => setAdding(false)} />}
      {renaming && <OrganizationDrawer org={renaming} onClose={() => setRenaming(null)} />}
    </section>
  );
}

function OrganizationDrawer(props: { org?: S["OrganizationView"]; onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const o = props.org;
  const [name, setName] = useState(o?.name ?? "");
  const [busy, setBusy] = useState(false);
  const first = useFirstField<HTMLFormElement>();
  const formId = `organization-form-${o?.id ?? "new"}`;
  const save = async () => {
    const wanted = name.trim();
    if (!wanted || busy) return;
    if (o && wanted === o.name) return props.onClose();
    setBusy(true);
    const done = o
      ? await act(
          () => api.editOrganization(o.id, { name: wanted }),
          () => ({ message: t("toast.renamed", { name: wanted }), undo: () => api.editOrganization(o.id, { name: o.name }) }),
        )
      : await act(
          () => api.addOrganization({ name: wanted }),
          (created) => ({ message: t("toast.added", { name: wanted }), undo: () => api.removeOrganization(created.id) }),
        );
    setBusy(false);
    if (done) props.onClose();
  };
  return (
    <Drawer
      open
      title={t(o ? "organization.rename_title" : "organization.add_title")}
      dirty={name !== (o?.name ?? "")}
      onClose={props.onClose}
      footer={
        <>
          <Button onClick={props.onClose}>{t("action.cancel")}</Button>
          <Button variant="primary" type="submit" form={formId} disabled={!name.trim() || busy} reason={t("setup.name_missing")}>
            {t(o ? "setup.save" : "setup.add_organization")}
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
        <Field id={`org-${o?.id ?? "new"}`} label={t("setup.organization_name")} value={name} onChange={setName} required />
      </form>
    </Drawer>
  );
}
