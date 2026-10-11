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
          { name: "page.png", media_type: "image/png", caption: "First page", data_base64: png },
          { name: "page.txt", media_type: "text/plain", caption: "", data_base64: btoa("Line one\nLine two <b>not bold</b>") },
          { name: "page.html", media_type: "text/html", caption: "Hidden", data_base64: btoa("<b>never shown</b>") },
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
    { target, choices: { count: false, style: "short" } },
    { target, choices: { count: false, style: "long" } },
  ]);
  expect(screen.getByRole("combobox", { name: "Style" })).toHaveValue("long");
});

test("Apply applies exactly what was reviewed, says what happened in words and offers Undo", async () => {
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
  await user.click(await screen.findByRole("button", { name: "Apply" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(calls.find((c) => c.route === "POST plugin-actions/apply")?.body).toEqual({ token: "tok-1" });
  expect(await screen.findByText("Make a note from notes.txt: 2 changes made, 1 waiting for you.")).toBeInTheDocument();
  await waitFor(() => expect(start).toHaveFocus());
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-4/undo"));
  expect(await screen.findByText("Undone. It's back as it was.")).toBeInTheDocument();
});

test("when nothing applied there is nothing to undo", async () => {
  const user = userEvent.setup();
  fakeApi({
    [PREVIEW_URL]: () => proposal(),
    "POST plugin-actions/apply": () => ({ changeset: "CS-5", applied: 0, held: 0, refused: 1 }),
  });
  renderApp(<Harness />);
  await user.click(screen.getByRole("button", { name: "Start it" }));
  await user.click(await screen.findByRole("button", { name: "Apply" }));
  expect(await screen.findByText("Make a note from notes.txt: 1 refused.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
});

test("if the review expired or the item changed, the dialog shows the server's text and Run it again asks afresh", async () => {
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
  await user.click(await screen.findByRole("button", { name: "Apply" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("that review has expired; run the action again");
  expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Run it again" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  await waitFor(() => expect(screen.getByRole("button", { name: "Apply" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "Apply" }));
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
  expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});
