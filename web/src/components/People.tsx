// People (design 7.13, 7.14): everyone the workspace works with, as a table. A row, Enter on it or its name opens the detail
// pane beside the table (over it when the priority columns would not fit, a drawer on a narrower window); the name's link is
// the person's page for a new tab. Adding and editing happen in a drawer, so the table
// stays in view and the new row appears beside the form. Organizations are kept here too, since a person works for one.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { viewHref, recordView } from "../lib/views";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { ListDetail } from "../ui/ListDetail";
import { Pill } from "../ui/Pill";
import { RecordsTable, type TableColumn } from "../ui/RecordsTable";
import { Skeleton } from "../ui/Skeleton";
import { Organizations } from "./Organizations";
import styles from "./People.module.css";
import { PersonDrawer } from "./PersonForm";
import { RowMenu, type MenuAction } from "./RowMenu";

/** The organization filter's choices besides one on file: everyone, and people with none. */
const ALL = "";
const NONE = "\u0001none";

/** The width the priority columns (name, role, organization, open items and the menu) need beside the pane. */
const PEOPLE_FIT = 600;

export function People() {
  const { t, tn } = useWords();
  const act = useAct();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const orgs = useQuery({ queryKey: ["organizations"], queryFn: api.organizations });
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<S["PersonView"] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [org, setOrg] = useState(ALL);
  const all = [...(people.data ?? [])].sort((a, b) => (a.is_pm === b.is_pm ? a.name.localeCompare(b.name) : a.is_pm ? -1 : 1));
  const rows = all.filter((p) => org === ALL || (org === NONE ? !p.org : p.org === org));
  const selected = all.find((p) => p.id === chosen) ?? null;

  const menu = (p: S["PersonView"]): MenuAction[] => {
    const left = p.status === "left";
    const entries: MenuAction[] = [{ id: "edit", label: t("setup.edit"), run: () => setEditing(p) }];
    if (!p.is_pm) {
      entries.push({
        id: "left",
        label: t(left ? "setup.mark_active" : "setup.mark_left"),
        run: () =>
          void act(
            () => api.editPerson(p.id, { status: left ? "active" : "left" }),
            () => ({
              message: t(left ? "toast.marked_active" : "toast.marked_left", { name: p.name }),
              undo: () => api.editPerson(p.id, { status: p.status }),
            }),
          ),
      });
      entries.push({
        id: "remove",
        label: t("setup.remove"),
        run: () =>
          void act(
            () => api.removePerson(p.id),
            () => ({ message: t("toast.removed", { name: p.name }), undo: () => api.restorePerson(p.id) }),
          ),
      });
    }
    return entries;
  };

  const tags = (p: S["PersonView"]) => (
    <>
      {p.is_pm && <Pill tone="neutral">{t("setup.you")}</Pill>}
      {p.status === "left" && <Pill tone="neutral">{t("setup.left")}</Pill>}
      {p.track_only && <Pill tone="neutral">{t("people.watching")}</Pill>}
    </>
  );
  const reach = (p: S["PersonView"]) => Object.entries(p.how_to_reach ?? {}).map(([kind, value]) => `${kind}: ${value}`);
  const columns: TableColumn<S["PersonView"]>[] = [
    { id: "role", header: t("people.col.role"), rank: 1, core: true, cell: (p) => p.role ?? "" },
    { id: "org", header: t("people.col.org"), rank: 2, core: true, cell: (p) => p.org_name ?? "" },
    { id: "reach", header: t("people.col.reach"), rank: 3, cell: (p) => reach(p).map((line) => (
        <div key={line} title={line} className={styles.clip}>
          {line}
        </div>
      )) },
    { id: "open", header: t("people.col.open"), rank: 1, core: true, numeric: true, cell: (p) => (p.open_items > 0 ? p.open_items : "") },
    { id: "last", header: t("people.col.last"), rank: 2, cell: (p) => (p.last_contact ? day(p.last_contact) : "") },
  ];
  const filter = (
    <div className={["field", styles.orgFilter].join(" ")} data-size="content">
      <label htmlFor="people-org">{t("people.filter_org")}</label>
      <select id="people-org" value={org} onChange={(e) => setOrg(e.target.value)}>
        <option value={ALL}>{t("people.all_orgs")}</option>
        {(orgs.data ?? []).map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
        <option value={NONE}>{t("people.no_org")}</option>
      </select>
    </div>
  );

  return (
    <section className="panel-section" aria-labelledby="people-title">
      <div className="heading">
        <h1 id="people-title">{t("setup.people")}</h1>
        <Button variant="primary" onClick={() => setAdding(true)}>
          {t("setup.add_person")}
        </Button>
      </div>
      <ListDetail
        title={selected?.name ?? ""}
        onClose={() => setChosen(null)}
        fit={PEOPLE_FIT}
        detail={selected ? <PersonDetail person={selected} tags={tags(selected)} reach={reach(selected)} onEdit={() => setEditing(selected)} menu={menu(selected)} /> : null}
      >
        {people.isPending ? (
          <Skeleton />
        ) : all.length === 0 ? (
          <EmptyState text={t("setup.no_people")} action={{ label: t("setup.add_person"), onClick: () => setAdding(true) }} />
        ) : (
          <>
            {(orgs.data ?? []).length > 0 && filter}
            {rows.length === 0 ? (
              <p className="empty">{t("people.none_here")}</p>
            ) : (
              <RecordsTable
                label={t("setup.people")}
                name={{
                  header: t("people.col.name"),
                  cell: (p, open) => (
                    <>
                      <a href={viewHref(recordView("person", p.id))} onClick={open}>
                        {p.name}
                      </a>{" "}
                      {tags(p)}
                      {p.aliases.length > 0 && <div className="hint">{t("setup.also_called", { names: p.aliases.join(", ") })}</div>}
                    </>
                  ),
                }}
                columns={columns}
                groups={[{ id: "all", title: t("setup.people"), rows }]}
                rowKey={(p) => p.id}
                selected={chosen}
                onSelect={(p) => setChosen(p.id)}
                actionsHeader={t("people.col.actions")}
                actions={(p) => <RowMenu label={p.name} actions={menu(p)} />}
              />
            )}
            <p className="hint">{tn("people.count", all.length)}</p>
          </>
        )}
      </ListDetail>
      <Organizations />
      {adding && <PersonDrawer onClose={() => setAdding(false)} onSaved={(id) => setChosen(id)} />}
      {editing && <PersonDrawer person={editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

function PersonDetail(props: { person: S["PersonView"]; tags: React.ReactNode; reach: string[]; onEdit: () => void; menu: MenuAction[] }) {
  const { t, tn } = useWords();
  const p = props.person;
  const fact = (label: string, value: React.ReactNode) =>
    value ? (
      <div className="detail">
        <dt>{label}</dt>
        <dd>{value}</dd>
      </div>
    ) : null;
  return (
    <>
      <div className="row-end">{props.tags}</div>
      <dl className="details-list">
        {fact(t("people.col.role"), p.role)}
        {fact(t("people.col.org"), p.org_name)}
        {fact(t("setup.first_name"), p.first_name)}
        {fact(t("setup.aliases"), p.aliases.join(", "))}
        {fact(t("people.col.reach"), props.reach.length ? props.reach.map((line) => <div key={line}>{line}</div>) : null)}
        {fact(t("people.col.open"), p.open_items > 0 ? tn("people.open_with", p.open_items) : null)}
        {fact(t("people.col.last"), p.last_contact ? day(p.last_contact) : null)}
      </dl>
      <div className="row-end">
        <a className="btn" href={viewHref(recordView("person", p.id))}>
          {t("records.open_page", { name: p.name })}
        </a>
        <Button variant="primary" onClick={props.onEdit}>
          {t("setup.edit")}
        </Button>
      </div>
    </>
  );
}
