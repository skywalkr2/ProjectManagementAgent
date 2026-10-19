import "@testing-library/jest-dom/vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { reveal, useReveal } from "../lib/reveal";
import { fakeApi, renderApp } from "../test-utils";
import { HoldPill } from "./OnHold";

const person = (id: string, name: string): S["PersonView"] => ({ id, name, role: null, org: null, aliases: [], status: "active", is_pm: false, track_only: false, open_items: 0 });
const people = [person("P-1", "Quinn Sample"), person("P-2", "Robin Sample"), person("P-3", "Sam Twin"), person("P-4", "Sam Twin")];

function Listener(props: { on: (id: string) => void }) {
  useReveal("person", (id) => {
    props.on(id);
    return true;
  });
  return null;
}

test("a person named in what a to-do waits for is a link to their group in Follow-ups", async () => {
  fakeApi({ "GET people": () => people });
  const user = userEvent.setup();
  const seen = vi.fn();
  renderApp(
    <>
      <Listener on={seen} />
      <HoldPill what="Quinn Sample's answer" due={null} />
    </>,
  );
  const link = await screen.findByRole("link", { name: "Quinn Sample" });
  expect(link).toHaveAttribute("href", expect.stringMatching(/#work\/followups$/));
  expect(screen.getByText(/On hold:/)).toHaveTextContent("On hold: Quinn Sample's answer");
  await user.click(link);
  expect(seen).toHaveBeenCalledWith("P-1");
});

test("words that name nobody, only a first name, or two people alike stay plain text", async () => {
  fakeApi({ "GET people": () => people });
  renderApp(
    <>
      <HoldPill what="the legal review" />
      <HoldPill what="Quinn's answer" />
      <HoldPill what="Sam Twin to reply" />
    </>,
  );
  await waitFor(() => expect(screen.getAllByText(/On hold:/)).toHaveLength(3));
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByRole("link")).toBeNull();
  expect(reveal("person", "P-1")).toBe(false);
});
