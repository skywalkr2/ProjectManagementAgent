// Organizations (design 5.1, 7.13): the companies and bodies people work for, a table with one row each, how many people work there
// and the other names it goes by. Adding
// and renaming happen in a drawer; removing acts at once with Undo, and an organization people still work for can't be removed.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useFirstField } from "../lib/focus";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Drawer } from "../ui/Drawer";
import { RecordsTable, type TableColumn } from "../ui/RecordsTable";
import { Skeleton } from "../ui/Skeleton";
import { Field } from "./PersonForm";
import { RowMenu, type MenuAction } from "./RowMenu";

export function Organizations() {
  const { t } = useWords();
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
  const columns: TableColumn<S["OrganizationView"]>[] = [
    { id: "people", header: t("orgs.col.people"), rank: 1, numeric: true, cell: (o) => (o.people > 0 ? o.people : "") },
    { id: "aliases", header: t("orgs.col.aliases"), rank: 2, cell: (o) => o.aliases.join(", ") },
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
        <RecordsTable
          label={t("setup.organizations")}
          name={{ header: t("orgs.col.name"), title: (o) => o.name, cell: (o) => o.name }}
          columns={columns}
          groups={[{ id: "all", title: t("setup.organizations"), rows }]}
          rowKey={(o) => o.id}
          actionsHeader={t("people.col.actions")}
          actions={(o) => <RowMenu label={o.name} actions={menu(o)} />}
        />
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
