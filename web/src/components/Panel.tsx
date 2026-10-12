// A plugin's panel (design 7.2): its records as a table, a list or a board. The first column opens the record's page;
// each row has one primary action and the rest in its menu. A person action opens its review; a kind of AI work starts
// at once. Every row looks the same whichever view the plugin chose. A document panel is read-only text the plugin
// builds (headings, paragraphs, lists, tables, rules), drawn as our own elements, never as HTML.
import { useQuery } from "@tanstack/react-query";
import { Fragment, useRef, type ReactNode } from "react";
import { api, ApiError, type S } from "../lib/api";
import { resolveOffers, usePluginActions, useTaskKinds, type Offer } from "../lib/plugin-actions";
import { usePluginRun } from "../lib/plugin-run";
import { readable, useValueLines } from "../lib/records";
import { useWords } from "../lib/wording";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SafeLink } from "./SafeText";
import { Skeleton } from "../ui/Skeleton";

export function Panel(props: { name: string; project?: string; onOpenRecord: (kind: string, id: string) => void }) {
  const { t, tn } = useWords();
  const panels = useQuery({ queryKey: props.project ? ["panels", props.project] : ["panels"], queryFn: () => api.panels(props.project) });
  const panel = panels.data?.find((p) => p.name === props.name);
  const isDocument = panel?.view === "document";
  const rows = useQuery({
    queryKey: ["panel-rows", props.name, props.project ?? null],
    queryFn: () => api.panelRows(props.name, props.project),
    enabled: !!panel && !isDocument,
  });
  const document = useQuery({
    queryKey: ["panel-document", props.name, props.project ?? null],
    queryFn: () => api.panelDocument(props.name, props.project),
    enabled: isDocument,
  });
  const { run, review } = usePluginRun();
  const workspaceActions = usePluginActions(undefined, undefined, !!panel?.new_action);
  const newAction = panel?.new_action ? workspaceActions.data?.find((a) => a.name === panel.new_action) : undefined;
  const newButton = useRef<HTMLButtonElement>(null);
  const title = panel?.title ?? readable(props.name.slice(props.name.lastIndexOf("/") + 1));
  const headingId = "panel-title";

  const content = isDocument ? document : rows;
  const failure = panels.error ?? content.error;
  let body;
  if (panels.isPending || (!!panel && content.isPending)) body = <Skeleton />;
  else if (panels.isError || content.isError || !panel) {
    body = (
      <p className="empty" role="alert">
        {failure instanceof ApiError && failure.detail ? failure.detail : t("panel.load_failed")}{" "}
        <button
          type="button"
          className="btn"
          onClick={() => {
            void panels.refetch();
            void content.refetch();
          }}
        >
          {t("action.try_again")}
        </button>
      </p>
    );
  } else if (isDocument) {
    body = document.data?.blocks ? (
      <Document blocks={document.data.blocks} onOpenRecord={props.onOpenRecord} />
    ) : (
      <p className="empty">{t("panel.document_empty")}</p>
    );
  } else if (!rows.data || rows.data.length === 0) body = <p className="empty">{t("panel.empty")}</p>;
  else {
    const shared = { panel, rows: rows.data, run, onOpenRecord: props.onOpenRecord };
    body =
      panel.view === "board" ? <Board {...shared} /> : panel.view === "list" ? <List {...shared} /> : <Table {...shared} />;
  }

  return (
    <section className="panel-section" aria-labelledby={headingId}>
      <div className="heading">
        {props.project ? <h3 id={headingId}>{title}</h3> : <h1 id={headingId}>{title}</h1>}
        {!isDocument && rows.data && rows.data.length > 0 && <span className="hint">{tn("panel.count", rows.data.length)}</span>}
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

type Inline = S["DocumentInline"];
type Block = S["DocumentBlock"];

/** One run of text: plain text, never markup. A record link opens the record's page; an outside link shows its domain. */
function Run(props: { inline: Inline; onOpenRecord: (kind: string, id: string) => void }) {
  const { inline, onOpenRecord } = props;
  const record = inline.record;
  if (record) {
    return (
      <button type="button" className="link-button" onClick={() => onOpenRecord(record.kind, record.id)}>
        {styled(inline)}
      </button>
    );
  }
  if (inline.url) return <SafeLink label={inline.text} url={inline.url} />;
  return <>{styled(inline)}</>;
}

function styled(inline: Inline): ReactNode {
  let node: ReactNode = inline.text;
  if (inline.code) node = <code>{node}</code>;
  if (inline.em) node = <em>{node}</em>;
  if (inline.strong) node = <strong>{node}</strong>;
  return node;
}

function Runs(props: { inlines: Inline[]; onOpenRecord: (kind: string, id: string) => void }) {
  return (
    <>
      {props.inlines.map((inline, i) => (
        <Run key={i} inline={inline} onOpenRecord={props.onOpenRecord} />
      ))}
    </>
  );
}

/** A document's headings sit under the panel's own h2: levels 1 to 3 are h3 to h5. */
const HEADINGS = ["h3", "h4", "h5"] as const;

function Document(props: { blocks: Block[]; onOpenRecord: (kind: string, id: string) => void }) {
  const { onOpenRecord } = props;
  return (
    <div className="document">
      {props.blocks.map((block, i) => {
        const key = `b${i}`;
        switch (block.type) {
          case "heading": {
            const Tag = HEADINGS[Math.min(Math.max(block.level ?? 1, 1), 3) - 1];
            return (
              <Tag key={key}>
                <Runs inlines={block.inlines ?? []} onOpenRecord={onOpenRecord} />
              </Tag>
            );
          }
          case "paragraph":
            return (
              <p key={key}>
                <Runs inlines={block.inlines ?? []} onOpenRecord={onOpenRecord} />
              </p>
            );
          case "list": {
            const Tag = block.ordered ? "ol" : "ul";
            return (
              <Tag key={key}>
                {(block.items ?? []).map((item, j) => (
                  <li key={j}>
                    <Runs inlines={item} onOpenRecord={onOpenRecord} />
                  </li>
                ))}
              </Tag>
            );
          }
          case "table":
            return (
              <div key={key} className="table-wrap" tabIndex={0} role="region" aria-labelledby="panel-title">
                <table className="panel-table">
                  <thead>
                    <tr>
                      {(block.header ?? []).map((cell, j) => (
                        <th key={j} scope="col">
                          <Runs inlines={cell} onOpenRecord={onOpenRecord} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(block.rows ?? []).map((row, j) => (
                      <tr key={j}>
                        {row.map((cell, k) => (
                          <td key={k}>
                            <Runs inlines={cell} onOpenRecord={onOpenRecord} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "rule":
            return <hr key={key} />;
          default:
            return <Fragment key={key} />;
        }
      })}
    </div>
  );
}
