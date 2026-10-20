import "@testing-library/jest-dom/vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button as AriaButton } from "react-aria-components";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { MenuButton } from "../ui/MenuButton";
import { usePagesGroup } from "./HeaderLinks";

// Links to the person's own pages (design 7.1, 7.9): the first group of the person's menu, from the list in Settings.

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";

const links = [
  { name: "Planning board", address: `${WEB}boards.example.org/plan` },
  { name: "Team schedule", address: `${WEB}schedule.example.org/team` },
];

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

/** The group in a menu of its own, as the person's menu holds it. */
function Menu() {
  const group = usePagesGroup();
  return <MenuButton groups={group ? [group] : []} trigger={<AriaButton>Open the menu</AriaButton>} />;
}

const show = (value: unknown) => {
  const calls = fakeApi({ "GET settings": () => ({ fingerprint: "fp", items: [item(value)] }) });
  renderApp(<Menu />);
  return calls;
};

test("the menu lists each link by its name, opening its address in a new tab", async () => {
  const user = userEvent.setup();
  show(links);
  await user.click(await screen.findByRole("button", { name: "Open the menu" }));
  const first = await screen.findByRole("menuitem", { name: "Planning board" });
  expect(first).toHaveAttribute("href", links[0].address);
  expect(first).toHaveAttribute("target", "_blank");
  expect(first.getAttribute("rel")).toContain("noopener");
  expect(screen.getByRole("menuitem", { name: "Team schedule" })).toHaveAttribute("href", links[1].address);
});

test("with no links there is no group", async () => {
  const calls = show([]);
  await waitFor(() => expect(calls.some((c) => c.route === "GET settings")).toBe(true));
  await act(async () => undefined);
  expect(screen.queryByRole("button", { name: "Open the menu" })).toBeNull();
});

test("a link that is not a web address is never offered", async () => {
  const user = userEvent.setup();
  show([...links, { name: "Odd one", address: "javascript:alert(1)" }, { name: "Another", address: 5 }]);
  await user.click(await screen.findByRole("button", { name: "Open the menu" }));
  expect(await screen.findByRole("menuitem", { name: "Planning board" })).toBeInTheDocument();
  expect(screen.queryByRole("menuitem", { name: "Odd one" })).toBeNull();
  expect(screen.queryByRole("menuitem", { name: "Another" })).toBeNull();
});
