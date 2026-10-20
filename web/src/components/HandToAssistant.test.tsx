import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { person, project } from "../lib/records-fixtures";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { OpenItems } from "./OpenItems";

// Handing an action to the assistant from its row (design 7.5): the assistant drafts the work as a pending draft, under the
// usual estimate and go; the to-do stays the person's. The row says where the work stands.

const action: S["OpenActionView"] = {
  id: "A-1",
  version: 3,
  text: "Send the proof to the printer",
  state: "open",
  owners: [{ person: "P-1", name: "Quinn Sample" }],
  due: null,
  project: "PRJ-1",
  project_name: "Harbor",
  parent_name: null,
  notes: null,
  since: "2026-10-01",
  on_hold: null,
  blocker: null,
  duplicate: null,
  origin: null,
  untouched_days: null,
  owner_question: null,
  to_send: false,
};

const handed = (over: Partial<S["HandedActionView"]> = {}): S["HandedActionView"] => ({ action: "A-1", request: "R-1", state: "working", draft: null, estimate_usd: null, ...over });

function api(extra: Routes = {}, lines: S["HandedActionView"][] = []) {
  return fakeApi({
    "GET open-items": () => ({ actions: [action], questions: [], stale_days: 21 }),
    "GET people": () => [person("P-1", "Quinn Sample")],
    "GET projects": () => [project("PRJ-1", "Harbor")],
    "GET actions/handed": () => lines,
    "POST actions/A-1/hand-over": () => ({ request: "R-1" }),
    ...extra,
  });
}

const menu = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(await screen.findByRole("button", { name: /More actions for Send the proof/ }));
};

test("Hand to the assistant is in the row's menu, asks what is wanted with the cursor in the field, and hands it over with the words", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  await menu(user);
  await user.click(await screen.findByRole("menuitem", { name: "Hand to the assistant" }));
  const box = await screen.findByRole("textbox", { name: /What do you want from it/ });
  await waitFor(() => expect(box).toHaveFocus());
  expect(screen.getByText(/The to-do stays yours until you close it/)).toBeInTheDocument();
  await user.type(box, "Three lines, to the printer.");
  await user.click(screen.getByRole("button", { name: "Hand it over" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/A-1/hand-over")?.body).toEqual({ note: "Three lines, to the printer." }));
  expect(await screen.findByText(/Handed to Helper/)).toBeInTheDocument();
  // Nothing about the to-do itself was changed.
  expect(calls.filter((c) => c.route.startsWith("POST") && c.route !== "POST actions/A-1/hand-over")).toHaveLength(0);
});

test("with no words the request carries none, and Escape closes the form without handing anything over", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  await menu(user);
  await user.click(await screen.findByRole("menuitem", { name: "Hand to the assistant" }));
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("textbox", { name: /What do you want from it/ })).toBeNull();
  await menu(user);
  await user.click(await screen.findByRole("menuitem", { name: "Hand to the assistant" }));
  await user.click(await screen.findByRole("button", { name: "Hand it over" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/A-1/hand-over")?.body).toEqual({}));
});

test("an action the assistant has in hand says so on its row and no longer offers to be handed over", async () => {
  const user = userEvent.setup();
  api({}, [handed()]);
  renderApp(<OpenItems />);
  const row = (await screen.findByText("Send the proof to the printer")).closest("li, div[data-row]") as HTMLElement;
  expect(await within(row).findByText("Helper is drafting this")).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: /More actions for Send the proof/ }));
  expect(screen.queryByRole("menuitem", { name: "Hand to the assistant" })).toBeNull();
});

test("a draft held for the person's go says so with the estimate", async () => {
  api({}, [handed({ state: "needs_go", estimate_usd: 0.31 })]);
  renderApp(<OpenItems />);
  expect(await screen.findByText(/Waiting for your go to draft this · about \$0\.31/)).toBeInTheDocument();
});

test("a draft ready for review is one button away: Review the draft opens it", async () => {
  const user = userEvent.setup();
  const calls = api(
    {
      "GET text-versions/TV-1/review": () => ({
        version: { id: "TV-1", number: 1, status: "pending", source: "draft", words: 4, created_at: "2026-10-14T10:00:00Z", note: null, questions: [], unmapped: [], authorship: [], read_version: 1 },
        current: null,
        three_way: false,
        regions: [],
        pending_text: "Hello,\n\nThe proof is attached.",
      }),
    },
    [handed({ state: "draft", draft: "TV-1" })],
  );
  renderApp(<OpenItems />);
  expect(await screen.findByText("A draft is ready for you")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Review the draft" }));
  await waitFor(() => expect(calls.some((c) => c.route === "GET text-versions/TV-1/review")).toBe(true));
});

test("a refusal from the server is told in its own words, the form stays open and nothing is shown as handed over", async () => {
  const user = userEvent.setup();
  api({ "POST actions/A-1/hand-over": () => new Refuse(409, "The assistant already has this action's work in hand.") });
  renderApp(<OpenItems />);
  await menu(user);
  await user.click(await screen.findByRole("menuitem", { name: "Hand to the assistant" }));
  await user.click(await screen.findByRole("button", { name: "Hand it over" }));
  expect(await screen.findByText(/That didn't work\. The assistant already has this action's work in hand\./)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: /What do you want from it/ })).toBeInTheDocument();
  expect(screen.queryByText(/Handed to Helper/)).toBeNull();
});
