import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { AiRouting } from "./AiRouting";

type View = S["AiRoutingView"];

const ACCOUNTS = [
  { name: "main", label: "Main account", kind: "service-a", adapter: "a", base_url: null, models: { everyday: "m1" }, used_for: ["routine"], backup_for: [], has_key: true, key_state: "saved", key_where: null, key_ending: false, answered_at: null, spent_today_usd: 0, checked_for: [], check_failed_for: [], checked_at: null, paused_until: null, check_usd: null, accepted_unchecked: false },
  { name: "big", label: "Strong account", kind: "service-a", adapter: "a", base_url: null, models: { everyday: "m2" }, used_for: ["deep"], backup_for: [], has_key: true, key_state: "saved", key_where: null, key_ending: false, answered_at: null, spent_today_usd: 0, checked_for: [], check_failed_for: [], checked_at: null, paused_until: null, check_usd: null, accepted_unchecked: false },
] as S["AiAccountView"][];

const fit = (tier: string, over: Partial<S["AiKindFit"]> = {}): S["AiKindFit"] => ({
  tier,
  skills: 2,
  measured: 2,
  stale: 0,
  below: 0,
  runs: 20,
  passes: 18,
  cost_per_pass_usd: 0.02,
  status: "ok",
  ...over,
});

const kind = (name: string, label: string, over: Partial<S["AiWorkKindView"]> = {}): S["AiWorkKindView"] => ({
  name,
  label,
  tier: "routine",
  default_tier: "routine",
  custom: false,
  source: "default",
  fits: [fit("routine"), fit("deep", { passes: 20, cost_per_pass_usd: 0.1 })],
  suggested_tier: null,
  suggestion_why_not: null,
  ...over,
});

function start(over: Partial<View> = {}): View {
  return {
    kinds: [kind("notes", "Notes"), kind("sort-mail", "Sort mail", { fits: [fit("routine", { skills: 0, measured: 0, runs: 0, passes: 0, cost_per_pass_usd: null, status: "not_measured" }), fit("deep", { skills: 0, measured: 0, runs: 0, passes: 0, cost_per_pass_usd: null, status: "not_measured" })] }), kind("ex/draft-chapter", "Draft chapter", { fits: [fit("routine", { measured: 0, runs: 0, passes: 0, status: "not_measured", cost_per_pass_usd: null }), fit("deep", { status: "stale" })] })],
    tiers: [
      { name: "routine", account: "main", escalate_to: "deep", escalate_source: "file" },
      { name: "deep", account: "big", escalate_to: null, escalate_source: "default" },
    ],
    rules: [{ task: "notes", input_chars_over: null, quoted_messages_over: 3, data_level: null, tier: "deep" }],
    rules_source: "file",
    rule_suggestions: [],
    min_score: 0.8,
    confirm_above_usd: 0.1,
    per_run_usd: 0.25,
    ...over,
  };
}

/** A fake server that applies a settings save to what the routing view shows, as the real one does. */
function server(view: View, extra: Record<string, (body: unknown) => unknown> = {}) {
  let n = 1;
  return fakeApi({
    "GET ai/routing": () => view,
    "GET ai/accounts": () => ACCOUNTS,
    "GET ai/endpoints": () => [{ id: "service-a", name: "Service A", adapter: "a", base_url: "", needs_key: true, note: "" }],
    "GET settings": () => ({ fingerprint: `fp-${n}`, items: [] }),
    ...extra,
    "POST settings": (raw) => {
      const body = raw as S["SettingsSave"];
      if (body.fingerprint !== `fp-${n}`) return new Refuse(409, "The settings changed since you opened them. Look again, then save.");
      const changes: S["SettingChangeView"][] = [];
      const apply = (key: string, after: unknown, isReset: boolean) => {
        let before: unknown;
        const task = key.match(/^ai\.tasks\.(.+)\.tier$/);
        const tier = key.match(/^ai\.tiers\.(.+)\.escalate_to$/);
        if (task) {
          const k = view.kinds.find((x) => x.name === task[1])!;
          before = k.tier;
          k.tier = isReset ? k.default_tier : String(after);
          k.custom = !isReset;
          after = k.tier;
        } else if (tier) {
          const x = view.tiers.find((y) => y.name === tier[1])!;
          before = x.escalate_to;
          x.escalate_to = isReset ? null : String(after);
          after = x.escalate_to;
        } else if (key === "ai.routing") {
          before = view.rules.map((r) => ({ when: { task: r.task }, tier: r.tier }));
          view.rules = (after as Array<{ when: Record<string, unknown>; tier: string }>).map((r) => ({
            task: (r.when.task as string) ?? null,
            input_chars_over: (r.when.input_chars_over as number) ?? null,
            quoted_messages_over: (r.when.quoted_messages_over as number) ?? null,
            data_level: (r.when.data_level as never) ?? null,
            tier: r.tier,
          }));
        }
        changes.push({ key, before, after, was_default: false, is_default: isReset });
      };
      for (const [key, after] of Object.entries(body.changes ?? {})) apply(key, after, false);
      for (const key of body.reset ?? []) apply(key, null, true);
      n += 1;
      return { changes, fingerprint: `fp-${n}`, needs_restart: false };
    },
  });
}

const posted = (calls: ReturnType<typeof fakeApi>) => calls.filter((c) => c.route === "POST settings").map((c) => c.body);
const NOTES = "Filing what you hand in";
const rowOf = (name: string) => document.querySelector(`[data-kind="${name}"]`) as HTMLElement;

test("each kind of work has a list of the models to pick from, named in plain words with the account that does the work", async () => {
  server(start());
  renderApp(<AiRouting />);
  expect(await screen.findByRole("heading", { name: "Which model does what" })).toBeInTheDocument();
  const notes = within(rowOf("notes")).getByLabelText(NOTES) as HTMLSelectElement;
  expect(notes).toHaveValue("routine");
  expect(within(notes).getAllByRole("option").map((o) => o.textContent)).toEqual(["Everyday work · Main account", "Harder work · Strong account"]);
  expect(screen.queryByText(/routine|deep|tier/i)).toBeNull();
});

test("nothing is shown while no account is set up", async () => {
  server(start(), { "GET ai/accounts": () => [] });
  renderApp(<AiRouting />);
  await waitFor(() => expect(screen.queryByRole("heading", { name: "Which model does what" })).toBeNull());
});

test("choosing a model saves the setting as it is made, reads it back with Undo, and Undo puts the old one back", async () => {
  const user = userEvent.setup();
  const calls = server(start());
  renderApp(<AiRouting />);
  await user.selectOptions(await within(await screen.findByLabelText(NOTES).then(() => rowOf("notes"))).findByLabelText(NOTES), "deep");
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toEqual({ changes: { "ai.tasks.notes.tier": "deep" }, reset: [], fingerprint: "fp-1" });
  expect(await screen.findByText(`${NOTES} now goes to Harder work · Strong account.`)).toBeInTheDocument();
  expect(within(rowOf("notes")).getByText("Changed")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  expect(posted(calls)[1]).toEqual({ changes: { "ai.tasks.notes.tier": "routine" }, reset: [], fingerprint: "fp-2" });
});

test("Reset puts a kind of work back to what it uses without a choice", async () => {
  const user = userEvent.setup();
  const calls = server(start({ kinds: [kind("notes", "Notes", { tier: "deep", custom: true })] }));
  renderApp(<AiRouting />);
  await user.click(await screen.findByRole("button", { name: `Reset ${NOTES}` }));
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toEqual({ changes: {}, reset: ["ai.tasks.notes.tier"], fingerprint: "fp-1" });
  expect(await screen.findByText(`${NOTES} is back to Everyday work · Main account.`)).toBeInTheDocument();
});

test("what was measured is said with counts, a cost for each pass, and out of date or not measured where that is true", async () => {
  server(start());
  renderApp(<AiRouting />);
  await screen.findByLabelText(NOTES);
  const notes = within(rowOf("notes"));
  expect(notes.getByText("Everyday work · Main account: passes 18 of 20 · about $0.02 for each pass")).toBeInTheDocument();
  expect(notes.getByText("Harder work · Strong account: passes 20 of 20 · about $0.10 for each pass")).toBeInTheDocument();
  expect(within(rowOf("sort-mail")).getByText("No tests cover this kind of work yet, so nothing is measured for it.")).toBeInTheDocument();
  const chapter = within(rowOf("ex/draft-chapter"));
  expect(chapter.getByText("Everyday work · Main account: not measured yet")).toBeInTheDocument();
  expect(chapter.getByText(/Harder work · Strong account: out of date, passed 18 of 20 when last measured, so it doesn't count/)).toBeInTheDocument();
});

test("a partly measured or low result is said as it is, never as a pass", async () => {
  server(start({ kinds: [kind("notes", "Notes", { fits: [fit("routine", { measured: 1, status: "not_measured" }), fit("deep", { passes: 10, status: "below_min", below: 1 })] })] }));
  renderApp(<AiRouting />);
  await screen.findByLabelText(NOTES);
  const notes = within(rowOf("notes"));
  expect(notes.getByText(/measured for 1 of 2 skills, passes 18 of 20/)).toBeInTheDocument();
  expect(notes.getByText(/passes 10 of 20, below your pass mark/)).toBeInTheDocument();
});

test("a suggestion from the measurements is offered, and Use this saves it like any change, with Undo", async () => {
  const user = userEvent.setup();
  const calls = server(start({ kinds: [kind("notes", "Notes", { suggested_tier: "deep" })] }));
  renderApp(<AiRouting />);
  expect(await screen.findByText("Suggested from measurements: Harder work · Strong account")).toBeInTheDocument();
  expect(posted(calls)).toHaveLength(0); // never applied by itself
  await user.click(screen.getByRole("button", { name: `Use Harder work · Strong account for ${NOTES}` }));
  await waitFor(() => expect(posted(calls)).toEqual([{ changes: { "ai.tasks.notes.tier": "deep" }, reset: [], fingerprint: "fp-1" }]));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  expect(posted(calls)[1]).toMatchObject({ changes: { "ai.tasks.notes.tier": "routine" } });
});

test("when nothing qualifies the reason is said, and a kind that is already on the cheapest says so", async () => {
  server(
    start({
      kinds: [
        kind("notes", "Notes", { suggestion_why_not: "stale" }),
        kind("sort-mail", "Sort mail", { suggestion_why_not: "no_cases" }),
        kind("ex/draft-chapter", "Draft chapter", { suggested_tier: "routine" }),
      ],
    }),
  );
  renderApp(<AiRouting />);
  await screen.findByLabelText(NOTES);
  expect(within(rowOf("notes")).getByText("No suggestion yet: the measurements are out of date.")).toBeInTheDocument();
  expect(within(rowOf("sort-mail")).queryByText(/No suggestion/)).toBeNull();
  expect(within(rowOf("ex/draft-chapter")).getByText("The model it uses now is the cheapest that passed the tests.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^Use / })).toBeNull();
});

test("a failed answer's second try is a list per model, says when it happens, and Don't is a reset", async () => {
  const user = userEvent.setup();
  const calls = server(start());
  renderApp(<AiRouting />);
  expect(await screen.findByText(/only when the app's own checks find a problem, never because the model says it isn't sure/)).toBeInTheDocument();
  const routine = screen.getByLabelText("Everyday work · Main account", { selector: "select" }) as HTMLSelectElement;
  expect(routine).toHaveValue("deep");
  expect(within(routine).getAllByRole("option").map((o) => o.textContent)).toEqual(["Don't try again", "Try once more with Harder work · Strong account"]);
  const deep = screen.getByLabelText("Harder work · Strong account", { selector: "select" });
  expect(deep).toHaveValue("");
  expect(within(deep).queryByRole("option", { name: /Strong account/ })).toBeNull(); // not itself
  await user.selectOptions(routine, "");
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toEqual({ changes: {}, reset: ["ai.tiers.routine.escalate_to"], fingerprint: "fp-1" });
  await user.selectOptions(deep, "routine");
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  expect(posted(calls)[1]).toMatchObject({ changes: { "ai.tiers.deep.escalate_to": "routine" } });
});

test("the rules are rows with pick lists; changing one saves the whole list in order, and first match wins is said", async () => {
  const user = userEvent.setup();
  const calls = server(start());
  renderApp(<AiRouting />);
  expect(await screen.findByText(/the first one that fits decides/)).toBeInTheDocument();
  const rule = within(screen.getByRole("group", { name: "Rule 1" }));
  expect(rule.getByLabelText("Kind of work")).toHaveValue("notes");
  expect(rule.getByLabelText("Quotes more earlier messages than")).toHaveValue("3");
  expect(rule.getByLabelText("Longer than (characters)")).toHaveValue("");
  expect(within(rule.getByLabelText("How private it is")).getAllByRole("option").map((o) => o.textContent)).toEqual(["Any", "Open material", "Internal material", "Restricted material"]);
  await user.selectOptions(rule.getByLabelText("How private it is"), "restricted");
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toEqual({
    changes: { "ai.routing": [{ when: { task: "notes", quoted_messages_over: 3, data_level: "restricted" }, tier: "deep" }] },
    reset: [],
    fingerprint: "fp-1",
  });
  expect(await screen.findByText("Saved: 1 rule.")).toBeInTheDocument();
});

test("a number is saved when the cursor leaves the box, and a word in it is refused on the row without saving", async () => {
  const user = userEvent.setup();
  const calls = server(start());
  renderApp(<AiRouting />);
  const chars = await screen.findByLabelText("Longer than (characters)");
  await user.type(chars, "20x");
  await user.tab();
  expect(await screen.findByText("Enter a whole number.")).toBeInTheDocument();
  expect(posted(calls)).toHaveLength(0);
  await user.clear(chars);
  await user.type(chars, "20000");
  await user.tab();
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toMatchObject({ changes: { "ai.routing": [{ when: { task: "notes", input_chars_over: 20000, quoted_messages_over: 3 }, tier: "deep" }] } });
});

test("a new rule waits, unsaved, until it says when it applies, then is saved at the end of the list; the cursor starts in it", async () => {
  const user = userEvent.setup();
  const calls = server(start());
  renderApp(<AiRouting />);
  await user.click(await screen.findByRole("button", { name: "Add a rule" }));
  const added = within(screen.getByRole("group", { name: "Rule 2" }));
  expect(added.getByLabelText("Kind of work")).toHaveFocus();
  expect(added.getByText(/Say when this rule applies/)).toBeInTheDocument();
  expect(posted(calls)).toHaveLength(0); // a rule with no condition would send everything
  await user.selectOptions(added.getByLabelText("Kind of work"), "sort-mail");
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect((posted(calls)[0] as { changes: Record<string, unknown> }).changes["ai.routing"]).toEqual([
    { when: { task: "notes", quoted_messages_over: 3 }, tier: "deep" },
    { when: { task: "sort-mail" }, tier: "deep" },
  ]);
});

test("a rule moves up or down and is removed from its menu, each saved with Undo", async () => {
  const user = userEvent.setup();
  const calls = server(
    start({
      rules: [
        { task: "notes", input_chars_over: null, quoted_messages_over: 3, data_level: null, tier: "deep" },
        { task: "sort-mail", input_chars_over: null, quoted_messages_over: null, data_level: null, tier: "deep" },
      ],
    }),
  );
  renderApp(<AiRouting />);
  await screen.findByRole("group", { name: "Rule 2" });
  await user.click(screen.getByRole("button", { name: "More actions for Rule 2" }));
  await user.click(await screen.findByRole("menuitem", { name: "Move up" }));
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect((posted(calls)[0] as { changes: Record<string, unknown> }).changes["ai.routing"]).toEqual([
    { when: { task: "sort-mail" }, tier: "deep" },
    { when: { task: "notes", quoted_messages_over: 3 }, tier: "deep" },
  ]);
  await waitFor(() => expect(within(screen.getByRole("group", { name: "Rule 1" })).getByLabelText("Kind of work")).toHaveValue("sort-mail"));
  await user.click(screen.getByRole("button", { name: "More actions for Rule 1" }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove" }));
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  expect((posted(calls)[1] as { changes: Record<string, unknown> }).changes["ai.routing"]).toEqual([{ when: { task: "notes", quoted_messages_over: 3 }, tier: "deep" }]);
  expect((await screen.findAllByRole("button", { name: "Undo" })).length).toBeGreaterThan(0);
  await waitFor(() => expect(screen.queryByRole("group", { name: "Rule 2" })).toBeNull());
});

test("a suggested rule is offered under the rules and added only when the person says so", async () => {
  const user = userEvent.setup();
  const calls = server(
    start({
      rules: [],
      rule_suggestions: [{ rule: { task: "notes", input_chars_over: null, quoted_messages_over: 3, data_level: null, tier: "deep" }, skills: ["Acting on the new message"] }],
    }),
  );
  renderApp(<AiRouting />);
  expect(await screen.findByText(new RegExp(`Suggested: send ${NOTES} to Harder work · Strong account when it quotes more than 3 earlier messages\\. Acting on the new message measured under your pass mark`))).toBeInTheDocument();
  expect(posted(calls)).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: `Add the rule: send ${NOTES} to Harder work · Strong account` }));
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect((posted(calls)[0] as { changes: Record<string, unknown> }).changes["ai.routing"]).toEqual([{ when: { task: "notes", quoted_messages_over: 3 }, tier: "deep" }]);
});

test("a change made elsewhere since the screen opened is refused in plain words on the row, and what was chosen is tried again after looking", async () => {
  const user = userEvent.setup();
  let moved = false;
  const calls = server(start(), {
    "GET settings": () => ({ fingerprint: moved ? "fp-9" : "fp-1", items: [] }),
  });
  renderApp(<AiRouting />);
  const notes = await screen.findByLabelText(NOTES);
  await user.click(notes); // opened as fp-1 is known
  moved = true;
  await user.selectOptions(notes, "deep");
  expect(await within(rowOf("notes")).findByRole("alert")).toHaveTextContent("This was changed since you opened it.");
  expect(posted(calls)).toHaveLength(1);
  expect(notes).toHaveValue("routine"); // what is saved
});

test("after the refusal what changed elsewhere is refreshed and listed with when, and the choice that was refused is not applied", async () => {
  const user = userEvent.setup();
  const first = start();
  let moved = false;
  const calls = server(first, {
    "GET ai/routing": () => ({ ...first, kinds: first.kinds.map((k) => (moved && k.name === "sort-mail" ? { ...k, tier: "deep", custom: true } : k)) }),
    "GET settings": () => ({ fingerprint: moved ? "fp-9" : "fp-1", changed_at: "2026-10-20T09:14:00Z", items: [] }),
  });
  renderApp(<AiRouting />);
  const notes = await screen.findByLabelText(NOTES);
  await user.click(notes);
  moved = true;
  await user.selectOptions(notes, "deep");
  const lines = await screen.findByRole("status", { name: "Refreshed from what is saved now" });
  expect(lines).toHaveTextContent(/refreshed: Sorting mail is now Harder work, changed elsewhere at .*\d/);
  expect(lines).not.toHaveTextContent("Filing what you hand in");
  await waitFor(() => expect(screen.getByLabelText("Sorting mail")).toHaveValue("deep"));
  expect(notes).toHaveValue("routine");
  expect(posted(calls)).toHaveLength(1);
});

test("the spending line says when the stronger model needs the person's go, from the amounts in the settings", async () => {
  server(start({ confirm_above_usd: 0.5, per_run_usd: 2 }));
  renderApp(<AiRouting />);
  const line = await screen.findByText(/follows your spending limits/);
  expect(line).toHaveTextContent("more than $0.50");
  expect(line).toHaveTextContent("or the amount you already agreed to");
  expect(line).toHaveTextContent("more than $2.00 is started");
});

test("a rule set outside the app can be read but not changed", async () => {
  server(start({ rules_source: "env" }));
  renderApp(<AiRouting />);
  const rule = within(await screen.findByRole("group", { name: "Rule 1" }));
  expect(rule.getByLabelText("Kind of work")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Add a rule" })).toBeDisabled();
  expect(screen.getAllByText("Set outside the app by an environment variable").length).toBeGreaterThan(0);
});
