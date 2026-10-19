import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { WorkingCopies } from "./WorkingCopies";

const KIND = "demo/chapter";
const ID = "CH-1";
const FIELD = "body_text";
const formats = `working-copies/formats?kind=${encodeURIComponent(KIND)}&field=${FIELD}`;
const list = `working-copies?kind=${encodeURIComponent(KIND)}&id=${ID}`;

function copy(extra: Partial<S["WorkingCopyView"]> = {}): S["WorkingCopyView"] {
  return {
    id: "WC-1",
    format: "demo/word",
    label: "Word file",
    field: FIELD,
    base: 1,
    status: "out",
    stale: false,
    file: "FILE-9",
    proposal: null,
    handed_at: "2026-10-09T14:00:00Z",
    returned_at: null,
    ...extra,
  };
}

function show(routes: Routes, onReview = vi.fn()) {
  const calls = fakeApi({
    [`GET ${formats}`]: () => [{ name: "demo/word", label: "Word file", extension: "docx" }],
    [`GET ${list}`]: () => [],
    ...routes,
  });
  renderApp(<WorkingCopies kind={KIND} id={ID} field={FIELD} onReview={onReview} />);
  return { calls, onReview };
}

test("each format has a Hand out button; after it, there is a link to download the file", async () => {
  const user = userEvent.setup();
  const { calls } = show({ "POST working-copies": () => copy({ file: "FILE 9" }) });
  await user.click(await screen.findByRole("button", { name: "Open a working copy as Word file" }));
  const link = await screen.findByRole("link", { name: "Download" });
  expect(link).toHaveAttribute("href", "api/files/FILE%209/content");
  expect(calls.find((c) => c.route === "POST working-copies")?.body).toEqual({ format: "demo/word", kind: KIND, id: ID, field: FIELD });
});

test("copies are listed in words, an out-of-date one says so, and only copies that are out have actions", async () => {
  show({
    [`GET ${list}`]: () => [
      copy({ stale: true }),
      copy({ id: "WC-2", status: "returned", label: "Word file" }),
      copy({ id: "WC-3", status: "dropped" }),
      copy({ id: "WC-4", field: "other_field" }),
    ],
  });
  const rows = await screen.findAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("Out with you");
  expect(rows[0]).toHaveTextContent("Out of date");
  expect(within(rows[0]).getByRole("button", { name: "Bring back your edits to Word file" })).toBeInTheDocument();
  expect(rows[1]).toHaveTextContent("Brought back");
  expect(within(rows[1]).queryByRole("button")).toBeNull();
});

test("bringing a file back sends its bytes with its name and opens the review of what came back", async () => {
  const user = userEvent.setup();
  const { calls, onReview } = show({
    [`GET ${list}`]: () => [copy()],
    "POST working-copies/WC-1/return?name=chapter%201.docx": () => ({ unchanged: false, version: "V-5", unmapped: [] }),
  });
  await screen.findByRole("button", { name: "Bring back your edits to Word file" });
  const file = new File(["edited bytes"], "chapter 1.docx", { type: "application/octet-stream" });
  await user.upload(screen.getByLabelText("Choose the file with your edits to Word file"), file);
  await waitFor(() => expect(onReview).toHaveBeenCalledWith("V-5", expect.any(Function)));
  expect(calls.find((c) => c.route.startsWith("POST working-copies/WC-1/return"))?.body).toBe(file);
});

test("a file that came back unchanged says so and opens nothing", async () => {
  const user = userEvent.setup();
  const { onReview } = show({
    [`GET ${list}`]: () => [copy()],
    "POST working-copies/WC-1/return?name=same.docx": () => ({ unchanged: true, version: null, unmapped: [] }),
  });
  await screen.findByRole("button", { name: "Bring back your edits to Word file" });
  await user.upload(screen.getByLabelText("Choose the file with your edits to Word file"), new File(["x"], "same.docx"));
  expect(await screen.findByText("Word file came back as it left, so nothing changed.")).toBeInTheDocument();
  expect(onReview).not.toHaveBeenCalled();
});

test("Set aside is in the row's menu and acts at once", async () => {
  const user = userEvent.setup();
  const { calls } = show({ [`GET ${list}`]: () => [copy()], "POST working-copies/WC-1/drop": () => ({ ok: "WC-1" }) });
  await user.click(await screen.findByRole("button", { name: /^More actions/ }));
  await user.click(screen.getByRole("menuitem", { name: "Set aside" }));
  expect(await screen.findByText("Set aside Word file.")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST working-copies/WC-1/drop")).toBe(true);
});

test("nothing shows for a text no program can be handed out for and with no copies", async () => {
  const { calls } = show({ [`GET ${formats}`]: () => [] });
  await waitFor(() => expect(calls.length).toBe(2));
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(screen.queryByRole("heading")).toBeNull();
});
