import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { App } from "../App";
import { Ask } from "./Ask";
import { HandIn } from "./HandIn";

// Hand something in is a drawer and Ask is a pane on a wide screen (design 7.13): each leaves what the person was working
// on in view; below the desktop width Ask is a dialog, and on a phone the drawer is the whole screen.

const rc = (extra: Partial<S["RuntimeConfig"]> = {}): S["RuntimeConfig"] => ({
  api_base: "api",
  assistant_name: "Helper",
  assistant_named: true,
  base_path: "",
  demo: false,
  feedback_to: "feedback@example.com",
  narrow_below_px: 640,
  logo: false,
  theme: "system",
  density: "comfortable",
  pm: null,
  shortcuts: { undo: "u", hand_in: "n", help: "?", ask: "/" },
  toast_seconds: 0,
  version: "9.8.7",
  wording: {},
  workspace_name: "Workspace",
  ...extra,
});

const today = {
  "GET panels": () => [],
  "GET asks": () => [],
  "GET projects": () => [],
  "POST handin": () => ({ request: "REQ-1", source: null }),
};

/** Makes the window as wide as given: a media query is true when it asks for no more than the width. */
function windowWidth(px: number) {
  vi.stubGlobal("matchMedia", (query: string) => {
    const min = /min-width:\s*(\d+)px/.exec(query);
    const max = /max-width:\s*(\d+)px/.exec(query);
    const matches = (min ? px >= Number(min[1]) : true) && (max ? px <= Number(max[1]) : true);
    return { matches, media: query, addEventListener: () => undefined, removeEventListener: () => undefined };
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("Hand something in", () => {
  test("opens as a drawer over the screen it was opened from, named by its heading, with the cursor in the box", async () => {
    fakeApi(today);
    renderApp(<HandIn onClose={() => undefined} />);
    const drawer = await screen.findByRole("dialog", { name: "Hand something in" });
    expect(within(drawer).getByLabelText("Paste or type it here")).toHaveFocus();
    expect(within(drawer).getByRole("button", { name: "Hand in" })).toBeDisabled();
  });

  test("closing it with words in the box asks first, and Keep editing leaves them there", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    fakeApi(today);
    renderApp(<HandIn onClose={onClose} />);
    const box = await screen.findByLabelText("Paste or type it here");
    await user.click(box);
    await user.paste("Subject: dates");
    await user.keyboard("{Escape}");
    expect(await screen.findByRole("alert")).toHaveTextContent(/discard/i);
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(screen.getByLabelText("Paste or type it here")).toHaveValue("Subject: dates");
    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: "Discard" }));
    expect(onClose).toHaveBeenCalled();
  });

  test("an empty box closes at once, and Hand in in the footer sends it", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const calls = fakeApi(today);
    renderApp(<HandIn onClose={onClose} />);
    await user.click(await screen.findByLabelText("Paste or type it here"));
    await user.paste("Subject: dates");
    await user.click(screen.getByRole("button", { name: "Hand in" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(calls.find((c) => c.route === "POST handin")!.body).toEqual({ note: "", pasted: "Subject: dates" });
    onClose.mockClear();
    renderApp(<HandIn onClose={onClose} />);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  test("in the app, the button opens it and the screen behind it is still there", async () => {
    const user = userEvent.setup();
    fakeApi({ ...today, "GET today/agenda": () => [], "GET today/todo": () => [], "GET today/arrived": () => ({ items: [], left_out: 0 }), "GET watch": () => [] });
    renderApp(<App rc={rc()} />);
    await user.click(await screen.findByRole("button", { name: "Hand something in" }));
    expect(await screen.findByRole("dialog", { name: "Hand something in" })).toBeInTheDocument();
    expect(document.querySelector("main#main")).toBeInTheDocument();
  });
});

describe("Ask", () => {
  test("as a pane it is a side area named by its heading, with the cursor in the question, and Escape closes it", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    fakeApi({ "GET asks": () => [] });
    renderApp(<Ask pane onClose={onClose} />);
    const pane = await screen.findByRole("complementary", { name: "Ask Helper" });
    expect(within(pane).getByRole("textbox")).toHaveFocus();
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  test("on a wide screen the Ask key opens the pane beside the screen, not a dialog", async () => {
    const user = userEvent.setup();
    windowWidth(1600);
    fakeApi(today);
    renderApp(<App rc={rc()} />);
    await user.keyboard("/");
    expect(await screen.findByRole("complementary", { name: "Ask Helper" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    // The screen it was opened from is not covered or made inert.
    expect(screen.getByRole("main")).not.toHaveAttribute("aria-hidden");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("complementary", { name: "Ask Helper" })).toBeNull());
  });

  test("on a narrower screen it is a dialog", async () => {
    const user = userEvent.setup();
    windowWidth(1200);
    fakeApi(today);
    renderApp(<App rc={rc()} />);
    await user.keyboard("/");
    expect(await screen.findByRole("dialog", { name: "Ask Helper" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Ask Helper" })).toBeNull();
  });
});
