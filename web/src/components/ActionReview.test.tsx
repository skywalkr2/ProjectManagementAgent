import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { useActionReview } from "./ActionReview";

const action = { name: "demo/make-note", label: "Make a note", on: "file" };
const target = { kind: "file", id: "FILE-1" };

function Harness() {
  const { start, review } = useActionReview();
  return (
    <>
      <button type="button" onClick={() => start(action, target)}>
        Start it
      </button>
      {review}
    </>
  );
}

function proposal(extra: Partial<S["ActionProposalView"]> = {}): S["ActionProposalView"] {
  return {
    token: "tok-1",
    action: action.name,
    summary: "Make a note from notes.txt",
    ops: [{ op: "note", label: "Note: first line (6 words)" }],
    files: [],
    previews: [],
    choices: [],
    notes: [],
    expires_at: "2026-10-09T15:00:00Z",
    ...extra,
  };
}

const PREVIEW_URL = "POST plugin-actions/demo/make-note/preview";

test("it shows what it will change, the files it adds, previews and notes", async () => {
  const user = userEvent.setup();
  const png = btoa("not really a picture");
  fakeApi({
    [PREVIEW_URL]: () =>
      proposal({
        ops: [
          { op: "note", label: "Note: first line" },
          { op: "note", label: "" },
        ],
        files: [{ name: "result.txt", media_type: "text/plain", size: 1536, file_kind: "attachment" }],
        previews: [
          { name: "page.png", media_type: "image/png", caption: "First page", alt: "", data_base64: png },
          { name: "page.txt", media_type: "text/plain", caption: "", alt: "", data_base64: btoa("Line one\nLine two <b>not bold</b>") },
          { name: "page.html", media_type: "text/html", caption: "Hidden", alt: "", data_base64: btoa("<b>never shown</b>") },
        ],
        notes: ["Only the first line is used."],
      }),
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const dialog = await screen.findByRole("dialog", { name: "Make a note from notes.txt" });
  const changes = within(dialog).getByRole("region", { name: "What it will change" });
  expect(within(changes).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Note: first line", "A change"]);
  expect(within(dialog).getByText("result.txt (1.5 KB)")).toBeInTheDocument();
  const image = within(dialog).getByRole("img", { name: "First page" });
  expect(image).toHaveAttribute("src", `data:image/png;base64,${png}`);
  const text = within(dialog).getByRole("region", { name: "page.txt" });
  expect(text).toHaveTextContent("Line one");
  expect(text).toHaveTextContent("<b>not bold</b>");
  expect(text.querySelector("b")).toBeNull();
  expect(within(dialog).queryByText("never shown")).toBeNull();
  expect(within(dialog).queryByText("Hidden")).toBeNull();
  expect(within(dialog).getByText("Only the first line is used.")).toBeInTheDocument();
});

test("changing a choice asks again with every current value and keeps focus on the control", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    [PREVIEW_URL]: (body) => {
      const choices = (body as { choices: Record<string, string | boolean> }).choices;
      const count = choices.count ?? true;
      const style = choices.style ?? "short";
      return proposal({
        summary: `Make a note (${style})`,
        ops: [{ op: "note", label: count ? "Note with count" : "Note without count" }],
        choices: [
          { id: "count", label: "Include the word count", value: count, options: [], help: "Adds how many words there are.", text: false, max_length: 200 },
          {
            id: "style",
            label: "Style",
            value: style,
            options: [
              { value: "short", label: "Short" },
              { value: "long", label: "Long" },
            ],
            help: "",
            text: false,
            max_length: 200,
          },
        ],
      });
    },
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  await screen.findByRole("dialog", { name: "Make a note (short)" });
  const count = screen.getByRole("checkbox", { name: "Include the word count" });
  expect(count).toBeChecked();
  expect(count).toHaveAccessibleDescription("Adds how many words there are.");
  await user.click(count);
  expect(count).toHaveFocus();
  expect(await screen.findByText("Note without count")).toBeInTheDocument();
  expect(count).not.toBeChecked();
  expect(count).toHaveFocus();
  await user.selectOptions(screen.getByRole("combobox", { name: "Style" }), "long");
  await screen.findByRole("dialog", { name: "Make a note (long)" });
  const previews = calls.filter((c) => c.route === PREVIEW_URL).map((c) => c.body);
  expect(previews).toEqual([
    { target, choices: {} },
    { target, choices: { count: false, style: "short" }, previous: "tok-1" },
    { target, choices: { count: false, style: "long" }, previous: "tok-1" },
  ]);
  expect(screen.getByRole("combobox", { name: "Style" })).toHaveValue("long");
});

test("Use applies exactly what was reviewed, says what happened in words and offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    [PREVIEW_URL]: () => proposal(),
    "POST plugin-actions/apply": () => ({ changeset: "CS-4", applied: 2, held: 1, refused: 0 }),
    "POST changesets/CS-4/undo": () => ({ restored: [{ kind: "note", id: "N-1" }], skipped: [] }),
  });
  renderApp(<Harness />);
  const start = screen.getByRole("button", { name: "Start it" });
  await user.click(start);
  await screen.findByRole("dialog");
  await user.click(await screen.findByRole("button", { name: "Make these changes" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(calls.find((c) => c.route === "POST plugin-actions/apply")?.body).toEqual({ token: "tok-1" });
  expect(await screen.findByText("Make a note from notes.txt: 2 changes made, 1 waiting for you.")).toBeInTheDocument();
  await waitFor(() => expect(start).toHaveFocus());
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-4/undo"));
  expect(await screen.findByText("Undone.")).toBeInTheDocument();
});

test("when every change was refused it says so instead of reporting success, and there is nothing to undo", async () => {
  const user = userEvent.setup();
  fakeApi({
    [PREVIEW_URL]: () => proposal(),
    "POST plugin-actions/apply": () => ({ changeset: "CS-5", applied: 0, held: 0, refused: 1 }),
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  await user.click(await screen.findByRole("button", { name: "Make these changes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("No changes were made because one was refused.");
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.queryByText(/1 refused/)).toBeNull();
  expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
});

test("some refused but some applied is still reported as the usual summary", async () => {
  const user = userEvent.setup();
  fakeApi({
    [PREVIEW_URL]: () => proposal(),
    "POST plugin-actions/apply": () => ({ changeset: "CS-5", applied: 1, held: 0, refused: 1 }),
    "POST changesets/CS-5/undo": () => ({ restored: [], skipped: [] }),
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  await user.click(await screen.findByRole("button", { name: "Make these changes" }));
  expect(await screen.findByText("Make a note from notes.txt: 1 change made, 1 refused.")).toBeInTheDocument();
});

test("if the review expired or the item changed, the dialog shows the server's text and Try again asks afresh", async () => {
  const user = userEvent.setup();
  let round = 0;
  const calls = fakeApi({
    [PREVIEW_URL]: () => proposal({ token: `tok-${++round}` }),
    "POST plugin-actions/apply": (body) =>
      (body as { token: string }).token === "tok-1"
        ? new Refuse(409, "that review has expired; run the action again")
        : { changeset: "CS-6", applied: 1, held: 0, refused: 0 },
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  await user.click(await screen.findByRole("button", { name: "Make these changes" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("that review has expired; run the action again");
  expect(screen.getByRole("button", { name: "Make these changes" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  await waitFor(() => expect(screen.getByRole("button", { name: "Make these changes" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "Make these changes" }));
  expect(await screen.findByText("Make a note from notes.txt: 1 change made.")).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "POST plugin-actions/apply").map((c) => c.body)).toEqual([{ token: "tok-1" }, { token: "tok-2" }]);
});

test("an action that can't make a proposal shows why, with no Apply to press", async () => {
  const user = userEvent.setup();
  fakeApi({ [PREVIEW_URL]: () => new Refuse(409, "Only plain text files can be turned into a note.") });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Only plain text files can be turned into a note.");
  expect(screen.getByRole("dialog", { name: "Make a note" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Make these changes" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

const kept = (items: S["ActionItem"][], ticks: Record<string, boolean>) => items.map((i) => ({ ...i, kept: ticks[i.id] ?? i.kept }));

const ITEMS: S["ActionItem"][] = [
  { id: "i1", label: "Change the first thing", group: "g1", kept: true, ops: [{ op: "note", label: "Note one" }] },
  { id: "i2", label: "Change the second thing", group: "g1", kept: true, ops: [{ op: "note", label: "Note two" }] },
  { id: "i3", label: "Change the third thing", group: "g1", kept: false, ops: [{ op: "note", label: "Note three" }] },
  { id: "i4", label: "A loose thing", group: null, kept: true, ops: [] },
];
const GROUPS: S["ActionGroup"][] = [
  { id: "g1", heading: "Likely duplicates", explanation: "These look like things you already have." },
  { id: "g2", heading: "Empty group", explanation: "Nothing in here." },
];

test("items sit under their group's heading and explanation with a count, and ticking does not ask again", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    [PREVIEW_URL]: () =>
      proposal({
        items: ITEMS,
        groups: GROUPS,
        ops: [
          { op: "note", label: "Note one" },
          { op: "note", label: "Note two" },
        ],
      }),
    "POST plugin-actions/apply": () => ({ changeset: "CS-7", applied: 2, held: 0, refused: 0 }),
    "POST changesets/CS-7/undo": () => ({ restored: [{ kind: "note", id: "N-1" }], skipped: [] }),
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const dialog = await screen.findByRole("dialog");
  const group = (await within(dialog).findByRole("region", { name: "Likely duplicates" })) as HTMLElement;
  expect(within(group).getByText("These look like things you already have.")).toBeInTheDocument();
  expect(within(group).getByText("2 of 3 kept")).toBeInTheDocument();
  expect(within(group).getByRole("checkbox", { name: "Change the first thing" })).toBeChecked();
  expect(within(group).getByRole("checkbox", { name: "Change the third thing" })).not.toBeChecked();
  expect(within(dialog).queryByRole("region", { name: "Empty group" })).toBeNull();
  const loose = within(dialog).getByRole("region", { name: "Pick what to keep" });
  expect(within(loose).getByText("1 of 1 kept")).toBeInTheDocument();

  await user.click(within(group).getByRole("checkbox", { name: "Change the first thing" }));
  expect(within(group).getByText("1 of 3 kept")).toBeInTheDocument();
  const changes = within(dialog).getByRole("region", { name: "What it will change" });
  expect(within(changes).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Note two"]);
  expect(calls.filter((c) => c.route === PREVIEW_URL)).toHaveLength(1);

  await user.click(within(dialog).getByRole("button", { name: "Make these changes" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(calls.find((c) => c.route === "POST plugin-actions/apply")?.body).toEqual({
    token: "tok-1",
    kept: { i1: false, i2: true, i3: false, i4: true },
  });
});

test("Keep all and Drop all in a group's menu set every item in it", async () => {
  const user = userEvent.setup();
  fakeApi({ [PREVIEW_URL]: () => proposal({ items: ITEMS, groups: GROUPS }) });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const group = (await screen.findByRole("region", { name: "Likely duplicates" })) as HTMLElement;
  await user.click(within(group).getByRole("button", { name: "More actions for Likely duplicates" }));
  await user.click(await screen.findByRole("menuitem", { name: "Drop all" }));
  expect(within(group).getByText("0 of 3 kept")).toBeInTheDocument();
  for (const box of within(group).getAllByRole("checkbox")) expect(box).not.toBeChecked();
  await user.click(within(group).getByRole("button", { name: "More actions for Likely duplicates" }));
  await user.click(await screen.findByRole("menuitem", { name: "Keep all" }));
  expect(within(group).getByText("3 of 3 kept")).toBeInTheDocument();
});

test("a changed choice asks again with the previous review and the ticks, and the ticks carry over", async () => {
  const user = userEvent.setup();
  let n = 0;
  const calls = fakeApi({
    [PREVIEW_URL]: (body) => {
      const run = body as { choices: Record<string, string | boolean>; kept?: Record<string, boolean> };
      const style = (run.choices.style as string) ?? "short";
      return proposal({
        token: `tok-${++n}`,
        items: kept(ITEMS, run.kept ?? {}),
        groups: GROUPS,
        choices: [
          { id: "style", label: "Style", value: style, options: [{ value: "short", label: "Short" }, { value: "long", label: "Long" }], help: "", text: false, max_length: 200, group: "g1" },
        ],
      });
    },
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const group = (await screen.findByRole("region", { name: "Likely duplicates" })) as HTMLElement;
  expect(within(group).getByRole("combobox", { name: "Style" })).toBeInTheDocument();
  await user.click(within(group).getByRole("checkbox", { name: "Change the first thing" }));
  await user.selectOptions(within(group).getByRole("combobox", { name: "Style" }), "long");
  await waitFor(() => expect(within(group).getByRole("combobox", { name: "Style" })).toHaveValue("long"));
  await waitFor(() => expect(calls.filter((c) => c.route === PREVIEW_URL)).toHaveLength(2));
  const second = calls.filter((c) => c.route === PREVIEW_URL)[1].body;
  expect(second).toEqual({
    target,
    choices: { style: "long" },
    previous: "tok-1",
    kept: { i1: false, i2: true, i3: false, i4: true },
  });
  await waitFor(() => expect(within(group).getByText("1 of 3 kept")).toBeInTheDocument());
  expect(within(group).getByRole("checkbox", { name: "Change the first thing" })).not.toBeChecked();
});

test("a typed choice asks again on Enter or when the field is left with a changed value, not otherwise", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    [PREVIEW_URL]: (body) => {
      const title = ((body as { choices: Record<string, string> }).choices.title as string) ?? "Draft";
      return proposal({
        summary: `Make a note (${title})`,
        choices: [{ id: "title", label: "Title", value: title, options: [], help: "", text: true, max_length: 12 }],
      });
    },
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const input = await screen.findByRole("textbox", { name: "Title" });
  expect(input).toHaveValue("Draft");
  expect(input).toHaveAttribute("maxlength", "12");
  const asked = () => calls.filter((c) => c.route === PREVIEW_URL).length;
  await user.click(input);
  await user.tab();
  expect(asked()).toBe(1);
  await user.clear(input);
  await user.type(input, "Plan{Enter}");
  await screen.findByRole("dialog", { name: "Make a note (Plan)" });
  expect(asked()).toBe(2);
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("Plan");
  await user.type(screen.getByRole("textbox", { name: "Title" }), "ning");
  await user.tab();
  await screen.findByRole("dialog", { name: "Make a note (Planning)" });
  expect(asked()).toBe(3);
});

test("work the action also starts is listed with what it is about, and says each waits for the go", async () => {
  const user = userEvent.setup();
  fakeApi({
    [PREVIEW_URL]: () =>
      proposal({
        requests: [
          { id: "r1", kept: true, task: "demo/check", label: "Check the chapter", about: { kind: "demo/chapter", id: "CH-1" }, note: "" },
          { id: "r2", kept: true, task: "demo/other", label: "Summarize everything", about: null, note: "" },
        ],
      }),
    "GET record?kind=demo%2Fchapter&id=CH-1": () => ({ kind: "demo/chapter", id: "CH-1", version: 1, fields: { title: "The first chapter" }, long_text: [] }),
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const section = (await screen.findByRole("region", { name: "Additional work" })) as HTMLElement;
  expect(await within(section).findByText("Check the chapter (about The first chapter)")).toBeInTheDocument();
  expect(within(section).getByText("Summarize everything")).toBeInTheDocument();
  expect(within(section).getByText("2 of 2 AI tasks wait for you to start them.")).toBeInTheDocument();
});

test("an item that can't apply says why and starts dropped, and other problems are listed", async () => {
  const user = userEvent.setup();
  fakeApi({
    [PREVIEW_URL]: () =>
      proposal({
        items: [
          { id: "a", label: "Add Harbor", group: null, kept: true, ops: [{ op: "project.add", label: "Add Harbor" }] },
          {
            id: "b",
            label: "Add Lighthouse",
            group: null,
            kept: false,
            refused: "there is already a project called Lighthouse",
            ops: [{ op: "project.add", label: "Add Lighthouse" }],
          },
        ],
        problems: ["there is already a project called Lighthouse"],
      }),
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const dialog = await screen.findByRole("dialog");
  const refused = await within(dialog).findByRole("checkbox", { name: "Add Lighthouse" });
  expect(refused).not.toBeChecked();
  expect(refused).toHaveAccessibleDescription("Can't make this change: there is already a project called Lighthouse");
  expect(within(dialog).getByRole("alert")).toHaveTextContent("Update your choices");
});

type Req = S["ActionRequestView"];
const req = (id: string, extra: Partial<Req> = {}): Req => ({ id, kept: true, task: "demo/check", label: `Check ${id}`, about: null, note: "", ...extra });
const APPLY = "POST plugin-actions/apply";
const applied = () => ({ changeset: "CS-1", applied: 1, held: 0, refused: 0 });

async function openWith(extra: Partial<S["ActionProposalView"]>) {
  const user = userEvent.setup();
  const calls = fakeApi({ [PREVIEW_URL]: () => proposal(extra), [APPLY]: applied });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const section = (await screen.findByRole("region", { name: "Additional work" })) as HTMLElement;
  const dialog = screen.getByRole("dialog");
  const applyBody = async () => {
    await user.click(within(dialog).getByRole("button", { name: "Make these changes" }));
    await waitFor(() => expect(calls.some((c) => c.route === APPLY)).toBe(true));
    return calls.find((c) => c.route === APPLY)?.body;
  };
  return { user, calls, section, dialog, applyBody };
}

test("each piece of queued work has a tick, ticked as offered, and an untick is sent as that id false", async () => {
  const { user, section, applyBody } = await openWith({ requests: [req("r1"), req("r2"), req("r3", { kept: false })] });
  const boxes = within(section).getAllByRole("checkbox");
  expect(boxes.map((b) => (b as HTMLInputElement).checked)).toEqual([true, true, false]);
  expect(within(section).getAllByRole("listitem")).toHaveLength(3);
  expect(within(section).getByText("2 of 3 AI tasks wait for you to start them.")).toBeInTheDocument();
  await user.click(within(section).getByRole("checkbox", { name: "Check r2" }));
  expect(within(section).getByText("1 of 3 AI tasks wait for you to start them.")).toBeInTheDocument();
  expect(await applyBody()).toEqual({ token: "tok-1", kept_requests: { r2: false } });
});

test("nothing about queued work is sent when the person changed none", async () => {
  const { applyBody } = await openWith({ requests: [req("r1")] });
  expect(await applyBody()).toEqual({ token: "tok-1" });
});

test("work that goes with an item follows it: dropped with the item, disabled, with a hint, and free again when kept", async () => {
  const items: S["ActionItem"][] = [{ id: "i1", label: "Change the first thing", group: null, kept: true, ops: [] }];
  const { user, dialog, section, applyBody } = await openWith({
    items,
    requests: [req("r1", { item: "i1" }), req("r2", { item: "i1", label: "Also check the second" }), req("r3")],
  });
  const first = within(section).getByRole("checkbox", { name: "Check r1" });
  expect(first).toBeEnabled();
  await user.click(within(section).getByRole("checkbox", { name: "Also check the second" }));
  await user.click(within(dialog).getByRole("checkbox", { name: "Change the first thing" }));
  expect(first).not.toBeChecked();
  expect(first).toBeDisabled();
  expect(first).toHaveAccessibleDescription("Part of Change the first thing");
  expect(within(section).getByRole("checkbox", { name: "Check r3" })).toBeEnabled();
  expect(within(section).getByText("1 of 3 AI tasks wait for you to start them.")).toBeInTheDocument();
  await user.click(within(dialog).getByRole("checkbox", { name: "Change the first thing" }));
  expect(first).toBeEnabled();
  expect(first).toBeChecked();
  // The one the person unticked stays unticked.
  expect(within(section).getByRole("checkbox", { name: "Also check the second" })).not.toBeChecked();
  await user.click(within(dialog).getByRole("checkbox", { name: "Change the first thing" }));
  expect(await applyBody()).toEqual({
    token: "tok-1",
    kept: { i1: false },
    kept_requests: { r1: false, r2: false },
  });
});

test("a group's Keep all and Drop all set the work that belongs to the group", async () => {
  const user = userEvent.setup();
  fakeApi({
    [PREVIEW_URL]: () =>
      proposal({ items: ITEMS, groups: GROUPS, requests: [req("r1", { group: "g1" }), req("r2", { group: "g1" }), req("r3")] }),
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const group = (await screen.findByRole("region", { name: "Likely duplicates" })) as HTMLElement;
  const section = screen.getByRole("region", { name: "Additional work" });
  await user.click(within(group).getByRole("button", { name: "More actions for Likely duplicates" }));
  await user.click(await screen.findByRole("menuitem", { name: "Drop all" }));
  expect(within(section).getAllByRole("checkbox").map((b) => (b as HTMLInputElement).checked)).toEqual([false, false, true]);
  await user.click(within(section).getByRole("checkbox", { name: "Check r1" }));
  expect(within(section).getAllByRole("checkbox").map((b) => (b as HTMLInputElement).checked)).toEqual([true, false, true]);
  await user.click(within(group).getByRole("button", { name: "More actions for Likely duplicates" }));
  await user.click(await screen.findByRole("menuitem", { name: "Keep all" }));
  expect(within(section).getAllByRole("checkbox").map((b) => (b as HTMLInputElement).checked)).toEqual([true, true, true]);
});

test("more than five pieces of work get Keep all and Drop all, and fewer do not", async () => {
  const many = Array.from({ length: 6 }, (_, i) => req(`r${i + 1}`));
  const { user, section, applyBody } = await openWith({ requests: many });
  expect(within(section).getByText("6 of 6 kept")).toBeInTheDocument();
  await user.click(within(section).getByRole("button", { name: "More actions for Additional work" }));
  await user.click(await screen.findByRole("menuitem", { name: "Drop all" }));
  expect(within(section).getByText("0 of 6 kept")).toBeInTheDocument();
  expect(within(section).getByText("0 of 6 AI tasks wait for you to start them.")).toBeInTheDocument();
  for (const box of within(section).getAllByRole("checkbox")) expect(box).not.toBeChecked();
  await user.click(within(section).getByRole("button", { name: "More actions for Additional work" }));
  await user.click(await screen.findByRole("menuitem", { name: "Keep all" }));
  expect(within(section).getByText("6 of 6 AI tasks wait for you to start them.")).toBeInTheDocument();
  await user.click(within(section).getByRole("checkbox", { name: "Check r4" }));
  expect(await applyBody()).toEqual({ token: "tok-1", kept_requests: { r4: false } });
});

test("five pieces of work or fewer have no Keep all and Drop all", async () => {
  const { section } = await openWith({ requests: Array.from({ length: 5 }, (_, i) => req(`r${i + 1}`)) });
  expect(within(section).queryByRole("button", { name: /More actions/ })).toBeNull();
});

test("a proposal that only adds a file has no 'what it will change' line saying it changes nothing", async () => {
  const user = userEvent.setup();
  fakeApi({
    [PREVIEW_URL]: () => proposal({ ops: [], files: [{ name: "result.txt", media_type: "text/plain", size: 10, file_kind: "attachment" }] }),
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const dialog = await screen.findByRole("dialog", { name: "Make a note from notes.txt" });
  expect(await within(dialog).findByText(/result\.txt/)).toBeInTheDocument();
  expect(within(dialog).queryByText("What it will change")).toBeNull();
  expect(within(dialog).queryByText("It won't change anything.")).toBeNull();
});

test("a proposal with nothing at all still says it changes nothing", async () => {
  const user = userEvent.setup();
  fakeApi({ [PREVIEW_URL]: () => proposal({ ops: [] }) });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  const dialog = await screen.findByRole("dialog", { name: "Make a note from notes.txt" });
  expect(await within(dialog).findByText("It won't change anything.")).toBeInTheDocument();
});
