import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { RecordPage } from "./RecordPage";

const KIND = "demo/chapter";
const ID = "CH-1";
const on = `kind=${encodeURIComponent(KIND)}&id=${ID}`;
const field = "body_text";
const textUrl = `texts?kind=${encodeURIComponent(KIND)}&id=${ID}&field=${field}`;

const kind: S["KindView"] = {
  kind: KIND,
  fields: [
    { name: "id", description: "", type: "text", required: true, editable: false },
    { name: "title", description: "What the chapter is called.", type: "text", required: true, editable: true },
    { name: "owner", description: "", refers_to: "person", type: "reference", required: false, editable: true },
    { name: "tags", description: "", type: "list", required: false, editable: true },
    {
      name: "body_text",
      description: "The chapter itself.",
      long_text: "plain",
      type: "long_text",
      required: false,
      editable: false,
    },
  ],
};

function version(extra: Partial<S["TextVersionView"]> = {}): S["TextVersionView"] {
  return {
    id: "V-1",
    number: 1,
    version: 1,
    status: "accepted",
    source: "edit",
    words: 12,
    base: null,
    note: null,
    created_at: "2026-10-09T14:00:00Z",
    questions: [],
    unmapped: [],
    ...extra,
  };
}

function text(extra: Partial<S["TextFieldView"]> = {}): S["TextFieldView"] {
  return {
    text: "First paragraph.\n\nSecond <i>paragraph</i>.",
    current: 1,
    authorship: [
      { start: 0, end: 10, kind: "person", words: 5 },
      { start: 10, end: 20, kind: "assistant", words: 3 },
      { start: 20, end: 30, kind: "assistant_edit", words: 2 },
      { start: 30, end: 40, kind: "person", words: 1 },
    ],
    versions: [version()],
    ...extra,
  };
}

function routes(extra: Routes = {}): Routes {
  return {
    [`GET record?${on}`]: () => ({
      kind: KIND,
      id: ID,
      version: 4,
      fields: { id: ID, title: "The harbor", owner: "P-2", tags: ["one", "two"], notes: "", empty: [] },
      long_text: [field],
    }),
    [`GET kinds/${KIND}`]: () => kind,
    "GET people": () => [{ id: "P-2", name: "Robin Example" }],
    "GET projects": () => [],
    [`GET ${textUrl}`]: () => text(),
    [`GET working-copies/formats?kind=${encodeURIComponent(KIND)}&field=${field}`]: () => [],
    [`GET working-copies?${on}`]: () => [],
    [`GET plugin-actions?${on}`]: () => [],
    [`GET task-kinds?${on}`]: () => [],
    ...extra,
  };
}

test("ordinary fields are a labelled list: readable labels, help text, names for people, one line per list item", async () => {
  fakeApi(routes());
  renderApp(<RecordPage kind={KIND} id={ID} onBack={() => {}} />);
  expect(await screen.findByRole("heading", { level: 2, name: "The harbor" })).toBeInTheDocument();
  const details = screen.getByRole("region", { name: "Details" });
  const terms = within(details).getAllByRole("term").map((x) => x.textContent);
  expect(terms).toEqual(["Title", "Owner", "Tags"]);
  expect(within(details).getByText("What the chapter is called.")).toBeInTheDocument();
  expect(within(details).getByText("Robin Example")).toBeInTheDocument();
  expect(within(details).getByText("one")).toBeInTheDocument();
  expect(within(details).getByText("two")).toBeInTheDocument();
  expect(within(details).queryByText("P-2")).toBeNull();
});

test("a long text shows as plain text with three separate authorship counts", async () => {
  fakeApi(routes());
  renderApp(<RecordPage kind={KIND} id={ID} onBack={() => {}} />);
  const section = await screen.findByRole("region", { name: "Body text" });
  expect(await within(section).findByText("Second <i>paragraph</i>.")).toBeInTheDocument();
  expect(section.querySelector("i")).toBeNull();
  const who = within(section).getAllByRole("listitem").map((li) => li.textContent);
  expect(who).toContain("6 words written by you");
  expect(who).toContain("3 words drafted by Helper");
  expect(who).toContain("2 words of yours changed by Helper");
});

test("the versions list marks each one waiting with Review, which opens the text review", async () => {
  const user = userEvent.setup();
  fakeApi(
    routes({
      [`GET ${textUrl}`]: () =>
        text({
          versions: [
            version({ id: "V-2", number: 2, status: "pending", source: "draft", note: "A tighter opening", words: 9 }),
            version(),
          ],
        }),
      "GET text-versions/V-2/review": () => ({
        version: version({ id: "V-2", number: 2, status: "pending", version: 3 }),
        current: 1,
        three_way: false,
        regions: [],
        pending_text: "",
      }),
    }),
  );
  renderApp(<RecordPage kind={KIND} id={ID} onBack={() => {}} />);
  const section = await screen.findByRole("region", { name: "Body text" });
  expect(await within(section).findByText("A tighter opening")).toBeInTheDocument();
  expect(within(section).getByText(/Waiting for you · Draft · 9 words/)).toBeInTheDocument();
  expect(within(section).getAllByRole("button", { name: /^Review version/ })).toHaveLength(1);
  await user.click(within(section).getByRole("button", { name: "Review version 2" }));
  expect(await screen.findByRole("dialog", { name: "Review the changes" })).toBeInTheDocument();
});

test("Edit swaps the text for a box; Save sends it and offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(
    routes({
      "POST texts/edit": () => ({ changeset: "CS-9" }),
      "POST changesets/CS-9/undo": () => ({ restored: [{ kind: KIND, id: ID }], skipped: [] }),
    }),
  );
  renderApp(<RecordPage kind={KIND} id={ID} onBack={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  const box = screen.getByRole("textbox", { name: "Body text" });
  expect(box).toHaveFocus();
  expect(box).toHaveValue("First paragraph.\n\nSecond <i>paragraph</i>.");
  await user.clear(box);
  await user.type(box, "Rewritten.");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Text saved.")).toBeInTheDocument();
  expect(calls.find((c) => c.route === "POST texts/edit")?.body).toEqual({ kind: KIND, id: ID, field, text: "Rewritten." });
  await waitFor(() => expect(screen.queryByRole("textbox", { name: "Body text" })).toBeNull());
  await waitFor(() => expect(screen.getByRole("button", { name: "Edit" })).toHaveFocus());
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-9/undo"));
});

test("Cancel leaves the text alone", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(routes());
  renderApp(<RecordPage kind={KIND} id={ID} onBack={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("textbox")).toBeNull();
  expect(calls.some((c) => c.route === "POST texts/edit")).toBe(false);
});

test("what the plugins offer: the first is the primary button, the rest are in the menu, and a person action opens its review", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(
    routes({
      [`GET plugin-actions?${on}`]: () => [{ name: "demo/export", label: "Export", on: KIND }],
      [`GET task-kinds?${on}`]: () => [
        { name: "demo/check", label: "Check it", on: KIND },
        { name: "demo/polish", label: "Polish it", on: KIND },
      ],
      "POST plugin-actions/demo/export/preview": () => ({
        token: "t",
        action: "demo/export",
        summary: "Export the chapter",
        ops: [],
        files: [],
        previews: [],
        choices: [],
        notes: [],
        expires_at: "2026-10-09T15:00:00Z",
      }),
      "POST task-kinds/demo/polish/start": () => ({ request: "REQ-2" }),
    }),
  );
  renderApp(<RecordPage kind={KIND} id={ID} onBack={() => {}} />);
  const group = await screen.findByRole("group", { name: "Things to do here" });
  const primary = within(group).getByRole("button", { name: "Export" });
  await user.click(primary);
  await screen.findByRole("dialog", { name: "Export the chapter" });
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await user.click(within(group).getByRole("button", { name: /^More actions/ }));
  expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Check it", "Polish it"]);
  await user.click(screen.getByRole("menuitem", { name: "Polish it" }));
  expect(await screen.findByText("Started: Polish it")).toBeInTheDocument();
  expect(calls.find((c) => c.route === "POST task-kinds/demo/polish/start")?.body).toEqual({ about: { kind: KIND, id: ID }, note: "" });
});

test("Back goes back", async () => {
  const user = userEvent.setup();
  const back = vi.fn();
  fakeApi(routes());
  renderApp(<RecordPage kind={KIND} id={ID} onBack={back} />);
  await user.click(await screen.findByRole("button", { name: "Back" }));
  expect(back).toHaveBeenCalled();
});

const editKind: S["KindView"] = {
  kind: KIND,
  fields: [
    { name: "id", description: "", type: "text", required: true, editable: false },
    { name: "title", description: "What the chapter is called.", type: "text", required: true, editable: true },
    { name: "pages", description: "", type: "number", required: false, editable: true },
    { name: "final", description: "", type: "yes_no", required: false, editable: true },
    { name: "due", description: "", type: "date", required: false, editable: true },
    { name: "state", description: "", type: "choice", options: ["draft", "revised", "locked"], required: false, editable: true },
    { name: "mood", description: "", type: "choice", options: ["calm", "tense"], required: true, editable: true },
    { name: "owner", description: "", refers_to: "person", type: "reference", required: false, editable: true },
    { name: "book", description: "", refers_to: "project", type: "reference", required: false, editable: true },
    { name: "link", description: "", refers_to: "demo/other", type: "reference", required: false, editable: true },
    { name: "tags", description: "", type: "list", required: false, editable: true },
    { name: "locked", description: "", type: "text", required: false, editable: false },
    { name: "body_text", description: "", long_text: "plain", type: "long_text", required: false, editable: false },
    { name: "raw", description: "", type: "other", required: false, editable: true },
  ],
};

function editRoutes(extra: Routes = {}): Routes {
  return routes({
    [`GET kinds/${KIND}`]: () => editKind,
    [`GET record?${on}`]: () => ({
      kind: KIND,
      id: ID,
      version: 4,
      fields: { id: ID, title: "The harbor", pages: 12, final: false, due: "2026-11-01", state: "draft", mood: "calm", owner: "P-2", tags: ["one", "two"], locked: "x" },
      long_text: [field],
    }),
    "GET people": () => [
      { id: "P-2", name: "Robin Example", status: "active" },
      { id: "P-3", name: "Sam Sample", status: "active" },
    ],
    "GET projects": () => [
      { id: "PRJ-1", name: "First book" },
      { id: "PRJ-2", name: "Second book" },
    ],
    ...extra,
  });
}

async function openForm(user: ReturnType<typeof userEvent.setup>) {
  renderApp(<RecordPage kind={KIND} id={ID} onBack={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "Edit details" }));
  return screen.getByRole("form", { name: "Edit details" });
}

test("Edit details offers the right control for each editable field and skips the rest", async () => {
  const user = userEvent.setup();
  fakeApi(editRoutes());
  const form = await openForm(user);
  expect(within(form).getByRole("textbox", { name: "Title" })).toHaveValue("The harbor");
  expect(within(form).getByRole("textbox", { name: "Title" })).toBeRequired();
  expect(within(form).getByRole("spinbutton", { name: "Pages" })).toHaveValue(12);
  expect(within(form).getByRole("checkbox", { name: "Final" })).not.toBeChecked();
  expect(within(form).getByLabelText("Due")).toHaveAttribute("type", "date");
  expect(within(form).getByLabelText("Due")).toHaveValue("2026-11-01");
  const state = within(form).getByRole("combobox", { name: "State" });
  expect(within(state).getAllByRole("option").map((o) => o.textContent)).toEqual(["None", "draft", "revised", "locked"]);
  const mood = within(form).getByRole("combobox", { name: "Mood" });
  expect(within(mood).getAllByRole("option").map((o) => o.textContent)).toEqual(["calm", "tense"]);
  expect(within(form).getByRole("combobox", { name: "Owner" })).toHaveValue("P-2");
  const book = within(form).getByRole("combobox", { name: "Book" });
  expect(within(book).getAllByRole("option").map((o) => o.textContent)).toEqual(["None", "First book", "Second book"]);
  expect(within(form).getByRole("textbox", { name: /Tags/ })).toHaveValue("one\ntwo");
  for (const skipped of ["Id", "Link", "Locked", "Body text", "Raw"]) expect(within(form).queryByLabelText(skipped)).toBeNull();
});

test("Save sends only the changed fields with the version that was read, then offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(
    editRoutes({
      "POST records/edit": () => ({ changeset: "CS-9" }),
      "POST changesets/CS-9/undo": () => ({ restored: [{ kind: KIND, id: ID }], skipped: [] }),
    }),
  );
  const form = await openForm(user);
  const save = within(form).getByRole("button", { name: "Save" });
  expect(save).toBeDisabled();
  await user.clear(within(form).getByRole("textbox", { name: "Title" }));
  await user.type(within(form).getByRole("textbox", { name: "Title" }), "The new harbor");
  await user.click(within(form).getByRole("checkbox", { name: "Final" }));
  await user.selectOptions(within(form).getByRole("combobox", { name: "Book" }), "PRJ-2");
  await user.selectOptions(within(form).getByRole("combobox", { name: "Owner" }), "");
  await user.clear(within(form).getByRole("spinbutton", { name: "Pages" }));
  await user.clear(within(form).getByRole("textbox", { name: /Tags/ }));
  await user.type(within(form).getByRole("textbox", { name: /Tags/ }), "a{Enter}b{Enter}");
  await user.click(save);
  await waitFor(() => expect(screen.queryByRole("form", { name: "Edit details" })).toBeNull());
  expect(calls.find((c) => c.route === "POST records/edit")?.body).toEqual({
    kind: KIND,
    id: ID,
    read_version: 4,
    fields: { title: "The new harbor", final: true, book: "PRJ-2", owner: null, pages: null, tags: ["a", "b"] },
  });
  expect(await screen.findByText("Saved.")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "Edit details" })).toHaveFocus());
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-9/undo"));
});

test("a refusal shows the server's words and keeps the form open with what was typed", async () => {
  const user = userEvent.setup();
  fakeApi(editRoutes({ "POST records/edit": () => new Refuse(409, "This record changed after you opened it.") }));
  const form = await openForm(user);
  await user.type(within(form).getByRole("textbox", { name: "Title" }), "!");
  await user.click(within(form).getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This record changed after you opened it.");
  expect(screen.getByRole("form", { name: "Edit details" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("The harbor!");
  expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
});

test("Cancel puts the values back and closes the form", async () => {
  const user = userEvent.setup();
  fakeApi(editRoutes());
  const form = await openForm(user);
  await user.type(within(form).getByRole("textbox", { name: "Title" }), " and more");
  await user.click(within(form).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("form", { name: "Edit details" })).toBeNull();
  await user.click(await screen.findByRole("button", { name: "Edit details" }));
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("The harbor");
});
