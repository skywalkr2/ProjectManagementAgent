// What a queue line opens (design 7.7): its items in full, with the buttons that deal with them. It is the inspector from
// 1680px and expands under the line below that. The pieces are the ones the Work screens use (a change's card, a
// person's message to copy, a question's answer form), so a line and its screen can never disagree.
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { QueueLine } from "../lib/today";
import { useWords } from "../lib/wording";
import { Skeleton } from "../ui/Skeleton";
import { DecisionRow, PersonSection, WaitingSection } from "./FollowUps";
import { TodoRow } from "./TodayRail";
import { ChangeRow } from "./WhatChanged";

/** The kinds of line that open to items; the rest are a single act on the line itself. */
const OPENS = new Set<QueueLine["kind"]>(["decision", "question", "who_is", "owner", "held", "go", "refused", "failed", "review", "send", "nudge", "overdue"]);

export function opensItems(line: QueueLine): boolean {
  return OPENS.has(line.kind);
}

export function LineDetail(props: { line: QueueLine; sendBack?: boolean; onOpenGuide?: (step: string) => void }) {
  const { line } = props;
  switch (line.kind) {
    case "decision":
    case "question":
    case "owner":
    case "who_is":
      return <QuestionDetail line={line} onOpenGuide={props.onOpenGuide} />;
    case "send":
      return <SendDetail line={line} />;
    case "nudge":
      return <NudgeDetail line={line} />;
    case "overdue":
      return <OverdueDetail line={line} />;
    default:
      return <ChangeDetail line={line} sendBack={props.sendBack} onOpenGuide={props.onOpenGuide} />;
  }
}

function Gone() {
  const { t } = useWords();
  return <p className="hint">{t("queue.detail.gone")}</p>;
}

/** The change a line is about: the same card What changed shows, open, with its buttons. */
function ChangeDetail(props: { line: QueueLine; sendBack?: boolean; onOpenGuide?: (step: string) => void }) {
  const changes = useQuery({ queryKey: ["changes"], queryFn: api.changes });
  if (changes.isPending) return <Skeleton />;
  const item = changes.data?.find((c) => c.id === props.line.request);
  if (!item) return <Gone />;
  return (
    <ol className="queue">
      <ChangeRow item={item} reveal={0} open sendBack={props.sendBack} onOpenGuide={props.onOpenGuide} />
    </ol>
  );
}

/** A question put to the person: the answer form, or the choice of who or which one. A name the assistant couldn't place
 * is asked as a question too; when it has none the change that holds it is what opens. */
function QuestionDetail(props: { line: QueueLine; onOpenGuide?: (step: string) => void }) {
  const followups = useQuery({ queryKey: ["followups"], queryFn: api.followups });
  if (followups.isPending) return <Skeleton />;
  const question = followups.data?.find((s) => s.is_pm)?.questions.find((q) => q.id === props.line.question);
  if (!question) return props.line.request ? <ChangeDetail line={props.line} onOpenGuide={props.onOpenGuide} /> : <Gone />;
  return (
    <ul className="children">
      <DecisionRow question={question} reveal={0} />
    </ul>
  );
}

/** What is ready to send to a person: the message in a box, to copy and then mark as sent. */
function SendDetail(props: { line: QueueLine }) {
  const followups = useQuery({ queryKey: ["followups"], queryFn: api.followups });
  if (followups.isPending) return <Skeleton />;
  const section = followups.data?.find((s) => !s.is_pm && s.person === props.line.person);
  if (!section) return <Gone />;
  return (
    <ol className="queue">
      <PersonSection section={section} open />
    </ol>
  );
}

/** What a person hasn't answered: each item with the step that closes it. */
function NudgeDetail(props: { line: QueueLine }) {
  const followups = useQuery({ queryKey: ["followups"], queryFn: api.followups });
  if (followups.isPending) return <Skeleton />;
  const section = followups.data?.find((s) => !s.is_pm && s.person === props.line.person);
  if (!section) return <Gone />;
  return (
    <ol className="queue">
      <WaitingSection section={section} compact nudgeOpen />
    </ol>
  );
}

/** The person's own overdue to-dos, each to mark done. */
function OverdueDetail(props: { line: QueueLine }) {
  const todo = useQuery({ queryKey: ["today", "todo"], queryFn: api.todo });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  if (todo.isPending) return <Skeleton />;
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  const rows = (todo.data ?? []).filter((x) => (props.line.actions ?? []).includes(x.action));
  if (rows.length === 0) return <Gone />;
  return (
    <ul className="tb-list">
      {rows.map((item) => (
        <TodoRow key={item.action} item={item} project={item.project ? (names.get(item.project) ?? "") : ""} showDue />
      ))}
    </ul>
  );
}
