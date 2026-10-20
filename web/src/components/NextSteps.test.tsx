// The obvious next step as one click: "Add a new person" on a "Who is this?" question (prefilled, the cursor in its first
// field, Undo), and the three choices on a project the assistant found.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { AskChooser } from "./AskChooser";
import { WhatChanged } from "./WhatChanged";

const prefill: S["NewPersonPrefillView"] = {
  full_name: "Jordan Pike",
  first_name: "Jordan",
  org: "Fernhill Press",
  role: "Sign printer",
  contact_kind: "email",
  contact_value: "jordan@example.org",
  contact_kinds: ["email", "phone", "address"],
};

const done: S["NewPersonDone"] = {
  person: "PER-9",
  name: "Jordan Pike",
  undo: ["CS-3", "CS-2"],
  changeset: "CS-1",
  released: [0, 1],
};

const whoIs = { id: "Q-1", about: "held-op", name: "Jordan", options: [] };

const personRoutes = {
  "GET people": () => [],
  "GET organizations": () => [{ id: "ORG-1", name: "Sample Org", aliases: [], notes: null, people: 2 }],
  "GET questions/Q-1/new-person": () => prefill,
  "POST questions/Q-1/new-person": () => done,
  "POST changesets/CS-1/undo": () => ({ restored: [0, 1], skipped: [] }),
  "POST changesets/CS-2/undo": () => ({ restored: [0], skipped: [] }),
  "POST changesets/CS-3/undo": () => ({ restored: [0], skipped: [] }),
};

/** The person picker's last choice opens the form in place: a drawer over the screen, which is never left. */
async function addAPerson(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(await screen.findByRole("combobox"), "Add a person…");
}

test("Add a person… in the list opens a form with the cursor in the full name, filled in from the input", async () => {
  const user = userEvent.setup();
  fakeApi(personRoutes);
  renderApp(<AskChooser ask={whoIs} />);
  await addAPerson(user);
  const name = await screen.findByRole("textbox", { name: "Full name" });
  expect(name).toHaveFocus();
  expect(name).toHaveValue("Jordan Pike");
  expect(screen.getByRole("textbox", { name: /First name/ })).toHaveValue("Jordan");
  expect(screen.getByRole("combobox", { name: /Organization/ })).toHaveValue("Fernhill Press");
  expect(screen.getByRole("textbox", { name: "Role" })).toHaveValue("Sign printer");
  expect(screen.getByRole("combobox", { name: /Contact type/ })).toHaveValue("email");
  expect(screen.getByRole("textbox", { name: /Email address or phone number/ })).toHaveValue("jordan@example.org");
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("textbox", { name: "Full name" })).toBeNull();
});

test("adding the person sends the form, says what went ahead and Undo takes the released items back first", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(personRoutes);
  renderApp(<AskChooser ask={whoIs} />);
  await addAPerson(user);
  const role = await screen.findByRole("textbox", { name: "Role" });
  await user.clear(role);
  await user.type(role, "Printer");
  await user.click(screen.getByRole("button", { name: "Add and use" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST questions/Q-1/new-person")?.body).toEqual({
    full_name: "Jordan Pike",
    first_name: "Jordan",
    org: "Fernhill Press",
    role: "Printer",
    contact_kind: "email",
    contact_value: "jordan@example.org",
  }));
  expect(await screen.findByText("Added Jordan Pike. Related work has resumed.")).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Full name" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route.endsWith("/undo")).map((c) => c.route)).toEqual([
    "POST changesets/CS-1/undo",
    "POST changesets/CS-3/undo",
    "POST changesets/CS-2/undo",
  ]));
  expect(calls.find((c) => c.route === "POST changesets/CS-1/undo")?.body).toEqual({ ops: [0, 1] });
});

test("a blank contact value sends no kind, and the add button waits for a name", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    ...personRoutes,
    "GET questions/Q-1/new-person": () => ({ ...prefill, org: "", role: "", contact_kind: "", contact_value: "" }),
  });
  renderApp(<AskChooser ask={{ ...whoIs, name: "" }} />);
  await addAPerson(user);
  const name = await screen.findByRole("textbox", { name: "Full name" });
  await user.clear(name);
  expect(screen.getByRole("button", { name: "Add and use" })).toBeDisabled();
  await user.type(name, "Casey Moor");
  await user.click(screen.getByRole("button", { name: "Add and use" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST questions/Q-1/new-person")?.body).toMatchObject({
    full_name: "Casey Moor",
    org: null,
    role: null,
    contact_kind: null,
    contact_value: null,
  }));
});

test("Add a person… is in the owner list too: the form opens in place and the person it adds is the one picked", async () => {
  const user = userEvent.setup();
  let people: S["PersonView"][] = [];
  const calls = fakeApi({
    ...personRoutes,
    "GET people": () => people,
    "POST people": () => {
      people = [{ id: "PER-9", name: "Casey Moor", role: null, org: null, org_name: null, aliases: [], status: "active", is_pm: false, track_only: false, open_items: 0, how_to_reach: {} } as S["PersonView"]];
      return { id: "PER-9" };
    },
    "POST questions/Q-2/answer": () => ({ request: null }),
  });
  renderApp(<AskChooser ask={{ id: "Q-2", about: "owner", name: null, options: [] }} />);
  const picker = await screen.findByRole("combobox", { name: "Who owns this?" });
  expect(within(picker).getByRole("option", { name: "Add a person…" })).toBeInTheDocument();
  await user.selectOptions(picker, "Add a person…");
  const dialog = await screen.findByRole("dialog", { name: "Add a person" });
  await waitFor(() => expect(within(dialog).getByRole("textbox", { name: "Full name" })).toHaveFocus());
  await user.type(within(dialog).getByRole("textbox", { name: "Full name" }), "Casey Moor");
  await user.click(within(dialog).getByRole("button", { name: "Add a person" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST people")?.body).toMatchObject({ full_name: "Casey Moor" }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Add a person" })).toBeNull());
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Who owns this?" })).toHaveValue("PER-9"));
  // The person is picked, not applied: answering is still their next click.
  expect(calls.some((c) => c.route === "POST questions/Q-2/answer")).toBe(false);
});

function projectChange(): S["ChangeItem"] {
  return {
    id: "REQ-5",
    version: 2,
    dismissed: false,
    stage_task: false,
    first_go: false,
    refused: false,
    state: "review",
    waiting: null,
    created_at: "2026-10-09T14:00:00Z",
    note: null,
    source: null,
    source_title: "Email about the fair",
    changeset: {
      id: "CS-5",
      summary: "A plan is needed.",
      status: "held",
      reviewed: false,
      trust: "untrusted",
      ops: [
        {
          index: 0,
          op: "note",
          status: "applied",
          reason: null,
          group: "op0",
          title: "The plan is due soon.",
          meta: { owners: [] },
          evidence: null,
          record: { kind: "note", id: "NOTE-1" },
          ask: null,
        },
        {
          index: 1,
          op: "project.add",
          status: "held",
          reason: "A project the workspace doesn't have yet: add it, or say where this belongs?",
          group: "op1",
          title: "Start the project Harvest Fair",
          meta: { owners: [], name: "Harvest Fair" },
          evidence: { quote: "The Harvest Fair needs a plan" },
          record: null,
          ask: null,
        },
      ],
    },
  };
}

const projectRoutes = {
  "GET changes": () => [projectChange()],
  "GET projects": () => [
    { id: "PRJ-1", name: "Sample Series", parent: null },
    { id: "PRJ-2", name: "Sample Book", parent: "PRJ-1" },
  ],
  "POST changesets/CS-5/ops/1/release": () => ({ ok: "CS-5" }),
  "POST changesets/CS-5/undo": () => ({ restored: [1], skipped: [] }),
  "POST changesets/CS-5/ops/1/part-of": () => ({ changeset: "CS-6" }),
  "POST changesets/CS-5/ops/1/not-a-project": () => ({ changeset: "CS-7" }),
  "POST changesets/CS-6/undo": () => ({ restored: [0], skipped: [] }),
  "POST changesets/CS-7/undo": () => ({ restored: [0], skipped: [] }),
};

test("a project the assistant found asks Add, with the other two choices in its menu", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(projectRoutes);
  renderApp(<WhatChanged />);
  expect(await screen.findByText("Add a project “Harvest Fair”?")).toBeInTheDocument();
  expect(screen.getByText("The Harvest Fair needs a plan")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Do it anyway" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-5/ops/1/release"));
  expect(await screen.findByText("Added the project Harvest Fair.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST changesets/CS-5/undo")?.body).toEqual({ ops: [1] }));
});

test("It's part of picks a project from the list with the cursor in it, files the work there and offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(projectRoutes);
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: "More actions for Harvest Fair" }));
  await user.click(await screen.findByRole("menuitem", { name: "It's part of…" }));
  const list = await screen.findByRole("combobox", { name: "“Harvest Fair” is part of" });
  expect(list).toHaveFocus();
  const go = screen.getByRole("button", { name: "File it there" });
  expect(go).toBeDisabled();
  expect(screen.getByRole("option", { name: "Sample Series › Sample Book" })).toBeInTheDocument();
  await user.selectOptions(list, "PRJ-2");
  await user.click(go);
  await waitFor(() => expect(calls.find((c) => c.route === "POST changesets/CS-5/ops/1/part-of")?.body).toEqual({ project: "PRJ-2" }));
  expect(await screen.findByText("Filed under Sample Series › Sample Book. “Harvest Fair” is kept as a name for it.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-6/undo"));
});

test("a project added from a link nothing can open says it was not read, in its row", async () => {
  const change = projectChange();
  change.changeset!.ops[1].meta = { owners: [], name: "Harvest Fair", note: "Not read: nothing set up can open this link" };
  fakeApi({ ...projectRoutes, "GET changes": () => [change] });
  renderApp(<WhatChanged />);
  expect(await screen.findByText("Not read: nothing set up can open this link")).toBeInTheDocument();
});

test("a project whose name shares a word with the held one is offered by name in the menu, filed there in one click", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    ...projectRoutes,
    "GET projects": () => [
      { id: "PRJ-1", name: "Sample Series", parent: null },
      { id: "PRJ-3", name: "Harvest Planning", parent: "PRJ-1" },
    ],
    "POST changesets/CS-5/ops/1/part-of": () => ({ changeset: "CS-6" }),
  });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: "More actions for Harvest Fair" }));
  expect(screen.queryByRole("menuitem", { name: "It's part of Sample Series" })).toBeNull();
  await user.click(await screen.findByRole("menuitem", { name: "It's part of Sample Series › Harvest Planning" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST changesets/CS-5/ops/1/part-of")?.body).toEqual({ project: "PRJ-3" }));
  expect(await screen.findByText("Filed under Sample Series › Harvest Planning. “Harvest Fair” is kept as a name for it.")).toBeInTheDocument();
});

test("Not a project sets it aside at once, says the words are kept, and offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(projectRoutes);
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: "More actions for Harvest Fair" }));
  await user.click(await screen.findByRole("menuitem", { name: "Not a project" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-5/ops/1/not-a-project"));
  expect(await screen.findByText("“Harvest Fair” is kept as not a project.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-7/undo"));
});
