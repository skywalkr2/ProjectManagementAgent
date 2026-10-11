import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { Setup } from "./Setup";

const project = (id: string, name: string): S["ProjectView"] => ({
  id,
  name,
  group: null,
  status: null,
  phase: null,
  target: null,
  owner: null,
  owner_name: null,
  summary: null,
  language: "en-US",
  language_own: false,
  spent_usd: 0,
});
const note = (id: string, text: string, p: S["ProjectView"] | null): S["NoteView"] => ({
  id,
  text,
  project: p?.id ?? null,
  project_name: p?.name ?? null,
  created_at: "2026-10-09T14:00:00Z",
  trust: "trusted",
});

const first = project("PRJ-1", "First project");
const second = project("PRJ-2", "Second project");

function api(notes: S["NoteView"][]) {
  fakeApi({
    "GET people": () => [],
    "GET projects": () => [first, second],
    "GET notes": () => notes,
  });
}

test("a project's menu shows its notes, newest first, and counts them", async () => {
  const user = userEvent.setup();
  api([note("N-3", "newer note", first), note("N-2", "other project", second), note("N-1", "older note", first)]);
  renderApp(<Setup />);
  const row = (await screen.findByText(first.name)).closest("li")!;
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Notes (2)" }));
  const items = within(row).getAllByRole("listitem").map((li) => li.textContent);
  expect(items[0]).toContain("newer note");
  expect(items[1]).toContain("older note");
  expect(items.join(" ")).not.toContain("other project");
});

test("a project with no notes says so", async () => {
  const user = userEvent.setup();
  api([]);
  renderApp(<Setup />);
  const row = (await screen.findByText(second.name)).closest("li")!;
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Notes (0)" }));
  expect(within(row).getByText("No notes are filed under this project yet.")).toBeInTheDocument();
});

test("notes with no project are grouped at the end", async () => {
  api([note("N-1", "loose thought", null)]);
  renderApp(<Setup />);
  const group = (await screen.findByRole("heading", { name: "Notes not filed under a project" })).closest("section")!;
  expect(within(group).getByText("loose thought")).toBeInTheDocument();
});

test("the group is absent when every note is filed under a project", async () => {
  api([note("N-1", "filed", first)]);
  renderApp(<Setup />);
  await screen.findByText(first.name);
  expect(screen.queryByRole("heading", { name: "Notes not filed under a project" })).not.toBeInTheDocument();
});
