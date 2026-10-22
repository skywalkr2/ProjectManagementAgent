import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { ReminderWhere } from "./ReminderWhere";
import { ReminderWhereRow } from "./ReminderWhereRow";

// Where reminders reach the person when the app isn't open (design 6.12): the choices, the accounts that can carry each,
// the exact reminder shown before the yes, ending the yes with Undo, and Today's line when the yes has gone stale.

const text = (subject: string, body: string, event_title = subject): S["ReminderTextView"] => ({ subject, body, event_title });
const view = (over: Partial<S["ReminderWhereView"]> = {}): S["ReminderWhereView"] => ({
  where: "nowhere",
  account: null,
  account_label: null,
  standing: null,
  stale: [],
  accounts: [
    { id: "mailbox:work", label: "Work mail", mail: true, calendar: false },
    { id: "signin:me@example.com", label: "My sign-in (me@example.com)", mail: true, calendar: true },
  ],
  template_version: "v1",
  example: {
    item: text("Call the print shop about the proofs", "Call the print shop about the proofs\n\nReminder for 2026-10-22 10:00."),
    plain: text("A reminder from the app", "A reminder from the app.\n\nReminder for 2026-10-22 10:00."),
  },
  look_ahead_hours: 24,
  ...over,
});
const SAVED = { changes: [], fingerprint: "fp-2", needs_restart: false } satisfies S["SettingsSaved"];
const standing = (over: Partial<S["StandingYesView"]> = {}): S["StandingYesView"] => ({
  id: "XSY-1",
  form: "mail",
  account: "mailbox:work",
  account_label: "Work mail",
  given_at: "2026-10-22T09:00:00Z",
  template_version: "v1",
  stale: [],
  ...over,
});

function routes(current: S["ReminderWhereView"], extra: Record<string, (body: unknown) => unknown> = {}) {
  return {
    "GET reminders/where": () => current,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "POST settings": () => SAVED,
    ...extra,
  };
}
const sent = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;

describe("where reminders reach you", () => {
  test("offers nowhere, the app's calendar, an account's calendar and an account's mail", async () => {
    fakeApi(routes(view()));
    renderApp(<ReminderWhere />);
    expect(await screen.findByRole("radio", { name: /Nowhere/ })).toBeChecked();
    for (const name of [/In the app's calendar/, /In my calendar/, /To my mail/]) expect(screen.getByRole("radio", { name })).toBeInTheDocument();
  });

  test("lists only the accounts that can carry the form chosen, and shows the exact reminder once one is picked", async () => {
    fakeApi(routes(view()));
    renderApp(<ReminderWhere />);
    await userEvent.click(await screen.findByRole("radio", { name: /In my calendar/ }));
    const pick = await screen.findByRole("combobox", { name: "Account" });
    expect(within(pick).getAllByRole("option").map((o) => o.textContent)).toEqual(["Pick an account", "My sign-in (me@example.com)"]);
    expect(screen.queryByText(/exactly what a reminder will say/)).toBeNull();
    await userEvent.selectOptions(pick, "signin:me@example.com");
    expect(screen.getByText(/exactly what a reminder will say/)).toBeInTheDocument();
    expect(screen.getByText(/An event called: Call the print shop about the proofs/)).toBeInTheDocument();
    expect(screen.getByText(/A reminder from the app/, { selector: "p" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yes, send my reminders there without asking" })).toBeEnabled();
  });

  test("a mail shows its subject and body, and a yes names the form, the account and the version seen", async () => {
    const calls = fakeApi(routes(view(), { "POST reminders/yes": () => ({ changeset: "CS-9" }) }));
    renderApp(<ReminderWhere />);
    await userEvent.click(await screen.findByRole("radio", { name: /To my mail/ }));
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Account" }), "mailbox:work");
    expect(screen.getByText(/Mail to you\. Subject: Call the print shop about the proofs/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yes, send my reminders there without asking" }));
    await waitFor(() => expect(sent(calls, "POST reminders/yes")).toEqual({ form: "mail", account: "mailbox:work", template_version: "v1" }));
    expect(sent(calls, "POST settings")).toMatchObject({ changes: { "steward.reminders.where": "mail", "steward.reminders.where_account": "mailbox:work" } });
  });

  test("Undo after giving the yes brings back the earlier choice and account exactly, not Ask me each time", async () => {
    const earlier = view({ where: "calendar", account: "signin:me@example.com", account_label: "My sign-in (me@example.com)" });
    const change = (key: string, before: string, after: string) => ({ key, before, after, was_default: false, is_default: false });
    const saved = {
      changes: [change("steward.reminders.where", "calendar", "mail"), change("steward.reminders.where_account", "signin:me@example.com", "mailbox:work")],
      fingerprint: "fp-2",
      needs_restart: false,
    } satisfies S["SettingsSaved"];
    const calls = fakeApi(
      routes(earlier, {
        "POST settings": () => saved,
        "POST reminders/yes": () => ({ changeset: "CS-9" }),
        "POST changesets/CS-9/undo": () => ({ applied: [], skipped: [] }),
      }),
    );
    renderApp(<ReminderWhere />);
    await userEvent.click(await screen.findByRole("radio", { name: /To my mail/ }));
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Account" }), "mailbox:work");
    await userEvent.click(screen.getByRole("button", { name: "Yes, send my reminders there without asking" }));
    await waitFor(() => expect(sent(calls, "POST reminders/yes")).toBeTruthy());
    await userEvent.click(await screen.findByRole("button", { name: /Undo/ }));
    await waitFor(() => expect(calls.filter((c) => c.route === "POST settings")).toHaveLength(2));
    expect(calls.some((c) => c.route === "POST changesets/CS-9/undo")).toBe(true);
    // the yes is taken back first, then the choice and account go back to what they were
    const order = calls.map((c) => c.route).filter((r) => r === "POST changesets/CS-9/undo" || r === "POST settings");
    expect(order).toEqual(["POST settings", "POST changesets/CS-9/undo", "POST settings"]);
    expect(calls.filter((c) => c.route === "POST settings")[1].body).toEqual({
      changes: { "steward.reminders.where": "calendar", "steward.reminders.where_account": "signin:me@example.com" },
      reset: [],
      fingerprint: "fp-2",
    });
  });

  test("Ask me each time sets the choice and gives no yes", async () => {
    const calls = fakeApi(routes(view()));
    renderApp(<ReminderWhere />);
    await userEvent.click(await screen.findByRole("radio", { name: /To my mail/ }));
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Account" }), "mailbox:work");
    await userEvent.click(screen.getByRole("button", { name: "Ask me each time" }));
    await waitFor(() => expect(sent(calls, "POST settings")).toBeTruthy());
    expect(calls.some((c) => c.route === "POST reminders/yes")).toBe(false);
  });

  test("the app's calendar is set at once, with no account and no yes", async () => {
    const calls = fakeApi(routes(view()));
    renderApp(<ReminderWhere />);
    await userEvent.click(await screen.findByRole("radio", { name: /In the app's calendar/ }));
    await waitFor(() =>
      expect(sent(calls, "POST settings")).toMatchObject({ changes: { "steward.reminders.where": "app", "steward.reminders.where_account": "" } }),
    );
    expect(calls.some((c) => c.route === "POST reminders/yes")).toBe(false);
  });

  test("with a yes standing, says so and ending it has an Undo that takes it back", async () => {
    const current = view({ where: "mail", account: "mailbox:work", account_label: "Work mail", standing: standing() });
    const calls = fakeApi(
      routes(current, {
        "POST reminders/yes/end": () => ({ changeset: "CS-4" }),
        "POST changesets/CS-4/undo": () => ({ applied: [], skipped: [] }),
      }),
    );
    renderApp(<ReminderWhere />);
    expect(await screen.findByText(/Reminders go without asking, your mail, at Work mail, since 2026-10-22/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Stop sending without asking" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST reminders/yes/end")).toBe(true));
    await userEvent.click(await screen.findByRole("button", { name: /Undo/ }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-4/undo")).toBe(true));
  });
});

describe("Today's line for a yes that has gone stale", () => {
  test("starts with the verb, says what changed and opens Settings", async () => {
    const opened: string[] = [];
    fakeApi(
      routes(view({ where: "mail", account: "mailbox:work", standing: standing({ stale: ["template", "address"] }), stale: ["template", "address"] })),
    );
    renderApp(<ReminderWhereRow onView={(v) => opened.push(v)} />);
    expect(await screen.findByText("Look again at reminders in your mail: the reminder's wording changed and your own address changed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Look again" }));
    expect(opened).toEqual(["settings/today"]);
  });

  test("is not there while nothing has changed", async () => {
    fakeApi(routes(view({ where: "mail", account: "mailbox:work", standing: standing() })));
    renderApp(<ReminderWhereRow />);
    await waitFor(() => expect(screen.queryByText(/Look again/)).toBeNull());
  });
});
