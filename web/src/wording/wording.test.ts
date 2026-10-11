// Every key the code uses is in the wording sheet, and every family of keys built at run time is complete.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import sheet from "./en.json";
import schema from "../api/openapi.json";

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
  const s = (schema as { components: { schemas: Record<string, { properties: Record<string, { enum?: string[] }> }> } })
    .components.schemas;
  const states = s.ChangeItem.properties.state.enum ?? [];
  const opStatuses = s.OpView.properties.status.enum ?? [];
  const expected = [
    ...states.map((x) => `changes.state.${x}`),
    ...opStatuses.map((x) => `op.status.${x}`),
    "op.status.owner",
    ...["attention", "done", "all"].map((x) => `changes.filter.${x}`),
    ...["connecting", "live", "offline"].filter((x) => x !== "live").map((x) => `live.${x}`),
    ...["next", "previous", "primary", "send_back", "copy", "edit", "undo", "hand_in", "ask", "help"].map((x) => `help.${x}`),
    ...["notes", "other"].map((x) => `task.${x}`),
    ...["project", "other"].map((x) => `stages.group.${x}`),
    ...["you", "rule", "undo"].map((x) => `stages.by_${x}`),
    "changes.second.other_account",
    "changes.second.same_account",
    ...["ok", "failed"].map((x) => `setup.job_${x}`),
    "setup.job_other",
    ...["workspace", "template", "ai", "backup", "people", "first_note"].flatMap((x) => [`setup_step.${x}`, `setup_step.${x}.explanation`]),
    ...["stdin", "file"].map((x) => `welcome.ai.packet_via.${x}`),
    ...["stdout", "outbox"].map((x) => `welcome.ai.output_via.${x}`),
    ...["open", "internal", "restricted"].map((x) => `welcome.ai.data.${x}`),
    ...["number", "integer"].map((x) => `settings.invalid.${x}`),
    ...(s.AskView.properties.state.enum ?? []).map((x) => `ask.state.${x}`),
    ...(s.AutoClosedView.properties.change.enum ?? []).map((x) => `sources.closed.change.${x}`),
    ...(s.SettingProposalView.properties.status.enum ?? []).filter((x) => x !== "open").map((x) => `ask.proposal.${x}`),
    ...(s.ReportView.properties.status.enum ?? []).filter((x) => x !== "draft").map((x) => `ask.report_status.${x}`),
    ...(s.SignInView.properties.status.enum ?? []).map((x) => `sign_in.status.${x}`),
    ...["done", "failed", "refused", "expired"].map((x) => `sign_in.return.${x}`),
    "op.note.under",
    "op.note.none",
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
