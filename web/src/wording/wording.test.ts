// Every key the code uses is in the wording sheet, and every family of keys built at run time is complete.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import sheet from "./en.json";
import schema from "../api/openapi.json";
import { holdsRawData } from "../lib/raw-data";

const words = sheet as Record<string, string>;
const root = join(__dirname, "..");

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && !name.endsWith(".d.ts") ? [path] : [];
  });
}

const code = sources(root).map((p) => readFileSync(p, "utf-8")).join("\n");

test("every literal key exists", () => {
  const used = new Set<string>();
  for (const m of code.matchAll(/\bt\(\s*"([a-z_]+(?:\.[a-z_]+)+)"/g)) used.add(m[1]);
  for (const m of code.matchAll(/\?\s*"([a-z_]+(?:\.[a-z_]+)+)"\s*:\s*"([a-z_]+(?:\.[a-z_]+)+)"/g)) {
    used.add(m[1]);
    used.add(m[2]);
  }
  const plural = new Set<string>();
  for (const m of code.matchAll(/\btn\(\s*"([a-z_]+(?:\.[a-z_]+)+)"/g)) plural.add(m[1]);
  const missing = [...used].filter((k) => !(k in words) && !plural.has(k));
  const missingPlural = [...plural].flatMap((k) => [`${k}.one`, `${k}.other`]).filter((k) => !(k in words));
  expect(missing).toEqual([]);
  expect(missingPlural).toEqual([]);
});

test("key families built at run time are complete", () => {
  const s = (
    schema as {
      components: {
        schemas: Record<string, { properties: Record<string, { enum?: string[]; items?: { enum?: string[] }; additionalProperties?: boolean | { enum?: string[] } }> }>;
      };
    }
  ).components.schemas;
  const roles = s.EndpointView.properties.model_roles.additionalProperties;
  const modelRoles = typeof roles === "object" ? (roles.enum ?? []) : [];
  expect(modelRoles.length).toBeGreaterThan(0);
  const states = s.ChangeItem.properties.state.enum ?? [];
  const opStatuses = s.OpView.properties.status.enum ?? [];
  const expected = [
    ...states.map((x) => `changes.state.${x}`),
    ...opStatuses.map((x) => `op.status.${x}`),
    "op.status.owner",
    ...["attention", "done", "all"].map((x) => `changes.filter.${x}`),
    ...["connecting", "live", "offline"].filter((x) => x !== "live").map((x) => `live.${x}`),
    ...["next", "previous", "primary", "send_back", "copy", "edit", "move", "undo", "hand_in", "ask", "show_new", "help"].map((x) => `help.${x}`),
    ...["notes", "other"].map((x) => `task.${x}`),
    ...["project", "other"].map((x) => `stages.group.${x}`),
    ...["you", "rule", "undo"].map((x) => `stages.by_${x}`),
    "changes.second.other_account",
    "changes.second.same_account",
    ...["ok", "failed"].map((x) => `setup.job_${x}`),
    "setup.job_other",
    ...["workspace", "ai", "mail", "backup", "people", "template", "first_note", "addons"].flatMap((x) => [`setup_step.${x}`, `setup_step.${x}.explanation`]),
    ...(s.WalkthroughView.properties.step.enum ?? []).flatMap((x) => [`walkthrough.screen.${x}`, `walkthrough.why.${x}`]),
    ...["done", "skipped"].map((x) => `walkthrough.state.${x}`),
    ...["done", "skipped", "todo"].map((x) => `walkthrough.done.${x}`),
    ...["not_installed", "off", "restart", "problem", "ready"].map((x) => `walkthrough.mail.state.${x}`),
    ...(s.PackSummary.properties.reads.items?.enum ?? []).map((x) => `walkthrough.mail.reads.${x}`),
    ...modelRoles.map((x) => `welcome.ai.role.${x}`),
    ...["stdin", "file"].map((x) => `welcome.ai.packet_via.${x}`),
    ...["stdout", "outbox"].map((x) => `welcome.ai.output_via.${x}`),
    ...["open", "internal", "restricted"].map((x) => `welcome.ai.data.${x}`),
    ...["number", "integer"].map((x) => `settings.invalid.${x}`),
    ...(s.AskView.properties.state.enum ?? []).map((x) => `ask.state.${x}`),
    ...(s.AutoClosedView.properties.change.enum ?? []).map((x) => `sources.closed.change.${x}`),
    ...(s.SilentCloseView.properties.how.enum ?? []).map((x) => `sources.silent.how.${x}`),
    ...(s.SinceEntryView.properties.act.enum ?? []).flatMap((x) => [`since.act.${x}`, `queue.since.count.${x}`]),
    ...(s.SinceEntryView.properties.because.enum ?? []).map((x) => `since.why.${x}`),
    ...(s.SettingProposalView.properties.status.enum ?? []).filter((x) => x !== "open").map((x) => `ask.proposal.${x}`),
    ...(s.ReportView.properties.status.enum ?? []).filter((x) => x !== "draft").map((x) => `ask.report_status.${x}`),
    ...(s.SignInView.properties.status.enum ?? []).map((x) => `sign_in.status.${x}`),
    ...(s.ActView.properties.status.enum ?? []).flatMap((x) => [`outgoing.state.${x}`, `outgoing.state_long.${x}`]),
    ...(s.ActView.properties.kind.enum ?? []).flatMap((x) => [
      `outgoing.title.${x}`,
      `outgoing.what.${x}`,
      `outgoing.confirm.${x}`,
      `outgoing.confirm.again.${x}`,
      `outgoing.today.uncertain.${x}`,
    ]),
    ...(s.ActFailureView.properties.kind.enum ?? []).map((x) => `outgoing.failure.${x}`),
    ...(s.ActRecipientView.properties.reasons.items?.enum ?? []).map((x) => `outgoing.callout.${x}`),
    ...(s.ActRecipientView.properties.role.enum ?? []).map((x) => `outgoing.role.${x}`),
    ...["channel", "target", "about", "account", "content", "template"].map((x) => `outgoing.changed.${x}`),
    ...["reply", "reply_all", "forward"].flatMap((x) => [`outgoing.title.message.${x}`, `outgoing.what.message.${x}`]),
    ...["archive", "move", "label", "mark_read"].flatMap((x) => [`outgoing.title.mailbox.${x}.one`, `outgoing.title.mailbox.${x}.other`]),
    ...["accepted", "tentative", "declined", "propose"].flatMap((x) => [`outgoing.title.calendar.answer.${x}`, `outgoing.answer_line.${x}`, `acts.answer.${x}`]),
    "outgoing.title.calendar.create",
    "outgoing.what.calendar.create",
    "outgoing.what.calendar.answer",
    ...(s.DataFile.properties.layer.enum ?? []).map((x) => `dataform.layer.${x}`),
    ...["done", "failed", "refused", "expired"].map((x) => `sign_in.return.${x}`),
    "op.note.under",
    "op.note.none",
    ...["email", "calendar", "change", "note", "pasted"].flatMap((x) => [`fact.src.kind.${x}`, `fact.src.kind_a.${x}`]),
    ...["due", "target", "org", "to", "text", "how_to_reach", "why_they_matter"].map((x) => `field.${x}`),
    "record.by_assistant.unnamed",
    ...(s.ProposalView.properties.came_from.enum ?? []).map((x) => `learned.from.${x}`),
    ...(s.KnowsTerm.properties.confidence.enum ?? []).map((x) => `knows.confidence.${x}`),
    ...["status", "phase", "target", "owner", "summary"].map((x) => `knows.unknown.${x}`),
    ...["pasted", "email", "calendar", "change", "note", "task", "other"].map((x) => `knows.kind.${x}`),
    ...(s.AiState.properties.state.enum ?? []).filter((x) => x !== "ok").flatMap((x) => ["title", "todo"].map((y) => `ai.${x}.${y}`)),
    ...["action.add", "action.close", "question.add", "question.done", "fact", "note", "record.set", "record.log", "person.add"].map((x) => `op.${x}`),
  ];
  expect(expected.filter((k) => !(k in words))).toEqual([]);
});

test("no internal terms reach the screen", () => {
  const internal = /\b(changeset|op|ops|ledger|tier|payload|held)\b/i;
  const leaks = Object.entries(words).filter(([, text]) => internal.test(text.replace(/\{\w+\}/g, "")));
  expect(leaks).toEqual([]);
});

// The same patterns as the server's wording check (api/screen_text.py): text the screen shows never names a settings
// file, a secret reference, a settings key, a manifest field or a command. The settings files' names and the command
// line's subcommands are listed here by hand; a server test checks that this list is the command line's own.
const SETTINGS_FILES = ["workspace", "server", "storage", "ai", "dispatch", "checks", "language", "ui", "stages", "rules", "watch", "steward"];
const COMMANDS = [
  "ai",
  "backup",
  "config",
  "demo",
  "evaluate",
  "export",
  "import",
  "init",
  "install",
  "pack",
  "restore",
  "selfcheck",
  "serve",
  "start",
  "sync",
  "takeover",
  "template",
  "update",
];
const VCS = "pull|push|commit|clone|checkout|status|add|merge|rebase|fetch|log|diff|reset|stash|init|config|remote|tag|branch";

/** Entries that may name a command because they are shown only under a "For developers" disclosure. */
const COMMAND_ALLOWED = new Set(["addons.demo_command"]);

function wordingProblems(text: string): string[] {
  const found: string[] = [];
  for (const m of text.matchAll(/\S*\.ya?ml\b/g)) found.push(`names a settings file: ${m[0]}`);
  for (const m of text.matchAll(/\bsettings? files?\b/gi)) found.push(`names a settings file: ${m[0]}`);
  for (const m of text.matchAll(/\b(?:env|keychain):|\bfile:\/|\bfile:~/g)) found.push(`names a secret reference: ${m[0]}`);
  for (const m of text.matchAll(/\b(?:requires|provides)\.[a-z_]+|\bplugin_api\b/g)) found.push(`names a manifest field: ${m[0]}`);
  const key = new RegExp(`(?<![\\w.-])(?:${SETTINGS_FILES.join("|")})(?:\\.[A-Za-z_][\\w-]*)+(?![\\w-])`, "g");
  for (const m of text.matchAll(key)) found.push(`names a settings key: ${m[0]}`);
  for (const m of text.matchAll(/\bcockpit ([a-z][a-z-]*)/g)) if (COMMANDS.includes(m[1])) found.push(`names a command: ${m[0]}`);
  const other = new RegExp(`\\buv (?:run|sync|lock|pip|tool)\\b|\\bnpm [a-z]+|\\bgit (?:${VCS})\\b`, "g");
  for (const m of text.matchAll(other)) found.push(`names a command: ${m[0]}`);
  return found;
}

test("the wording check finds what it should and lets look-alikes through", () => {
  expect(wordingProblems("see ai.yaml").length).toBeGreaterThan(0);
  expect(wordingProblems("The settings file refers to it, and your Settings Files too")).toHaveLength(2);
  expect(wordingProblems("use env:NAME or file:/path")).toHaveLength(2);
  expect(wordingProblems("raise ai.budgets.per_run_usd")).toHaveLength(1);
  expect(wordingProblems("requires.secrets and plugin_api")).toHaveLength(2);
  expect(wordingProblems("run `cockpit serve` or uv run pytest")).toHaveLength(2);
  expect(wordingProblems("e.g. example.com, notes.md, version 1.2.3, and the end.")).toEqual([]);
  expect(wordingProblems("the cockpit restarts; git history stays")).toEqual([]);
});

test("no entry names a settings file, a secret reference, a settings key, a manifest field or a command", () => {
  const leaks = Object.entries(words).flatMap(([name, text]) =>
    wordingProblems(text)
      .filter((p) => !(COMMAND_ALLOWED.has(name) && p.startsWith("names a command")))
      .map((p) => `${name}: ${p}`),
  );
  expect(leaks).toEqual([]);
});

// With the assistant's default name, a line that says "{assistant}" would read "Assistant is on it", as if it were a name.
// Every such entry has an `.unnamed` variant that says "your assistant", and a variant never names the assistant itself.
test("every entry that names the assistant has a variant for an assistant that was never named", () => {
  const named = Object.entries(words).filter(([key, text]) => !key.endsWith(".unnamed") && text.includes("{assistant}"));
  expect(named.map(([key]) => key).filter((key) => !(`${key}.unnamed` in words))).toEqual([]);
  const variants = Object.entries(words).filter(([key]) => key.endsWith(".unnamed"));
  expect(variants.filter(([, text]) => text.includes("{assistant}")).map(([key]) => key)).toEqual([]);
  expect(variants.filter(([key]) => !(key.slice(0, -".unnamed".length) in words)).map(([key]) => key)).toEqual([]);
});

test("a variant keeps the placeholders of the line it stands in for", () => {
  const holes = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).filter((name) => name !== "assistant").sort();
  const off = Object.entries(words)
    .filter(([key]) => key.endsWith(".unnamed"))
    .filter(([key, text]) => JSON.stringify(holes(text)) !== JSON.stringify(holes(words[key.slice(0, -".unnamed".length)] ?? "")))
    .map(([key]) => key);
  expect(off).toEqual([]);
});

test("no entry of the sheet shows raw data: no braces around a quoted key and no data structure in a line", () => {
  const raw = Object.entries(words).filter(([, text]) => holdsRawData(text));
  expect(raw.map(([key]) => key)).toEqual([]);
});

// The setup path (the first-run review's N5): what a person with no IT background reads while setting the app up. No time
// zone id, language tag, secret reference, IMAP, port, TLS, token, CLI or command; what has to stay technical lives under
// Advanced, in keys that say so (`.advanced.`). The server's test (tests/test_setup_path_words.py) reaches the labels and
// descriptions that come from config schemas, connectors and add-on manifests; this one reaches the wording sheet.
const SETUP_PREFIXES = [
  "walkthrough.",
  "welcome.",
  "setup_step.",
  "start.",
  "settings.key.",
  "settings.group.",
  "settings.section.",
  "settings.option.",
  "sign_in.",
  "secret.",
  "folders.",
  "notices.",
  "timezone.",
  "queue.empty",
  "money.",
];
const SETUP_TERMS: [string, RegExp][] = [
  ["a time zone id", /\b(?:Africa|America|Antarctica|Arctic|Asia|Atlantic|Australia|Europe|Indian|Pacific)\/[A-Za-z_]+/],
  ["a language tag", /\b[a-z]{2,3}-[A-Z]{2}\b/],
  ["a secret reference", /\b(?:env|keychain):|\bfile:\/|\bfile:~/],
  ["IMAP", /\bIMAP\b/i],
  ["a port", /\bports?\b/i],
  ["TLS", /\bTLS\b/],
  ["a token", /\btokens?\b/i],
  ["the command line", /\bCLI\b|\bcommands?\b/i],
];
const setupProblems = (text: string): string[] => SETUP_TERMS.filter(([, pattern]) => pattern.test(text)).map(([name]) => name);

test("the setup-path check finds a technical word and lets look-alikes through", () => {
  for (const text of ["such as Europe/Paris", "as en-US", "env:NAME", "its IMAP host", "the port", "over TLS", "about 4,000 tokens", "the CLI", "its command"]) {
    expect(setupProblems(text).length, text).toBeGreaterThan(0);
  }
  for (const text of ["Yes/No and/or", "A report on transport", "Pick the city nearest you.", "American or British spelling", "Commanding views"]) {
    expect(setupProblems(text), text).toEqual([]);
  }
});

test("no entry on the setup path names a time zone id, a language tag, a secret reference, IMAP, a port, TLS, a token, the CLI or a command", () => {
  const leaks = Object.entries(words)
    .filter(([key]) => SETUP_PREFIXES.some((p) => key.startsWith(p)) && !key.split(".").includes("advanced"))
    .flatMap(([key, text]) => setupProblems(text).map((p) => `${key}: ${p}`));
  expect(leaks).toEqual([]);
});

// Before an op is decided it says what it would do, never that it did it (design 7.6): every op that says what was done has
// a conditional twin that starts with "Would", and a past-tense review title for one thing says what the assistant did.
test("every op that says what was done has a conditional twin, 'Would …', for the time before it is decided", () => {
  const done = Object.keys(words).filter((k) => k.startsWith("op.") && !/^op\.(status|because|show_source|hide_source|undo_this|do_anyway|meta|would)\b/.test(k));
  expect(done.filter((k) => !(`op.would.${k.slice(3)}` in words))).toEqual([]);
  const twins = Object.entries(words).filter(([k]) => k.startsWith("op.would."));
  expect(twins.filter(([k]) => !(`op.${k.slice("op.would.".length)}` in words)).map(([k]) => k)).toEqual([]);
  expect(twins.filter(([, text]) => !/^Would /.test(text)).map(([k]) => k)).toEqual([]);
});

test("a review title for one thing the assistant did is in the past tense and names the assistant", () => {
  const did = Object.entries(words).filter(([k]) => k.startsWith("queue.review.did.") && !k.endsWith(".unnamed"));
  expect(did.length).toBeGreaterThan(0);
  expect(did.filter(([, text]) => !text.startsWith("{assistant} ") || !text.includes("{item}")).map(([k]) => k)).toEqual([]);
  expect(did.filter(([, text]) => /^\{assistant\} (add|close|drop|move|mark|take|ask|file|record)\b/i.test(text)).map(([k]) => k)).toEqual([]);
});

// Money has no picker: every amount is in US dollars, and the first amount of a screen or its field label says so in
// plain words rather than with a code (design Part 7, "Money has no picker").
test("amounts are labeled as US dollars in plain words where a currency is named", () => {
  for (const key of ["setup.budget", "welcome.spend.intro", "settings.group.ai.budgets", "addons.intro", "addons.costs_hint"]) {
    expect(words[key], key).toContain("US dollars");
  }
  expect(Object.entries(words).filter(([, text]) => /\bUSD\b/.test(text)).map(([key]) => key)).toEqual([]);
});
