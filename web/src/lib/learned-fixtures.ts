// Records for the tests of the learning screens: a proposal, a line under a card, a project and a person.
import type { S } from "./api";

export function proposal(over: Partial<S["ProposalView"]> = {}): S["ProposalView"] {
  return {
    id: "LES-1",
    kind: "lesson",
    version: 3,
    text: "Interior files go to the editor before the printer.",
    status: "proposed",
    learned_from: "assistant",
    trust: "trusted",
    learned_at: "2026-10-09T14:00:00Z",
    applies_to: { task_kinds: ["notes"], projects: ["PRJ-1"], scope: "projects" },
    evidence: { quote: "go to the editor first", signal: "SIG-1" },
    came_from: "correction",
    batch: "daily",
    just_this_time_before: 0,
    more_evidence: [],
    used: 0,
    given: 0,
    ...over,
  };
}

export function learnedLine(over: Partial<S["LearnedLine"]> = {}): S["LearnedLine"] {
  return { signal: "SIG-1", kind: "sent_back", changeset: "CS-1", refs: ["CS-1"], state: "proposed", proposal: proposal(), ...over };
}

export function project(id: string, name: string): S["ProjectView"] {
  return {
    id,
    name,
    group: null,
    language: "en-US",
    language_own: false,
    role: "run",
    completed: false,
    open_actions: 0,
    open_questions: 0,
    owner: null,
    owner_name: null,
    phase: null,
    spent_usd: 0,
    status: null,
    summary: null,
    target: null,
  };
}

export function person(id: string, name: string): S["PersonView"] {
  return { id, name, aliases: [], is_pm: false, open_items: 0, role: null, status: "active", track_only: false };
}
