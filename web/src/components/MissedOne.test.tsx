import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RestartProvider } from "../lib/restart";
import { BottomBar } from "../shell/BottomBar";
import { Header } from "../shell/Header";
import { Refuse, fakeApi, rcFixture, renderApp, statusFixture } from "../test-utils";
import { MissedOneLine, MissedOneProvider } from "./MissedOne";
import { NothingNeedsYou } from "./Coverage";
import { SinceYesterday } from "./SinceYesterday";

// Missed one (design 6.32): a control in the header on every screen opens one small form, the cursor in its one field;
// sending says thanks and points at the request it made; the same form opens from the quiet screens and the phone's More
// sheet.

const noop = () => undefined;
const WORDS = "Dana said she would send the notes by Friday";

function header(routes: Parameters<typeof fakeApi>[0] = {}) {
  const calls = fakeApi({
    "GET status": () => statusFixture(),
    "GET me": () => ({ full_name: "Casey Example", person: null }),
    "GET runtime-config": () => ({ instance: null }),
    "GET changes": () => [{ id: "REQ-1" }],
    ...routes,
  });
  const rc = rcFixture({ workspace_name: "Example Workspace" });
  renderApp(
    <RestartProvider hellos={1}>
      <MissedOneProvider>
        <Header rc={rc} live={{ state: "live", lastUpdate: null, refresh: noop }} narrow={false} shortcuts={rc.shortcuts} onHandIn={noop} onAsk={noop} onHelp={noop} onFeedback={noop} onOpenGuide={noop} />
      </MissedOneProvider>
    </RestartProvider>,
  );
  return calls;
}

test("the header's Missed one opens the form with the cursor in its one field", async () => {
  const user = userEvent.setup();
  header();
  await user.click(await screen.findByRole("button", { name: "Missed one" }));
  const dialog = await screen.findByRole("dialog", { name: "Missed one" });
  const field = within(dialog).getByLabelText("What did I miss?");
  await waitFor(() => expect(field).toHaveFocus());
  expect(within(dialog).getByRole("button", { name: "Send" })).toBeDisabled();
});

test("sending posts the words, thanks the person in a toast that points at the request, and closes the form", async () => {
  const user = userEvent.setup();
  const calls = header({ "POST missed": () => ({ request: "REQ-9", signal: "SIG-3" }) });
  await user.click(await screen.findByRole("button", { name: "Missed one" }));
  const field = await screen.findByLabelText("What did I miss?");
  await user.type(field, WORDS);
  await user.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText("Thanks: I'll add it.")).toBeInTheDocument();
  expect(calls.find((c) => c.route === "POST missed")?.body).toEqual({ text: WORDS });
  expect(screen.getByRole("button", { name: "See it" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Missed one" })).toBeNull());
});

test("Enter sends, and a refusal keeps the form and what was typed", async () => {
  const user = userEvent.setup();
  header({ "POST missed": () => new Refuse(400, "Say what the assistant missed.") });
  await user.click(await screen.findByRole("button", { name: "Missed one" }));
  const field = await screen.findByLabelText("What did I miss?");
  await user.type(field, `${WORDS}{Enter}`);
  expect(await screen.findByText(/Say what the assistant missed\./)).toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: "Missed one" })).toBeInTheDocument();
  expect(screen.getByLabelText("What did I miss?")).toHaveValue(WORDS);
});

test("Escape closes the form without sending", async () => {
  const user = userEvent.setup();
  const calls = header();
  await user.click(await screen.findByRole("button", { name: "Missed one" }));
  await screen.findByLabelText("What did I miss?");
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Missed one" })).toBeNull());
  expect(calls.some((c) => c.route === "POST missed")).toBe(false);
});

test("an empty Today offers it beside what was read", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET coverage": () => null });
  renderApp(
    <MissedOneProvider>
      <NothingNeedsYou />
      <MissedOneLine />
    </MissedOneProvider>,
  );
  const line = document.querySelector<HTMLElement>("[data-missed-line]")!;
  expect(line).toHaveTextContent("Did Helper miss something?");
  await user.click(within(line).getByRole("button", { name: "Missed one" }));
  expect(await screen.findByRole("dialog", { name: "Missed one" })).toBeInTheDocument();
});

test("the empty list of what changed offers it too", async () => {
  fakeApi({
    "GET since-yesterday": () => ({ as_of: "2026-10-19T16:00:00Z", since: "2026-10-18T07:00:00Z", unseen: 0, entries: [] }),
    "GET today/queue": () => [],
  });
  renderApp(
    <MissedOneProvider>
      <SinceYesterday onOpenRecord={noop} />
    </MissedOneProvider>,
  );
  expect(await screen.findByText("Nothing changed since yesterday.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Missed one" })).toBeInTheDocument();
});

test("on a phone it is in the More sheet", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET panels": () => [], "GET changes": () => [{ id: "REQ-1" }], "GET followups": () => [] });
  renderApp(
    <MissedOneProvider>
      <BottomBar current="today" version="9.8.7" onHandIn={noop} onAsk={noop} onHelp={noop} onFeedback={noop} onOpenGuide={noop} />
    </MissedOneProvider>,
  );
  await user.click(screen.getByRole("button", { name: "More" }));
  await user.click(await screen.findByRole("button", { name: "Missed one" }));
  expect(await screen.findByRole("dialog", { name: "Missed one" })).toBeInTheDocument();
});
