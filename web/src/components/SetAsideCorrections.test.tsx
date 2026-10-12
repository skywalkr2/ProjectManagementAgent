import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { TodayBoard } from "./TodayBoard";
import { WhatChanged } from "./WhatChanged";

const AT = "@";
const SENDER = `news${AT}lists.example.com`;
const DONE: S["SetAsideDone"] = { id: "SNAP-1", version: 7, section: "sales", address: SENDER, domain: "lists.example.com" };
const SAVED: S["SettingsSaved"] = {
  changes: [{ key: "watch.triage", before: [], after: [{ name: "x" }], was_default: true, is_default: false }],
  fingerprint: "fp-2",
  needs_restart: false,
};

function today(extra: Routes = {}, setAside = 6) {
  const received = new Date().toISOString();
  const calls = fakeApi({
    "GET today/agenda": () => [],
    "GET today/todo": () => [],
    "GET today/arrived": () => ({
      items: [{ snapshot: "SNAP-1", source: "mail-1", title: "Spring sale", sender: "Shop", received, unread: true }],
      left_out: 0,
      set_aside: setAside,
    }),
    "GET watch": () => [],
    "GET projects": () => [],
    "GET changes": () => [],
    "GET plugin-today": () => [],
    "GET followups": () => [],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    ...extra,
  });
  const onView = vi.fn();
  renderApp(<TodayBoard onView={onView} />);
  return { calls, onView };
}

const column = (name: string) => screen.findByRole("region", { name });
const body = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;

test("Came in shows the count of what was set aside as a link to the folder, and nothing when none was", async () => {
  const user = userEvent.setup();
  const { onView } = today();
  const col = await column("Came in");
  await user.click(await within(col).findByRole("button", { name: "6 set aside" }));
  expect(onView).toHaveBeenCalledWith("sources");
});

test("no set-aside line when nothing is set aside", async () => {
  today({}, 0);
  const col = await column("Came in");
  await within(col).findByText("Spring sale");
  expect(within(col).queryByRole("button", { name: /set aside/ })).toBeNull();
});

test("a Came in row's menu sets the message aside as personal or sales, with Undo and an offer of a rule", async () => {
  const user = userEvent.setup();
  const { calls } = today({
    "POST mail/SNAP-1/set-aside": () => DONE,
    "POST set-aside/SNAP-1/put-back": () => DONE,
    "POST watch/sorting": () => SAVED,
  });
  const col = await column("Came in");
  await user.click(await within(col).findByRole("button", { name: "More actions for Spring sale" }));
  expect(screen.getByRole("menuitem", { name: "Set aside: personal" })).toBeInTheDocument();
  await user.click(screen.getByRole("menuitem", { name: "Set aside: sales" }));
  await waitFor(() => expect(body(calls, "POST mail/SNAP-1/set-aside")).toEqual({ section: "sales" }));
  expect(await screen.findByText("Set aside Spring sale as sales mail.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Always for this domain" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Always for this sender" }));
  await waitFor(() =>
    expect(body(calls, "POST watch/sorting")).toEqual({ fingerprint: "fp-1", choice: "sales", senders: [SENDER], domains: [] }),
  );
  expect(await screen.findByText(`From now on, mail from ${SENDER} is set aside as sales mail.`)).toBeInTheDocument();
});

test("Undo of a set-aside puts the message back with the version it was left at", async () => {
  const user = userEvent.setup();
  const { calls } = today({
    "POST mail/SNAP-1/set-aside": () => DONE,
    "POST set-aside/SNAP-1/put-back": () => DONE,
  });
  const col = await column("Came in");
  await user.click(await within(col).findByRole("button", { name: "More actions for Spring sale" }));
  await user.click(screen.getByRole("menuitem", { name: "Set aside: personal" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(body(calls, "POST set-aside/SNAP-1/put-back")).toEqual({ read_version: 7 }));
});

function change(id: string, extra: Partial<S["ChangeItem"]> = {}): S["ChangeItem"] {
  return {
    id,
    version: 4,
    dismissed: false,
    stage_task: false,
    first_go: false,
    refused: false,
    state: "needs_you",
    waiting: "Waiting for your first go.",
    created_at: "2026-10-09T14:00:00Z",
    note: null,
    source: "SRC-1",
    source_title: "Spring sale",
    changeset: null,
    ...extra,
  };
}

test("a What changed row for a mail message has the same two corrections; other rows do not", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET changes": () => [change("REQ-1", { mail_item: "SNAP-1" }), change("REQ-2", { source_title: "A note" })],
    "POST mail/SNAP-1/set-aside": () => DONE,
  });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: "More actions for Spring sale" }));
  await user.click(screen.getByRole("menuitem", { name: "Set aside: sales" }));
  await waitFor(() => expect(body(calls, "POST mail/SNAP-1/set-aside")).toEqual({ section: "sales" }));
  await user.keyboard("{Escape}");
  const other = screen.getByRole("button", { name: "More actions for A note" });
  await user.click(other);
  expect(screen.queryByRole("menuitem", { name: "Set aside: sales" })).toBeNull();
});
