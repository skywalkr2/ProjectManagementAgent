import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { PageLinks } from "./PageLinks";

// The list of the person's own pages, in Settings → Appearance (design 7.9): a name and a web address each, saved as it is
// made with Undo. The header shows them (HeaderLinks.test.tsx).

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";
const board = { name: "Planning board", address: `${WEB}boards.example.org/plan` };
const schedule = { name: "Team schedule", address: `${WEB}schedule.example.org/team` };

const item = (value: unknown): S["SettingItem"] => ({
  key: "ui.links",
  file: "ui",
  group: "ui",
  description: "Links to your own pages.",
  type: "other",
  options: [],
  value,
  default: [],
  source: "file",
  locked: false,
  basic: false,
  editable: true,
});

function show(initial: unknown, extra: Record<string, (body: unknown) => unknown> = {}) {
  let current = initial;
  let n = 1;
  const calls = fakeApi({
    "GET settings": () => ({ fingerprint: `fp-${n}`, items: [item(current)] }),
    "POST settings": (body) => {
      const sent = body as S["SettingsSave"];
      const before = current;
      current = (sent.changes as Record<string, unknown>)["ui.links"];
      n += 1;
      return { changes: [{ key: "ui.links", before, after: current, was_default: false, is_default: false }], fingerprint: `fp-${n}`, needs_restart: false };
    },
    ...extra,
  });
  renderApp(<PageLinks />);
  return calls;
}

const sent = (calls: ReturnType<typeof fakeApi>) => calls.filter((c) => c.route === "POST settings").map((c) => (c.body as S["SettingsSave"]).changes);

test("each saved link is a row with its name and address and a way to remove it", async () => {
  show([board, schedule]);
  const list = await screen.findByRole("list", { name: "Your pages" });
  const rows = within(list).getAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("Planning board");
  expect(rows[0]).toHaveTextContent(board.address);
  expect(within(rows[1]).getByRole("button", { name: "Remove Team schedule" })).toBeInTheDocument();
});

test("a page is added from a name and an address, saved at once with Undo", async () => {
  const user = userEvent.setup();
  const calls = show([board]);
  const name = await screen.findByRole("textbox", { name: "Name" });
  await user.type(name, "Team schedule");
  await user.type(screen.getByRole("textbox", { name: "Address" }), schedule.address);
  await user.click(screen.getByRole("button", { name: "Add this page" }));
  await waitFor(() => expect(sent(calls)).toEqual([{ "ui.links": [board, schedule] }]));
  expect(await screen.findByText(/Team schedule added to your pages/)).toBeInTheDocument();
  // The form is empty again and the new row is there.
  expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("");
  expect(await screen.findByText(schedule.address)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(sent(calls).pop()).toEqual({ "ui.links": [board] }));
});

test("removing a page saves at once with Undo, and leaves the others", async () => {
  const user = userEvent.setup();
  const calls = show([board, schedule]);
  await user.click(await screen.findByRole("button", { name: "Remove Planning board" }));
  await waitFor(() => expect(sent(calls)).toEqual([{ "ui.links": [schedule] }]));
  expect(await screen.findByText(/Planning board removed from your pages/)).toBeInTheDocument();
});

test("an address that is not a web address is told in plain words and nothing is saved", async () => {
  const user = userEvent.setup();
  const calls = show([]);
  await user.type(await screen.findByRole("textbox", { name: "Name" }), "Odd one");
  await user.type(screen.getByRole("textbox", { name: "Address" }), "javascript:alert(1)");
  await user.click(screen.getByRole("button", { name: "Add this page" }));
  expect(await screen.findByText(/must start with http:\/\/ or https:\/\//)).toBeInTheDocument();
  expect(sent(calls)).toEqual([]);
});

test("a name or address left empty keeps the button from saving", async () => {
  const user = userEvent.setup();
  const calls = show([]);
  const add = await screen.findByRole("button", { name: "Add this page" });
  expect(add).toBeDisabled();
  await user.type(screen.getByRole("textbox", { name: "Name" }), "Only a name");
  expect(add).toBeDisabled();
  expect(sent(calls)).toEqual([]);
});

test("a refusal from the server is shown by the form, with what was typed kept", async () => {
  const user = userEvent.setup();
  show([], { "POST settings": () => new Refuse(409, "The settings changed since you opened them. Look again, then save.") });
  await user.type(await screen.findByRole("textbox", { name: "Name" }), "Planning board");
  await user.type(screen.getByRole("textbox", { name: "Address" }), board.address);
  await user.click(screen.getByRole("button", { name: "Add this page" }));
  expect(await screen.findByText(/The settings changed since you opened them/)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Planning board");
});
