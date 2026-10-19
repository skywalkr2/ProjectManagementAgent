import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { Files } from "./Files";

function file(id: string, name: string, extra: Partial<S["FileView"]> = {}): S["FileView"] {
  return {
    id,
    version: 1,
    name,
    media_type: "text/plain",
    size: 2048,
    file_kind: "attachment",
    kind_label: "Attachment",
    project: null,
    meta: {},
    origin: "upload",
    replaces: null,
    added_at: "2026-10-09T14:00:00Z",
    data_level: "internal",
    ...extra,
  };
}

const project: S["ProjectView"] = {
  id: "P-1",
  name: "Harbor project",
  group: null,
  status: null,
  phase: null,
  target: null,
  owner: null,
  owner_name: null,
  summary: null,
  language: "en-US",
  language_own: false,
  role: "run",
  completed: false,
  spent_usd: 0,
  open_actions: 0,
  open_questions: 0,
};

const action = { name: "demo/make-note", label: "Make a note from this file", on: "file" };
const workspaceAction = { name: "demo/tidy", label: "Tidy up", on: null };

const proposal = (summary: string): S["ActionProposalView"] => ({
  token: "tok-1",
  action: action.name,
  summary,
  ops: [{ op: "note", label: "Note: first line" }],
  files: [],
  previews: [],
  choices: [],
  notes: [],
  expires_at: "2026-10-09T15:00:00Z",
});

test("one row per file, with its facts in words and Open as the one primary action", async () => {
  fakeApi({
    "GET files": () => [
      file("FILE-2", "built.pdf", { size: 3 * 1024 * 1024, origin: "tool", kind_label: "Build", project: "P-1" }),
      file("FILE-1", "notes.txt"),
    ],
    "GET projects": () => [project],
    "GET plugin-actions": () => [],
    "GET plugin-actions?kind=file&id=FILE-2": () => [],
    "GET plugin-actions?kind=file&id=FILE-1": () => [],
  });
  renderApp(<Files />);
  const built = await screen.findByRole("listitem", { name: "built.pdf" });
  expect(within(built).getByText("Build")).toBeInTheDocument();
  expect(within(built).getByText(/^3 MB · In Harbor project · Added /)).toBeInTheDocument();
  expect(within(built).getByText("Created by software; review before using")).toBeInTheDocument();
  const open = within(built).getByRole("link", { name: "Open built.pdf in a new tab" });
  expect(open).toHaveAttribute("href", "api/files/FILE-2/content");
  expect(open).toHaveAttribute("target", "_blank");
  expect(open).toHaveAttribute("rel", expect.stringContaining("noopener"));
  const notes = screen.getByRole("listitem", { name: "notes.txt" });
  expect(within(notes).getByText(/^2 KB · Added /)).toBeInTheDocument();
  expect(within(notes).queryByText(/Untrusted/)).toBeNull();
  expect(screen.getAllByRole("listitem").map((li) => li.getAttribute("aria-labelledby"))).toEqual(["file-FILE-2", "file-FILE-1"]);
});

test("with no files it says so, and offers adding one", async () => {
  fakeApi({ "GET files": () => [], "GET projects": () => [], "GET plugin-actions": () => [] });
  renderApp(<Files />);
  expect(await screen.findByText(/^No files yet\./)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add a file" })).toBeInTheDocument();
});

test("when the files don't load it says so and Try again asks again", async () => {
  const user = userEvent.setup();
  let ok = false;
  fakeApi({
    "GET files": () => {
      if (!ok) throw new Error("down");
      return [file("FILE-1", "notes.txt")];
    },
    "GET projects": () => [],
    "GET plugin-actions": () => [],
    "GET plugin-actions?kind=file&id=FILE-1": () => [],
  });
  renderApp(<Files />);
  expect(await screen.findByText(/The files didn't load\./)).toBeInTheDocument();
  ok = true;
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("listitem", { name: "notes.txt" })).toBeInTheDocument();
});

test("a file's actions are in its menu and open the review for that file", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET files": () => [file("FILE-1", "notes.txt")],
    "GET projects": () => [],
    "GET plugin-actions": () => [],
    "GET plugin-actions?kind=file&id=FILE-1": () => [action],
    "POST plugin-actions/demo/make-note/preview": () => proposal("Make a note from notes.txt"),
  });
  renderApp(<Files />);
  const row = await screen.findByRole("listitem", { name: "notes.txt" });
  const more = await within(row).findByRole("button", { name: "More actions for notes.txt" });
  await user.click(more);
  await user.click(await screen.findByRole("menuitem", { name: "Make a note from this file" }));
  const dialog = await screen.findByRole("dialog", { name: "Make a note from notes.txt" });
  expect(within(dialog).getByText("Note: first line")).toBeInTheDocument();
  expect(calls.find((c) => c.route === "POST plugin-actions/demo/make-note/preview")?.body).toEqual({
    target: { kind: "file", id: "FILE-1" },
    choices: {},
  });
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await waitFor(() => expect(more).toHaveFocus());
});

test("actions for the whole workspace are buttons that review with no target", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET files": () => [],
    "GET projects": () => [],
    "GET plugin-actions": () => [workspaceAction],
    "POST plugin-actions/demo/tidy/preview": () => ({ ...proposal("Tidy up the workspace"), action: workspaceAction.name }),
  });
  renderApp(<Files />);
  const button = await screen.findByRole("button", { name: "Tidy up" });
  await user.click(button);
  await screen.findByRole("dialog", { name: "Tidy up the workspace" });
  expect(calls.find((c) => c.route === "POST plugin-actions/demo/tidy/preview")?.body).toEqual({ target: null, choices: {} });
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(button).toHaveFocus());
});
