import "@testing-library/jest-dom/vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { fakeApi } from "../test-utils";
import { WordingProvider } from "./wording";
import { RestartNotice, RestartProvider, useRestart } from "./restart";

function Starter() {
  const { begin } = useRestart();
  return (
    <button type="button" onClick={begin}>
      begin
    </button>
  );
}

function tree(hellos: number, seconds = 60) {
  return (
    <WordingProvider>
      <RestartProvider hellos={hellos} seconds={seconds} doneSeconds={0.2} pollSeconds={0.05}>
        <Starter />
        <RestartNotice />
      </RestartProvider>
    </WordingProvider>
  );
}

const SAYS = "Restarting to use the new settings…";
const DONE = "Restarted with the new settings.";
const STUCK = "The restart failed. Close and reopen the app to use the new settings.";

const begin = () => act(() => screen.getByRole("button", { name: "begin" }).click());

test("the live region is always there, and says nothing until a restart begins", () => {
  fakeApi({ "GET runtime-config": () => ({ instance: "one" }) });
  render(tree(1));
  expect(screen.getByRole("status")).toBeEmptyDOMElement();
});

test("with a server that can't name its start, the notice stays until the event stream says hello again", async () => {
  fakeApi({ "GET runtime-config": () => ({ instance: null }) });
  const { rerender } = render(tree(1));
  begin();
  expect(screen.getByRole("status")).toHaveTextContent(SAYS);
  rerender(tree(1));
  expect(screen.getByRole("status")).toHaveTextContent(SAYS);
  rerender(tree(2));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(DONE));
  await waitFor(() => expect(screen.getByRole("status")).toBeEmptyDOMElement());
});

test("a new start of the app says it restarted, briefly, then clears", async () => {
  let instance = "one";
  fakeApi({ "GET runtime-config": () => ({ instance }) });
  render(tree(1));
  begin();
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(SAYS));
  await new Promise((resolve) => setTimeout(resolve, 150));
  expect(screen.getByRole("status")).toHaveTextContent(SAYS);
  instance = "two";
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(DONE));
  await waitFor(() => expect(screen.getByRole("status")).toBeEmptyDOMElement());
});

test("the event stream reconnecting without a new start is not a restart", async () => {
  fakeApi({ "GET runtime-config": () => ({ instance: "one" }) });
  const { rerender } = render(tree(1, 0.5));
  begin();
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(SAYS));
  rerender(tree(2, 0.5));
  await new Promise((resolve) => setTimeout(resolve, 200));
  expect(screen.getByRole("status")).toHaveTextContent(SAYS);
});

test("requests that fail while the app is down are ignored until it answers as a new start", async () => {
  let up = true;
  let instance = "one";
  const down = new Error("down");
  fakeApi({
    "GET runtime-config": () => {
      if (!up) throw down;
      return { instance };
    },
  });
  render(tree(1));
  begin();
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(SAYS));
  up = false;
  await new Promise((resolve) => setTimeout(resolve, 150));
  expect(screen.getByRole("status")).toHaveTextContent(SAYS);
  instance = "two";
  up = true;
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(DONE));
});

test("when the same start is still answering after the wait, the notice says it didn't restart and stays until dismissed", async () => {
  vi.useFakeTimers();
  fakeApi({ "GET runtime-config": () => ({ instance: "one" }) });
  render(tree(1, 5));
  begin();
  expect(screen.getByRole("status")).toHaveTextContent(SAYS);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5001);
  });
  expect(screen.getByRole("status")).toHaveTextContent(STUCK);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(120000);
  });
  expect(screen.getByRole("status")).toHaveTextContent(STUCK);
  vi.useRealTimers();
  act(() => screen.getByRole("button", { name: "Dismiss" }).click());
  expect(screen.getByRole("status")).toBeEmptyDOMElement();
});

test("with a server that can't name its start, running out of time also says it didn't restart", async () => {
  vi.useFakeTimers();
  fakeApi({ "GET runtime-config": () => ({ instance: null }) });
  render(tree(1, 5));
  begin();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5001);
  });
  expect(screen.getByRole("status")).toHaveTextContent(STUCK);
  vi.useRealTimers();
});

test("when asking, the notice says what waits for the restart", () => {
  fakeApi({ "GET runtime-config": () => ({ instance: "one" }) });
  function Asker() {
    const { offer } = useRestart();
    return (
      <button type="button" onClick={offer}>
        offer
      </button>
    );
  }
  render(
    <WordingProvider>
      <RestartProvider hellos={1}>
        <Asker />
        <RestartNotice what="Restart to use: Backups kept." />
      </RestartProvider>
    </WordingProvider>,
  );
  act(() => screen.getByRole("button", { name: "offer" }).click());
  expect(screen.getByRole("status")).toHaveTextContent("Restart to finish this change?");
  expect(screen.getByRole("status")).toHaveTextContent("Restart to use: Backups kept.");
});
