// A plugin's panel (design 7.2): its records as a table, a list or a board. The first column opens the record's page;
// each row has one primary action and the rest in its menu. A person action opens its review; a kind of AI work starts
// at once. Every row looks the same whichever view the plugin chose.
import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { api, type S } from "../lib/api";
import { resolveOffers, usePluginActions, useTaskKinds, type Offer } from "../lib/plugin-actions";
import { usePluginRun } from "../lib/plugin-run";
import { readable, useValueLines } from "../lib/records";
import { useWords } from "../lib/wording";
import { RowMenu, type MenuAction } from "./RowMenu";

export function Panel(props: { name: string; project?: string; onOpenRecord: (kind: string, id: string) => void }) {
  const { t, tn } = useWords();
  const panels = useQuery({ queryKey: props.project ? ["panels", props.project] : ["panels"], queryFn: () => api.panels(props.project) });
  const rows = useQuery({
    queryKey: ["panel-rows", props.name, props.project ?? null],
    queryFn: () => api.panelRows(props.name, props.project),
  });
  const { run, review } = usePluginRun();
  const panel = panels.data?.find((p) => p.name === props.name);
  const workspaceActions = usePluginActions(undefined, undefined, !!panel?.new_action);
  const newAction = panel?.new_action ? workspaceActions.data?.find((a) => a.name === panel.new_action) : undefined;
  const newButton = useRef<HTMLButtonElement>(null);
  const title = panel?.title ?? readable(props.name.slice(props.name.lastIndexOf("/") + 1));
  const headingId = "panel-title";

  let body;
  if (panels.isPending || rows.isPending) body = <p className="empty">{t("loading")}</p>;
  else if (panels.isError || rows.isError || !panel) {
    body = (
      <p className="empty">
        {t("panel.load_failed")}{" "}
        <button
          type="button"
          className="btn"
          onClick={() => {
            void panels.refetch();
            void rows.refetch();
          }}
        >
          {t("action.try_again")}
        </button>
      </p>
    );
  } else if (rows.data.length === 0) body = <p className="empty">{t("panel.empty")}</p>;
  else {
    const shared = { panel, rows: rows.data, run, onOpenRecord: props.onOpenRecord };
    body =
      panel.view === "board" ? <Board {...shared} /> : panel.view === "list" ? <List {...shared} /> : <Table {...shared} />;
  }

  return (
    <section className="panel-section" aria-labelledby={headingId}>
      <div className="heading">
        <h2 id={headingId}>{title}</h2>
        {rows.data && rows.data.length > 0 && <span className="hint">{tn("panel.count", rows.data.length)}</span>}
      </div>
      {newAction && (
        <div className="panel-new">
          <button
            type="button"
            className="btn primary"
            ref={newButton}
            onClick={() => run({ name: newAction.name, label: newAction.label, is: "action", on: null }, null, () => newButton.current)}
          >
            {newAction.label}
          </button>
        </div>
      )}
      {body}
      {review}
    </section>
  );
}

interface ViewProps {
  panel: S["PanelView"];
  rows: S["PanelRow"][];
  run: (offer: Offer, target: { kind: string; id: string }, returnTo?: () => HTMLElement | null | undefined) => void;
  onOpenRecord: (kind: string, id: string) => void;
}

/** What one row offers: its primary action and the menu's actions, once the record's offers are known. */
function useRowOffers(panel: S["PanelView"], row: S["PanelRow"]) {
  const actions = usePluginActions(panel.kind, row.id);
  const tasks = useTaskKinds(panel.kind, row.id);
  const ready = !actions.isPending && !tasks.isPending;
  const offers = ready
    ? resolveOffers([panel.primary_action, ...panel.row_actions], actions.data ?? [], tasks.data ?? [])
    : [];
  const primary = offers.find((o) => o.name === panel.primary_action) ?? null;
  const rest = offers.filter((o) => o !== primary);
  return { primary, rest };
}

/** The actions cell: one primary button and the "…" menu, for any row of any view. */
function RowActions(props: { panel: S["PanelView"]; row: S["PanelRow"]; label: string; run: ViewProps["run"] }) {
  const { t } = useWords();
  const { panel, row } = props;
  const box = useRef<HTMLDivElement>(null);
  const { primary, rest } = useRowOffers(panel, row);
  const target = { kind: panel.kind, id: row.id };
  const menu: MenuAction[] = rest.map((o) => ({
    id: o.name,
    label: o.label,
    run: () => props.run(o, target, () => box.current?.querySelector<HTMLElement>("button.more")),
  }));
  return (
    <div className="acts" ref={box}>
      {primary && (
        <button
          type="button"
          className="btn primary"
          data-key="primary"
          aria-label={t("panel.action_for", { action: primary.label, what: props.label })}
          onClick={(e) => {
            const button = e.currentTarget;
            props.run(primary, target, () => button);
          }}
        >
          {primary.label}
        </button>
      )}
      <RowMenu label={props.label} actions={menu} />
    </div>
  );
}

function useCells() {
  const lines = useValueLines();
  const { t } = useWords();
  return (row: S["PanelRow"], column: string) => lines(row.values[column]).join(", ") || t("panel.blank");
}

function RowTitle(props: { text: string; onOpen: () => void }) {
  return (
    <button type="button" className="link-button" onClick={props.onOpen}>
      {props.text}
    </button>
  );
}

function Table(props: ViewProps) {
  const { t } = useWords();
  const { panel } = props;
  const cell = useCells();
  return (
    <div className="table-wrap" role="region" aria-labelledby="panel-title" tabIndex={0}>
      <table className="panel-table">
        <thead>
          <tr>
            {panel.columns.map((c) => (
              <th key={c} scope="col">
                {readable(c)}
              </th>
            ))}
            <th scope="col">
              <span className="sr">{t("panel.actions")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {props.rows.map((row) => {
            const title = cell(row, panel.columns[0]);
            return (
              <tr key={row.id} data-row>
                {panel.columns.map((c, i) =>
                  i === 0 ? (
                    <th key={c} scope="row">
                      <RowTitle text={title} onOpen={() => props.onOpenRecord(panel.kind, row.id)} />
                    </th>
                  ) : (
                    <td key={c}>{cell(row, c)}</td>
                  ),
                )}
                <td>
                  <RowActions panel={panel} row={row} label={title} run={props.run} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** One row as a card: the title opens the record; the other columns are labelled facts beneath it. */
function Card(props: ViewProps & { row: S["PanelRow"]; titleColumn: string; skip: string[] }) {
  const { panel, row } = props;
  const cell = useCells();
  const title = cell(row, props.titleColumn);
  const facts = panel.columns.filter((c) => c !== props.titleColumn && !props.skip.includes(c));
  return (
    <li className="line" data-row>
      <div className="row pair">
        <div className="text">
          <div className="name">
            <RowTitle text={title} onOpen={() => props.onOpenRecord(panel.kind, row.id)} />
          </div>
          {facts.length > 0 && (
            <dl className="facts">
              {facts.map((c) => (
                <div key={c}>
                  <dt>{readable(c)}</dt>
                  <dd>{cell(row, c)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
        <RowActions panel={panel} row={row} label={title} run={props.run} />
      </div>
    </li>
  );
}

function List(props: ViewProps) {
  return (
    <ul className="queue">
      {props.rows.map((row) => (
        <Card key={row.id} {...props} row={row} titleColumn={props.panel.columns[0]} skip={[]} />
      ))}
    </ul>
  );
}

/** Columns of cards, one for each value of the first column; a card is titled by the next column. */
function Board(props: ViewProps) {
  const { panel } = props;
  const cell = useCells();
  const groupBy = panel.columns[0];
  const titleColumn = panel.columns[1] ?? panel.columns[0];
  const groups = new Map<string, S["PanelRow"][]>();
  for (const row of props.rows) {
    const key = cell(row, groupBy);
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  return (
    <div className="board">
      {[...groups].map(([name, rows], i) => (
        <section key={name} className="board-column" aria-labelledby={`board-${i}`}>
          <h3 id={`board-${i}`} className="what">
            {name}
          </h3>
          <ul className="queue">
            {rows.map((row) => (
              <Card key={row.id} {...props} row={row} titleColumn={titleColumn} skip={[groupBy]} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
