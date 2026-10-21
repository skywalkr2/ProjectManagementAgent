import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartProvider } from "../lib/restart";
import { Refuse, fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Handover } from "./Handover";

const view = (over: Partial<S["HandoverView"]> = {}): S["HandoverView"] => ({
  state: "diverged",
  here: { computer: "Desk", changes: 7, latest: "2026-10-12T16:10:00-05:00" },
  folder: { computer: "Laptop", changes: 1, latest: "2026-10-11T09:05:00-05:00" },
  computer: "",
  last_seen: null,
  minutes_left: 0,
  chosen: null,
  ...over,
});

function show(first: S["HandoverView"], routes: (set: (page: S["HandoverView"]) => S["HandoverView"]) => Routes = () => ({}), canRestart = true) {
  // What the server would answer next: a choice or taking it back changes it.
  let page = first;
  const set = (next: S["HandoverView"]) => (page = next);
  const calls = fakeApi({
    "GET sync/handover": () => page,
    "GET status": () => statusFixture({ can_restart: canRestart }),
    "GET runtime-config": () => ({ instance: null }),
    ...routes(set),
  });
  renderApp(
    <RestartProvider hellos={1}>
      <Handover />
    </RestartProvider>,
  );
  return calls;
}

test("both sides are said in plain words, each with its count, its computer and its latest change", async () => {
  show(view());
  expect(await screen.findByRole("heading", { name: "Which copy to keep" })).toBeInTheDocument();
  expect(await screen.findByText(/No changes have been combined/)).toBeInTheDocument();
  const sides = screen.getAllByRole("listitem").filter((li) => /change/.test(li.textContent ?? ""));
  expect(sides[0]).toHaveTextContent("This computer");
  expect(sides[0]).toHaveTextContent("Made on Desk");
  expect(sides[0]).toHaveTextContent("7 changes the other copy doesn't have");
  expect(sides[0]).toHaveTextContent(/The latest was made \w{3}, \w{3} 12, 4:10\s?PM\./);
  expect(sides[1]).toHaveTextContent("The synced folder");
  expect(sides[1]).toHaveTextContent("1 change the other copy doesn't have");
  expect(document.body.textContent).not.toMatch(/cockpit|keep --|--here|--folder/);
});

test("each choice says what it does, and the cursor starts on the first", async () => {
  show(view());
  const here = await screen.findByRole("button", { name: "Keep this computer's copy" });
  expect(here).toHaveFocus();
  expect(screen.getByText(/The synced folder's copy is backed up, then replaced with this computer's copy/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Keep the synced folder's copy" })).toBeInTheDocument();
  expect(screen.getByText(/This computer's copy is backed up, then replaced with the folder's/)).toBeInTheDocument();
});

test("choosing notes the choice and then asks for the restart, which only the click starts", async () => {
  const user = userEvent.setup();
  const calls = show(view(), (set) => ({
    "POST sync/handover": () => set(view({ state: "chosen", chosen: "folder" })),
    "POST restart": () => ({ restarting: true }),
  }));
  await user.click(await screen.findByRole("button", { name: "Keep the synced folder's copy" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST sync/handover")!.body).toEqual({ which: "folder" }));
  expect(await screen.findByText("You chose to keep the synced folder's copy.")).toBeInTheDocument();
  expect(screen.getByText(/You can change it until then/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Keep this computer's copy" })).toBeNull();
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
  await user.click(await screen.findByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST restart")).toHaveLength(1));
});

test("a choice already noted shows as chosen, and Change my mind takes it back", async () => {
  const user = userEvent.setup();
  const calls = show(view({ state: "chosen", chosen: "here" }), (set) => ({ "DELETE sync/handover": () => set(view()) }));
  expect(await screen.findByText("You chose to keep this computer's copy.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Change my mind" }));
  await waitFor(() => expect(calls.some((c) => c.route === "DELETE sync/handover")).toBe(true));
  expect(await screen.findByRole("button", { name: "Keep this computer's copy" })).toBeInTheDocument();
});

test("when the app can't restart itself the page says to close and start it, with no restart button", async () => {
  show(view({ state: "chosen", chosen: "folder" }), () => ({}), false);
  expect(await screen.findByText(/Close and reopen the app to keep your chosen copy/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Restart now" })).toBeNull();
});

test("a refusal, such as the other computer being open, is shown in the server's words", async () => {
  const user = userEvent.setup();
  show(view(), () => ({
    "POST sync/handover": () => new Refuse(409, "The workspace is open on the other computer. Close it there first."),
  }));
  await user.click(await screen.findByRole("button", { name: "Keep this computer's copy" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("The workspace is open on the other computer. Close it there first.");
  expect(screen.getByRole("button", { name: "Keep this computer's copy" })).toBeInTheDocument();
});

test("a workspace open on another computer shows who, since when and the wait, and offers no choice", async () => {
  show(view({ state: "elsewhere", here: null, folder: null, computer: "Laptop", last_seen: "2026-10-12T16:10:00-05:00", minutes_left: 6 }));
  expect(await screen.findByText(/Laptop opened your work, so this computer stopped saving to the synced folder/)).toBeInTheDocument();
  expect(screen.getByText(/Last connected \w{3}, \w{3} 12, 4:10\s?PM\./)).toBeInTheDocument();
  expect(screen.getByText("If it is off or asleep, the workspace can be opened here in about 6 minutes.")).toBeInTheDocument();
  expect(screen.getByText(/You may need to choose one to keep/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Keep/ })).toBeNull();
});

test("with nothing to settle it says so", async () => {
  show(view({ state: "clear", here: null, folder: null }));
  expect(await screen.findByText(/Both copies match/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Keep/ })).toBeNull();
});

test("a page that doesn't load can be tried again", async () => {
  const user = userEvent.setup();
  let ok = false;
  show(view(), () => ({ "GET sync/handover": () => (ok ? view() : new Refuse(500, "no")) }));
  const retry = await screen.findByRole("button", { name: "Try again" });
  ok = true;
  await user.click(retry);
  expect(await within(document.body).findByRole("button", { name: "Keep this computer's copy" })).toBeInTheDocument();
});

test("a side with no changes of its own says nothing about a count, never \"0 changes\"", async () => {
  show(view({ folder: { computer: "Laptop", changes: 0, latest: null } }));
  expect(await screen.findByRole("heading", { name: "Which copy to keep" })).toBeInTheDocument();
  expect(await screen.findByText(/7 changes the other copy doesn't have/)).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/\b0 changes?\b/);
});
