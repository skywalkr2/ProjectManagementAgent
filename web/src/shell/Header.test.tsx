import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RestartProvider } from "../lib/restart";
import { initAppearance } from "../lib/theme";
import { fakeApi, rcFixture, renderApp, statusFixture } from "../test-utils";
import { Header } from "./Header";

function show(over: { demo?: boolean; logo?: boolean; narrow?: boolean; handlers?: Partial<Record<"onHandIn" | "onAsk" | "onHelp" | "onFeedback" | "onOpenGuide", () => void>> } = {}) {
  fakeApi({
    "GET status": () => statusFixture(),
    "GET me": () => ({ full_name: "Casey Example", person: null }),
    "GET runtime-config": () => ({ instance: null }),
  });
  const rc = rcFixture({ demo: over.demo ?? false, logo: over.logo ?? false, workspace_name: "Example Workspace" });
  const noop = () => undefined;
  const h = over.handlers ?? {};
  renderApp(
    <RestartProvider hellos={1}>
      <Header
        rc={rc}
        live={{ state: "live", lastUpdate: null, refresh: noop }}
        narrow={over.narrow ?? false}
        shortcuts={rc.shortcuts}
        onHandIn={h.onHandIn ?? noop}
        onAsk={h.onAsk ?? noop}
        onHelp={h.onHelp ?? noop}
        onFeedback={h.onFeedback ?? noop}
        onOpenGuide={h.onOpenGuide ?? noop}
      />
    </RestartProvider>,
  );
}

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.removeAttribute("data-density");
  window.localStorage.clear();
});

test("the brand is a link to Today, named for what it does, with a monogram of the workspace name", () => {
  show();
  const brand = screen.getByRole("link", { name: "Go to Today · Example Workspace" });
  expect(brand).toHaveAttribute("href", expect.stringMatching(/#today$/));
  expect(brand).toHaveTextContent("Example Workspace");
  expect(brand).toHaveTextContent("EW");
});

test("a workspace with a logo shows the image, found under the API's brand address", () => {
  show({ logo: true });
  const image = screen.getByRole("link", { name: "Go to Today · Example Workspace" }).querySelector("img")!;
  expect(image).toHaveAttribute("src", "api/brand/logo");
  expect(image).toHaveAttribute("alt", "");
});

test("a demo workspace shows the Demo chip, in words, and others don't", () => {
  show({ demo: true });
  expect(screen.getByText("Demo")).toBeInTheDocument();
});

test("the assistant's alive line is in the header beside the status chip", async () => {
  show();
  const chip = await screen.findByRole("button", { name: /^App status: / });
  const alive = await screen.findByRole("button", { name: /^Assistant/ });
  expect(alive).toHaveTextContent("no tasks yet");
  expect(alive.parentElement).toBe(chip.parentElement);
});

test("no Demo chip when the workspace is not a demo", () => {
  show();
  expect(screen.queryByText("Demo")).toBeNull();
});

test("Ask is a search-style field naming the assistant and its key, and it opens the Ask box", async () => {
  const user = userEvent.setup();
  const onAsk = vi.fn();
  show({ handlers: { onAsk } });
  const field = screen.getAllByRole("button", { name: "Ask" })[0];
  expect(field).toHaveTextContent("Ask Helper or search…");
  expect(field).toHaveTextContent("/");
  await user.click(field);
  expect(onAsk).toHaveBeenCalledTimes(1);
});

test("Hand something in is the one primary button, and it opens the hand-in", async () => {
  const user = userEvent.setup();
  const onHandIn = vi.fn();
  show({ handlers: { onHandIn } });
  const button = screen.getByRole("button", { name: "Hand something in" });
  expect(button).toHaveAttribute("data-variant", "primary");
  await user.click(button);
  expect(onHandIn).toHaveBeenCalledTimes(1);
});

test("Help is a menu: shortcuts, the setup guide, feedback and the version as a line that does nothing", async () => {
  const user = userEvent.setup();
  const onHelp = vi.fn();
  const onFeedback = vi.fn();
  const onOpenGuide = vi.fn();
  show({ handlers: { onHelp, onFeedback, onOpenGuide } });
  await user.click(screen.getByRole("button", { name: "Help" }));
  expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Show keyboard shortcuts", "Setup guide", "Write feedback", "Version 9.8.7"]);
  expect(screen.getByRole("menuitem", { name: "Version 9.8.7" })).toHaveAttribute("aria-disabled", "true");
  await user.click(screen.getByRole("menuitem", { name: "Show keyboard shortcuts" }));
  expect(onHelp).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "Help" }));
  await user.click(screen.getByRole("menuitem", { name: "Setup guide" }));
  await waitFor(() => expect(onOpenGuide).toHaveBeenCalledTimes(1));
  await user.click(screen.getByRole("button", { name: "Help" }));
  await user.click(screen.getByRole("menuitem", { name: "Write feedback" }));
  expect(onFeedback).toHaveBeenCalledTimes(1);
});

test("the person's initials open the user menu, where theme and density are saved for this device", async () => {
  const user = userEvent.setup();
  initAppearance({ brand_color: null, theme: "system", density: "comfortable" });
  show();
  const avatar = await screen.findByRole("button", { name: "Change appearance, Casey Example" });
  expect(avatar).toHaveTextContent("CE");
  await user.click(avatar);
  const dark = screen.getByRole("menuitemradio", { name: "Dark" });
  expect(screen.getByRole("menuitemradio", { name: "Match this computer" })).toBeChecked();
  await user.click(dark);
  expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  expect(window.localStorage.getItem("cockpit:theme")).toBe("dark");
  await user.click(screen.getByRole("button", { name: "Change appearance, Casey Example" }));
  expect(screen.getByRole("menuitemradio", { name: "Dark" })).toBeChecked();
  await user.click(screen.getByRole("menuitemradio", { name: "Compact" }));
  expect(document.documentElement).toHaveAttribute("data-density", "compact");
  expect(window.localStorage.getItem("cockpit:density")).toBe("compact");
});

test("until the workspace knows the person's name, the avatar uses the workspace's", async () => {
  show();
  await waitFor(() => expect(screen.getByRole("button", { name: /^Change appearance, / })).toBeInTheDocument());
});

test("on a phone only the brand, the status chip and the user menu remain", async () => {
  show({ narrow: true, demo: true });
  const header = screen.getByRole("banner");
  expect(within(header).getByRole("link", { name: /Go to Today/ })).toBeInTheDocument();
  expect(within(header).getByRole("button", { name: /^App status: / })).toBeInTheDocument();
  expect(within(header).getByRole("button", { name: /^Change appearance, / })).toBeInTheDocument();
  expect(within(header).queryByRole("button", { name: "Ask" })).toBeNull();
  expect(within(header).queryByRole("button", { name: "Hand something in" })).toBeNull();
  expect(within(header).queryByRole("button", { name: "Help" })).toBeNull();
  expect(within(header).getByText("Demo")).toBeInTheDocument();
});

test("on a phone only the logo, the status chip and the avatar are in the header: no workspace name, no assistant label", async () => {
  show({ narrow: true });
  const header = screen.getByRole("banner");
  const brand = within(header).getByRole("link", { name: "Go to Today · Example Workspace" });
  // The name is the link's accessible name; it takes no room on screen.
  expect(brand).not.toHaveTextContent("Example Workspace");
  expect(brand).toHaveTextContent("EW");
  await within(header).findByRole("button", { name: /^App status: / });
  expect(within(header).queryByRole("button", { name: /^Assistant/ })).toBeNull();
  expect(Array.from(header.querySelectorAll("button, a")).map((el) => el.getAttribute("aria-label") ?? el.textContent)).toHaveLength(3);
});

test("on a phone the assistant's state is in the status chip's popover", async () => {
  const user = userEvent.setup();
  show({ narrow: true });
  await user.click(await screen.findByRole("button", { name: /^App status: / }));
  const dialog = await screen.findByRole("dialog", { name: "Status" });
  const alive = within(dialog).getByText("Assistant", { selector: "p" }).closest("li")!;
  expect(alive).toHaveAttribute("data-state", "alive");
  expect(alive).toHaveTextContent("no tasks yet");
});

test("from a wider screen the assistant's line is beside the chip and the popover doesn't repeat it", async () => {
  const user = userEvent.setup();
  show();
  await user.click(await screen.findByRole("button", { name: /^App status: / }));
  const dialog = await screen.findByRole("dialog", { name: "Status" });
  expect(dialog.querySelector('[data-state="alive"]')).toBeNull();
});
