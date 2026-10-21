import "@testing-library/jest-dom/vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import type { View } from "../lib/views";
import { fakeApi, renderApp } from "../test-utils";
import { MAIL_LINK_MAX } from "../lib/mail";
import { Feedback } from "./Feedback";

const TO = "feedback@example.com";
const SUBJECT = "Feedback on PM Cockpit";

type Problem = S["FeedbackProblem"];

function open(props: { to?: string | null; view?: View; version?: string; problems?: Problem[] } = {}) {
  fakeApi({
    "GET panels": () => [{ name: "plan", title: "The plan", tab: "work" }],
    ...(props.problems ? { "GET feedback/problems": () => ({ problems: props.problems }) } : {}),
  });
  const onClose = vi.fn();
  renderApp(<Feedback onClose={onClose} view={props.view ?? "records/files"} version={props.version ?? "9.8.7"} to={"to" in props ? props.to : TO} />);
  return { onClose, user: userEvent.setup() };
}

const message = () => screen.getByLabelText("What happened, or what would help?");
const preview = () => screen.getByLabelText("Message") as HTMLTextAreaElement;

test("the dialog is named, the box has the focus and nothing can go until something is written", () => {
  open();
  expect(screen.getByRole("dialog", { name: "Write feedback" })).toBeInTheDocument();
  expect(message()).toHaveFocus();
  expect(message()).toBeRequired();
  expect(message()).toHaveAccessibleDescription(/Nothing is sent from here\. Copy your message.*Write a few words to continue\./);
  expect(screen.getByRole("button", { name: "Copy" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Open in your email app" })).toBeDisabled();
  expect(screen.queryByRole("link", { name: "Open in your email app" })).toBeNull();
});

test("the preview shows the subject and the body, ending with the version and the screen", async () => {
  const { user } = open();
  expect(screen.getByLabelText("Include the app version and the screen you were on")).toBeChecked();
  await user.type(message(), "The list is empty");
  expect(screen.getByLabelText("Subject")).toHaveValue(SUBJECT);
  expect(screen.getByLabelText("Subject")).toHaveAttribute("readonly");
  expect(preview()).toHaveAttribute("readonly");
  expect(preview().value).toBe("The list is empty\n\nApp version: 9.8.7\nScreen: Files");
});

test("without the version lines the body is only what was written", async () => {
  const { user } = open();
  await user.type(message(), "Just this");
  await user.click(screen.getByLabelText("Include the app version and the screen you were on"));
  expect(preview().value).toBe("Just this");
  expect(preview().value).not.toMatch(/version|Screen/i);
});

test("the screen is a plugin panel's title or a record page's general name", async () => {
  const first = open({ view: "work/panel/plan" });
  await first.user.type(message(), "x");
  await waitFor(() => expect(preview().value).toMatch(/Screen: The plan$/));
});

test("a record page is named in general terms, never by its record", async () => {
  const { user } = open({ view: "records/thing/abc" });
  await user.type(message(), "x");
  expect(preview().value).toMatch(/Screen: A project or person page$/);
  expect(preview().value).not.toMatch(/abc|thing/);
});

test("with an address the mail link is the main action, with the subject and body encoded", async () => {
  const { user } = open();
  await user.type(message(), "Line one\nLine & two");
  const link = screen.getByRole("link", { name: "Open in your email app" });
  const body = "Line one\nLine & two\n\nApp version: 9.8.7\nScreen: Files";
  expect(link).toHaveAttribute(
    "href",
    `mailto:${TO}?subject=${encodeURIComponent(SUBJECT)}&body=${encodeURIComponent(body.replace(/\n/g, "\r\n"))}`,
  );
  expect(link).toHaveClass("primary");
  expect(screen.getByRole("button", { name: "Copy" })).not.toHaveClass("primary");
});

test("the version and screen lines are left out of the link when unchecked", async () => {
  const { user } = open();
  await user.type(message(), "Only this");
  await user.click(screen.getByLabelText("Include the app version and the screen you were on"));
  const href = screen.getByRole("link", { name: "Open in your email app" }).getAttribute("href")!;
  expect(href).toContain(`body=${encodeURIComponent("Only this")}`);
  expect(href).not.toContain("version");
});

test("a message too long for a mail link has no link and says to copy it", async () => {
  const { user } = open();
  await user.click(message());
  await user.paste("a".repeat(MAIL_LINK_MAX));
  expect(screen.queryByRole("link", { name: "Open in your email app" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Open in your email app" })).toBeNull();
  expect(screen.getByText(/too long for a mail link/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy" })).toHaveClass("primary");
});

test("without an address Copy is the main action and the hint says who to send it to", async () => {
  const { user } = open({ to: null });
  await user.type(message(), "Hello");
  expect(screen.queryByRole("link")).toBeNull();
  expect(screen.queryByText("Open in your email app")).toBeNull();
  expect(screen.getByRole("button", { name: "Copy" })).toHaveClass("primary");
  expect(screen.getByText("Send it to whoever gave you the app.")).toBeInTheDocument();
});

test("Copy puts the subject, a blank line and the body on the clipboard, and says so", async () => {
  const { user } = open({ to: null });
  await user.type(message(), "Hello");
  await user.click(screen.getByRole("button", { name: "Copy" }));
  expect(await navigator.clipboard.readText()).toBe(`${SUBJECT}\n\nHello\n\nApp version: 9.8.7\nScreen: Files`);
  expect(await screen.findByText("Copied. Paste it into an email to send it.")).toBeInTheDocument();
});

test("when copying is blocked it says so and the text stays there to select", async () => {
  const { user } = open();
  await user.type(message(), "Hello");
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));
  await user.click(screen.getByRole("button", { name: "Copy" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/Your browser blocked copying/);
  expect(screen.queryByText(/^Copied/)).toBeNull();
  expect(preview().value).toContain("Hello");
  expect(preview()).not.toBeDisabled();
});

test("Close and Escape close the dialog", async () => {
  const { user, onClose } = open();
  await user.click(screen.getByRole("button", { name: "Close" }));
  expect(onClose).toHaveBeenCalledTimes(1);
  await user.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledTimes(2);
});

const CALL: Problem = {
  at: "2026-10-21T09:30:00+10:00",
  doing: "task",
  what: "notes",
  service: "example-service",
  adapter: "example-adapter",
  program_version: null,
  params: { tier: "routine", model: "example-model", temperature: "0.2", max_output: "800", send_temperature: "yes" },
  status: 400,
  error_kind: "other",
  text: "bad key <secret> for <name> <address>",
};
const READ: Problem = {
  at: "2026-10-21T08:00:00Z",
  doing: "source_read",
  what: "folder",
  service: null,
  adapter: null,
  program_version: null,
  params: {},
  status: null,
  error_kind: "outage",
  text: "couldn't read <path>",
};
const CALL_LINES = [
  "2026-10-21 09:30 +10:00",
  "Doing: working on notes",
  "Service: example-service",
  "Adapter: example-adapter",
  "Request: level of work: routine; model: example-model; temperature: 0.2; output limit: 800; sends temperature: yes",
  "Status: 400",
  "Error: other",
  "Said: bad key <secret> for <name> <address>",
];
const READ_LINES = ["2026-10-21 08:00 UTC", "Doing: reading folder", "Error: outage", "Said: couldn't read <path>"];

test("the problems box appears only when there were problems, is ticked, and the preview shows exactly the lines", async () => {
  const { user } = open({ problems: [CALL, READ] });
  const box = await screen.findByRole("checkbox", { name: "Add the last problems (2)" });
  expect(box).toBeChecked();
  await user.type(message(), "It failed");
  const expected = ["It failed", "", "App version: 9.8.7", "Screen: Files", "", "Recent problems", ...CALL_LINES, "", ...READ_LINES].join("\n");
  expect(preview().value).toBe(expected);
});

test("unticking the problems takes every one of their lines out of the preview and the link", async () => {
  const { user } = open({ problems: [CALL] });
  await user.type(message(), "It failed");
  await user.click(await screen.findByRole("checkbox", { name: "Add the last problems (1)" }));
  expect(preview().value).toBe("It failed\n\nApp version: 9.8.7\nScreen: Files");
  expect(screen.getByRole("link", { name: "Open in your email app" }).getAttribute("href")).not.toContain("Recent");
});

test("the problems are in the email link and on the clipboard exactly as the preview shows them", async () => {
  const { user } = open({ problems: [READ] });
  await user.type(message(), "Hello");
  await screen.findByRole("checkbox", { name: "Add the last problems (1)" });
  const body = preview().value;
  expect(screen.getByRole("link", { name: "Open in your email app" })).toHaveAttribute("href", expect.stringContaining(encodeURIComponent(body.replace(/\n/g, "\r\n"))));
  await user.click(screen.getByRole("button", { name: "Copy" }));
  expect(await navigator.clipboard.readText()).toBe(`${SUBJECT}\n\n${body}`);
});

test("with no problems, or when they can't be fetched, there is no problems box", async () => {
  const none = open({ problems: [] });
  await none.user.type(message(), "x");
  await waitFor(() => expect(screen.queryByRole("checkbox", { name: /last problems/ })).toBeNull());
  expect(preview().value).toBe("x\n\nApp version: 9.8.7\nScreen: Files");
});

test("problems too long for a mail link leave the copy path", async () => {
  const long = { ...CALL, text: "x".repeat(MAIL_LINK_MAX) };
  const { user } = open({ problems: [long] });
  await user.type(message(), "Hello");
  await screen.findByRole("checkbox", { name: "Add the last problems (1)" });
  expect(screen.queryByRole("link", { name: "Open in your email app" })).toBeNull();
  expect(screen.getByText(/too long for a mail link/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy" })).toHaveClass("primary");
});
