import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { person, project } from "../lib/records-fixtures";
import { fakeApi, renderApp } from "../test-utils";
import { RecordPage } from "./RecordPage";

// A record's page says names, dates and words (design 7.14): references as names, dates as elsewhere, choices as
// labels, no help text while viewing, and the details in the order a reader looks for them.

const WEB = "https" + "://";
const field = (name: string, type: S["FieldView"]["type"], extra: Partial<S["FieldView"]> = {}): S["FieldView"] => ({
  name,
  description: `Help for ${name}, shown only in the edit form.`,
  type,
  required: false,
  editable: true,
  ...extra,
});

const page = (kind: string, id: string, name: string, details: S["RecordPageView"]["details"]): S["RecordPageView"] => ({
  kind,
  id,
  version: 2,
  name,
  details,
  open_actions: [],
  open_questions: [],
  completed_actions: [],
  fact_source: null,
  activity: [],
});

const ref = (kind: string, id: string, name: string) => ({ kind, id, name });

function serve(kind: string, id: string, fields: Record<string, unknown>, fieldViews: S["FieldView"][], shown: S["RecordPageView"]) {
  const k = encodeURIComponent(kind);
  fakeApi({
    [`GET record?kind=${k}&id=${id}`]: () => ({ kind, id, version: 3, fields: { id, ...fields }, long_text: [] }),
    [`GET kinds/${kind}`]: () => ({ kind, fields: fieldViews }),
    [`GET record-pages/${id}?kind=${k}`]: () => shown,
    "GET people": () => [person("PER-1", "Robin Sample")],
    "GET projects": () => [project("PRJ-1", "Harbor")],
    "GET settings": () => ({ fingerprint: "fp", items: [] }),
    "GET lists": () => [],
    "GET organizations": () => [],
    [`GET plugin-actions?kind=${k}&id=${id}`]: () => [],
    [`GET task-kinds?kind=${k}&id=${id}`]: () => [],
  });
}

const personFields = [
  field("full_name", "text", { required: true }),
  field("aliases", "list"),
  field("role", "text"),
  field("team", "text"),
  field("org", "reference", { refers_to: "organization" }),
  field("how_to_reach", "other"),
  field("name_verified", "yes_no"),
  field("status", "choice", { options: ["active", "left"] }),
];

test("a person's details say names, words and a label for a choice, in the order a reader looks for them, with no help text", async () => {
  serve(
    "person",
    "PER-1",
    { full_name: "Robin Sample", aliases: ["Rob"], role: "Editor", team: "TEAM-1", org: "ORG-1", how_to_reach: { email: "robin@example.org" }, name_verified: false, status: "active" },
    personFields,
    page("person", "PER-1", "Robin Sample", [
      { field: "team", value: "TEAM-1", type: "text", refs: [ref("team", "TEAM-1", "Quarry Editorial")] },
      { field: "org", value: "ORG-1", type: "text", refs: [ref("organization", "ORG-1", "Quarry House")] },
    ]),
  );
  renderApp(<RecordPage kind="person" id="PER-1" onBack={() => {}} />);
  const details = await screen.findByRole("region", { name: "Details" });
  await within(details).findByText("Quarry House");
  expect(within(details).getAllByRole("term").map((x) => x.textContent)).toEqual(["Full name", "Role", "Organization", "How to reach", "Aliases", "Team", "Name verified", "Status"]);
  const value = (term: string) => within(details).getByText(term).closest(".detail")!.querySelector("dd")!.textContent;
  expect(value("Organization")).toBe("Quarry House");
  expect(value("Team")).toBe("Quarry Editorial");
  expect(value("How to reach")).toBe("Email: robin@example.org");
  expect(value("Name verified")).toBe("No");
  expect(value("Status")).toBe("Active");
  expect(details.textContent).not.toMatch(/Help for/);
  expect(details.textContent).not.toMatch(/\b[A-Z]{2,5}-\d+\b/);
});

test("a project's details say its owner by name, its target as a day, and its links by title with the domain beside", async () => {
  const long = `${WEB}example.com/press/kit/2026/a-very-long-path-that-would-break-over-several-lines/index.html`;
  serve(
    "project",
    "PRJ-1",
    { name: "Harbor", status: "On track", target: "2026-12-01", owner: "PER-1", links: [{ label: "Press kit", url: long }] },
    [field("name", "text", { required: true }), field("status", "choice", { value_list: "project-status", options: ["On track"] }), field("target", "date"), field("owner", "text"), field("links", "list")],
    page("project", "PRJ-1", "Harbor", [{ field: "owner", value: "PER-1", type: "text", refs: [ref("person", "PER-1", "Robin Sample")] }]),
  );
  renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />);
  const details = await screen.findByRole("region", { name: "Details" });
  await within(details).findByText("Robin Sample");
  expect(within(details).getByText(day("2026-12-01"))).toBeInTheDocument();
  expect(within(details).getByText("On track")).toBeInTheDocument();
  const link = within(details).getByRole("link", { name: "Press kit" });
  expect(link).toHaveAttribute("href", long);
  expect(details.textContent).toContain("example.com");
  expect(details.textContent).not.toContain("a-very-long-path");
  expect(details.textContent).not.toMatch(/\d{4}-\d{2}-\d{2}|PER-1/);
});

test("an empty value is no row, and a list of maps shows each map's parts joined without empty ones", async () => {
  serve(
    "project",
    "PRJ-1",
    { name: "Harbor", summary: "", tags: [], roles: [{ person: "PER-1", role: "run" }, { person: "PER-1", role: "" }] },
    [field("name", "text"), field("summary", "text"), field("tags", "list"), field("roles", "list")],
    page("project", "PRJ-1", "Harbor", [{ field: "roles", value: [], type: "list", refs: [ref("person", "PER-1", "Robin Sample")] }]),
  );
  renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />);
  const details = await screen.findByRole("region", { name: "Details" });
  await within(details).findByText("Roles");
  expect(within(details).getAllByRole("term").map((x) => x.textContent)).toEqual(["Name", "Roles"]);
  const lines = within(details).getByText("Roles").closest(".detail")!.querySelectorAll("dd > div");
  expect([...lines].map((l) => l.textContent)).toEqual(["Robin Sample · Run", "Robin Sample"]);
});
