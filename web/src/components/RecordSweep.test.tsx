import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import type { S } from "../lib/api";
import { org, person, project, unfiledItem, unfiledView } from "../lib/records-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { OpenItems } from "./OpenItems";
import { People } from "./People";
import { Projects } from "./Projects";
import { RecordPage } from "./RecordPage";
import { Unfiled } from "./Unfiled";

// The sweep: every kind of record's page and the main list views, drawn from data the way the server
// sends it, never show an id of the app's own, a date as it is stored, a dot beside nothing, or a choice as its stored
// word. A new view that leaks one fails here.

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";
const ID = /\b[A-Z]{2,5}-\d+\b/;
const ISO_DATE = /\d{4}-\d{2}-\d{2}/;
const EMPTY_DOT = /·\s*·|·\s*$|^\s*·/m;

/** What no screen of the app says. `choices` are the stored words of choice fields, which a label stands in for. */
function sweep(root: HTMLElement, choices: string[] = []) {
  const text = root.textContent ?? "";
  expect(text.match(ID)?.[0] ?? null, "an id of the app's own").toBeNull();
  expect(text.match(ISO_DATE)?.[0] ?? null, "a date as it is stored").toBeNull();
  for (const piece of root.querySelectorAll("li, .detail, .meta, .sub, dd, td, p")) {
    // Lines of text only: a piece that holds other pieces is looked at through them.
    if (piece.querySelector("li, .detail, .meta, .sub, dd, td, p")) continue;
    const own = (piece.textContent ?? "").trim();
    expect(own, `an empty separator in "${own}"`).not.toMatch(EMPTY_DOT);
    expect(choices, `a stored word on its own line: "${own}"`).not.toContain(own);
  }
}

const field = (name: string, type: S["FieldView"]["type"], extra: Partial<S["FieldView"]> = {}): S["FieldView"] => ({ name, description: `Help for ${name}.`, type, required: false, editable: true, ...extra });
const ref = (kind: string, id: string, name: string) => ({ kind, id, name });
const robin = ref("person", "PER-1", "Robin Sample");
const harbor = ref("project", "PRJ-1", "Harbor");
const team = ref("team", "TEAM-1", "Quarry Editorial");
const house = ref("organization", "ORG-1", "Quarry House");

type Kind = { kind: string; fields: Record<string, unknown>; views: S["FieldView"][]; refs: Array<[string, ReturnType<typeof ref>[]]>; page?: Partial<S["RecordPageView"]> };

const kinds: Kind[] = [
  {
    kind: "person",
    fields: { full_name: "Robin Sample", aliases: ["Rob"], role: "Editor", team: "TEAM-1", org: "ORG-1", how_to_reach: { email: "robin@example.org" }, name_verified: false, status: "active", why_they_matter: "Runs the press" },
    views: [field("full_name", "text"), field("aliases", "list"), field("role", "text"), field("team", "text"), field("org", "reference", { refers_to: "organization" }), field("how_to_reach", "other"), field("name_verified", "yes_no"), field("status", "choice", { options: ["active", "left"] }), field("why_they_matter", "text")],
    refs: [["team", [team]], ["org", [house]]],
    page: {
      open_actions: [
        { id: "ACT-1", text: "Send two spine options", due: "2026-10-16", owners: ["Robin Sample"], project: "PRJ-1", project_name: "Harbor", origin: null },
        { id: "ACT-2", text: "Check the cover", owners: [], origin: null },
      ],
      completed_actions: [{ id: "ACT-3", text: "Book the printer", project: "PRJ-1", project_name: "Harbor", done_by: ["Robin Sample"], done_on: "2026-10-12" }],
      activity: [{ at: "2026-10-12T09:00:00Z", kind: "person", id: "PER-1", name: "Robin Sample", op: "record.set", field: "why_they_matter", actor: "assistant", by_assistant: true }],
    },
  },
  {
    kind: "project",
    fields: { name: "Harbor", status: "On track", phase: "Design", target: "2026-12-01", owner: "PER-1", parent: "PRJ-2", links: [{ label: "Press kit", url: `${WEB}example.com/press/kit` }], roles: [{ person: "PER-1", role: "run" }], log: [{ on: "2026-10-01", text: "Kicked off" }] },
    views: [field("name", "text"), field("status", "choice", { value_list: "project-status", options: ["On track"] }), field("phase", "choice", { value_list: "project-phase", options: ["Design"] }), field("target", "date"), field("owner", "text"), field("parent", "text"), field("links", "list"), field("roles", "list"), field("log", "list")],
    refs: [["owner", [robin]], ["roles", [robin]]],
  },
  { kind: "organization", fields: { name: "Quarry House", aliases: ["LH"], notes: "A small press." }, views: [field("name", "text"), field("aliases", "list"), field("notes", "text")], refs: [] },
  { kind: "team", fields: { name: "Quarry Editorial", members: ["PER-1", "PER-2"] }, views: [field("name", "text"), field("members", "list")], refs: [["members", [robin, ref("person", "PER-2", "Dana Whitlock")]]] },
  {
    kind: "action",
    fields: { text: "Send two spine options", owners: [{ person: "PER-1", team: "TEAM-1" }], due: "2026-10-20", status: "held", project: "PRJ-1", promised_to: ["PER-2"], basis: "said" },
    views: [field("text", "text"), field("owners", "list"), field("due", "date"), field("status", "choice", { options: ["open", "held", "done", "dropped"] }), field("project", "reference", { refers_to: "project" }), field("promised_to", "list"), field("basis", "choice", { options: ["inferred", "said"] })],
    refs: [["owners", [robin, team]], ["project", [harbor]], ["promised_to", [ref("person", "PER-2", "Dana Whitlock")]]],
  },
  {
    kind: "question",
    fields: { title: "Which spine suits the paperback?", text: "Two options came in.", to: "PER-1", status: "sent", kind: "decision", asks_about: "design", projects: ["PRJ-1"], sent_at: "2026-10-14T09:30:00+00:00" },
    views: [field("title", "text"), field("text", "text"), field("to", "reference", { refers_to: "person" }), field("status", "choice", { options: ["open", "sent", "answered", "dropped"] }), field("kind", "choice", { options: ["question", "decision"] }), field("asks_about", "choice", { options: ["date", "decision", "design", "mistake", "other"] }), field("projects", "list"), field("sent_at", "date")],
    refs: [["to", [robin]], ["projects", [harbor]]],
  },
  {
    kind: "fact",
    fields: { text: "Both spines are in the folder.", basis: "said", said_by: "PER-1", as_of: "2026-10-01", project: "PRJ-1", key: false },
    views: [field("text", "text"), field("basis", "choice", { options: ["inferred", "said", "person"] }), field("said_by", "reference", { refers_to: "person" }), field("as_of", "date"), field("project", "reference", { refers_to: "project" }), field("key", "yes_no")],
    refs: [["said_by", [robin]], ["project", [harbor]]],
    page: { fact_source: { basis: "said", by: "Robin Sample", kind: "email", sender: "Robin Sample", on: "2026-10-01", origin: { kind: "source", source: "SRC-1" } } },
  },
  {
    kind: "event",
    fields: { title: "Print sync", start: "2026-10-20T15:00:00+00:00", end: "2026-10-20T16:00:00+00:00", project: "PRJ-1", attendees: [], organizer: null, invitation: false },
    views: [field("title", "text"), field("start", "date"), field("end", "date"), field("project", "reference", { refers_to: "project" })],
    refs: [["project", [harbor]]],
  },
  { kind: "note", fields: { text: "Printer prefers PDF/X files.", project: "PRJ-1" }, views: [field("text", "text"), field("project", "reference", { refers_to: "project" })], refs: [["project", [harbor]]] },
];

function serve(k: Kind, id: string) {
  const enc = encodeURIComponent(k.kind);
  const name = String(k.fields.full_name ?? k.fields.name ?? k.fields.title ?? k.fields.text);
  const shown: S["RecordPageView"] = {
    kind: k.kind,
    id,
    version: 2,
    name,
    details: k.refs.map(([f, refs]) => ({ field: f, value: k.fields[f], type: "text" as const, refs })),
    open_actions: [],
    open_questions: [],
    completed_actions: [],
    fact_source: null,
    activity: [{ at: "2026-10-12T09:00:00Z", kind: k.kind, id, name, op: "record.edit", field: "due", actor: "assistant", by_assistant: true }],
    ...k.page,
  };
  const routes: Routes = {
    [`GET record?kind=${enc}&id=${id}`]: () => ({ kind: k.kind, id, version: 3, fields: { id, ...k.fields }, long_text: [] }),
    [`GET kinds/${k.kind}`]: () => ({ kind: k.kind, fields: k.views }),
    [`GET record-pages/${id}?kind=${enc}`]: () => shown,
    "GET people": () => [person("PER-1", "Robin Sample"), person("PER-2", "Dana Whitlock")],
    "GET projects": () => [project("PRJ-1", "Harbor"), project("PRJ-2", "Upper Shelf")],
    "GET settings": () => ({ fingerprint: "fp", items: [] }),
    "GET lists": () => [],
    "GET organizations": () => [org("ORG-1", "Quarry House")],
    [`GET plugin-actions?kind=${enc}&id=${id}`]: () => [],
    [`GET task-kinds?kind=${enc}&id=${id}`]: () => [],
  };
  fakeApi(routes);
}

test.each(kinds.map((k) => [k.kind, k] as const))("the page of a %s record says names, dates and words", async (_name, k) => {
  const id = `${k.kind.slice(0, 3).toUpperCase()}-1`;
  serve(k, id);
  const view = renderApp(<RecordPage kind={k.kind} id={id} onBack={() => {}} />);
  await screen.findByRole("region", { name: "Details" });
  await screen.findByRole("region", { name: "Activity" });
  if (k.page?.open_actions) await screen.findByRole("region", { name: /Open with/ });
  if (k.kind === "fact") await screen.findByRole("button", { name: /^from / });
  const stored = k.views.filter((f) => f.type === "choice" && !f.value_list).flatMap((f) => f.options ?? []);
  sweep(view.container, stored);
});

test("the people, projects, open to-dos and unfiled lists say names, dates and words", async () => {
  const ana = person("PER-1", "Ana Person", { role: "Editor", org: "ORG-1", org_name: "Quarry House", open_items: 4, last_contact: "2026-10-08", how_to_reach: { email: "ana@example.com" } });
  const open: S["OpenActionView"] = {
    id: "ACT-1", version: 3, text: "Send the proof to the printer", state: "overdue", owners: [{ person: "PER-1", name: "Ana Person" }], due: "2026-10-12", project: "PRJ-1", project_name: "Harbor", parent_name: null, notes: null,
    since: "2026-10-01", on_hold: null, blocker: null, duplicate: null, origin: null, untouched_days: null, owner_question: null, to_send: false,
  };
  const none: S["OpenActionView"] = { ...open, id: "ACT-2", text: "Order the sample copies", owners: [], due: null, project: null, project_name: "", state: "no_owner" };
  const ask: S["OpenQuestionView"] = { id: "Q-1", version: 2, title: "Which cover finish?", text: "", kind: "question", state: "waiting", to: "PER-1", to_name: "Ana Person", project_name: "Harbor", projects: ["PRJ-1"], since: "2026-10-08", waiting_days: 6, chases: 0, held_until: null, origin: null };
  const routes: Routes = {
    "GET people": () => [ana, person("PER-2", "Ben Person")],
    "GET organizations": () => [org("ORG-1", "Quarry House", 1)],
    "GET projects": () => [project("PRJ-1", "Harbor", { target: "2026-12-01", owner: "PER-1", owner_name: "Ana Person", status: "On track", open_actions: 2 })],
    "GET notes": () => [],
    "GET unfiled": () => unfiledView(unfiledItem("note", "N-1", "Printer prefers PDF/X files."), unfiledItem("action", "A-9", "Send the proof to the printer")),
    "GET open-items": () => ({ actions: [open, none], questions: [ask], stale_days: 21 }),
    "GET settings": () => ({ fingerprint: "fp", items: [] }),
    "GET lists": () => [],
  };
  for (const [name, ui, ready] of [
    ["people", <People key="p" />, () => screen.findByRole("link", { name: "Ana Person" })],
    ["projects", <Projects key="r" />, () => screen.findByRole("link", { name: "Harbor" })],
    ["open to-dos", <OpenItems key="o" />, () => screen.findByRole("list", { name: "Open to-dos" })],
    ["unfiled", <Unfiled key="u" />, () => screen.findByRole("heading", { name: "Unfiled" })],
  ] as const) {
    fakeApi(routes);
    const view = renderApp(ui);
    await ready();
    expect(within(view.container).queryAllByRole("row").length + within(view.container).queryAllByRole("listitem").length, name).toBeGreaterThan(0);
    sweep(view.container);
    view.unmount();
  }
});
