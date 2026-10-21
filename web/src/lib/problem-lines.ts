// The lines Send feedback adds for the last problems: one block per problem, in the person's own words, with exactly
// what the server sent (already masked). The same text is shown in the preview and goes in the email.
import type { S } from "./api";

type Words = (key: string, vars?: Record<string, string | number>) => string;

const PARAM_LABEL: Record<string, string> = {
  tier: "feedback.problem.param.tier",
  model: "feedback.problem.param.model",
  temperature: "feedback.problem.param.temperature",
  max_output: "feedback.problem.param.max_output",
  effort: "feedback.problem.param.effort",
  send_temperature: "feedback.problem.param.send_temperature",
  json_mode: "feedback.problem.param.json_mode",
  max_tokens_param: "feedback.problem.param.max_tokens_param",
  effort_param: "feedback.problem.param.effort_param",
};

/** The time as the server wrote it, as "2026-10-21 09:00 +10:00" (or "UTC"), so a maintainer can place it. */
export function problemTime(at: string): string {
  const m = at.match(/^(\d{4}-\d\d-\d\d)T(\d\d:\d\d)(?::\d\d(?:\.\d+)?)?(Z|[+-]\d\d:\d\d)?$/);
  if (!m) return at;
  return `${m[1]} ${m[2]} ${!m[3] || m[3] === "Z" ? "UTC" : m[3]}`;
}

function doing(p: S["FeedbackProblem"], t: Words): string {
  const what = p.what ?? "";
  switch (p.doing) {
    case "task":
      return what ? t("feedback.problem.doing.task", { what }) : t("feedback.problem.doing.task_unnamed");
    case "account_check":
      return what ? t("feedback.problem.doing.account_check_part", { what }) : t("feedback.problem.doing.account_check");
    case "source_read":
      return what ? t("feedback.problem.doing.source_read_kind", { what }) : t("feedback.problem.doing.source_read");
    default:
      return what ? t("feedback.problem.doing.app_where", { what }) : t("feedback.problem.doing.app");
  }
}

/** One problem's lines: when, what was being done, the account, the request's settings, the answer and the error text. */
export function problemBlock(p: S["FeedbackProblem"], t: Words): string[] {
  const lines = [problemTime(p.at), doing(p, t)];
  if (p.service) lines.push(t("feedback.problem.service", { service: p.service }));
  if (p.adapter) lines.push(t("feedback.problem.adapter", { adapter: p.adapter }));
  if (p.program_version) lines.push(t("feedback.problem.program", { version: p.program_version }));
  const settings = Object.entries(p.params ?? {}).map(([name, value]) => `${PARAM_LABEL[name] ? t(PARAM_LABEL[name]) : name}: ${value}`);
  if (settings.length) lines.push(t("feedback.problem.request", { settings: settings.join("; ") }));
  if (p.status != null) lines.push(t("feedback.problem.status", { status: p.status }));
  if (p.error_kind) lines.push(t("feedback.problem.kind", { kind: p.error_kind }));
  if (p.text) lines.push(t("feedback.problem.text", { text: p.text }));
  return lines;
}

/** The whole section for the message: a heading, then each problem's block with a blank line between. */
export function problemLines(problems: S["FeedbackProblem"][], t: Words): string[] {
  if (problems.length === 0) return [];
  return [t("feedback.problems_heading"), ...problems.flatMap((p, i) => (i === 0 ? problemBlock(p, t) : ["", ...problemBlock(p, t)]))];
}
