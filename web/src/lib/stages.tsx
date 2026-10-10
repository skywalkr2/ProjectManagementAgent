// Shared pieces of the stage screens: the queries, plain-words labels, and the one way to run a move or a go so that
// the Stages view and Today behave the same (act at once, offer Undo, show a refusal on the row).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { api, ApiError, type S } from "./api";
import { useToasts, type ToastInput } from "./toasts";
import { useWords } from "./wording";

export type StageView = S["StageView"];
export type StageRequest = S["StageRequestView"];

export function useStageRecords() {
  return useQuery({ queryKey: ["stages", "records"], queryFn: api.stageRecords });
}

export function useStageReady() {
  return useQuery({ queryKey: ["stages", "ready"], queryFn: api.stageReady });
}

export function useStageRequests() {
  return useQuery({ queryKey: ["stages", "requests"], queryFn: api.stageRequests });
}

/** Stage tasks that wait for the person's go. */
export function waitingForGo(requests: StageRequest[] | undefined): StageRequest[] {
  return (requests ?? []).filter((r) => r.approval === "required" && r.state === "needs_you");
}

export const sameItem = (a: { kind: string; id: string }, b: { kind: string; record?: string; id?: string }) =>
  a.kind === b.kind && a.id === (b.record ?? b.id);

/** What a kind of task is called in plain words; kinds the sheet doesn't name read as the assistant's work. */
export function useTaskWords() {
  const { t, has } = useWords();
  return (kind: string) => (has(`task.${kind}`) ? t(`task.${kind}`) : t("task.other"));
}

/** The heading for a kind of item; kinds the sheet doesn't name share a generic one. */
export function useKindWords() {
  const { t, has } = useWords();
  return (kind: string) => (has(`stages.group.${kind}`) ? t(`stages.group.${kind}`) : t("stages.group.other"));
}

export function upperFirst(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Run one action for a row: refetch afterwards, toast with Undo when it can be undone, and keep a refusal for the row. */
export function useRowAction() {
  const client = useQueryClient();
  const { push } = useToasts();
  const { t } = useWords();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const run = useCallback(
    async <T,>(call: () => Promise<T>, toast: (result: T) => ToastInput) => {
      if (running.current) return undefined;
      running.current = true;
      setBusy(true);
      setError(null);
      try {
        const result = await call();
        await client.invalidateQueries();
        const done = toast(result);
        const undo = done.undo;
        push({
          ...done,
          undo: undo
            ? async () => {
                await undo();
                await client.invalidateQueries();
              }
            : undefined,
        });
        return result;
      } catch (err) {
        const signedOut = err instanceof ApiError && err.status === 401;
        const detail = err instanceof ApiError ? err.detail : "";
        setError(signedOut ? t("error.signed_out") : t("error.failed", { detail }).trim());
        return undefined;
      } finally {
        running.current = false;
        setBusy(false);
      }
    },
    [client, push, t],
  );
  return { error, busy, run };
}

/** Move an item to a stage, sending the version that was read; Undo goes through the changeset undo route. */
export function useMove() {
  const { t } = useWords();
  const { error, busy, run } = useRowAction();
  const move = (view: StageView, to: S["StageLabel"]) =>
    run(
      () => api.stageMove({ record: view.record, to: to.id, read_version: view.version }),
      (moved) => ({
        message: t("toast.stage_moved", { title: view.title, stage: to.label }),
        undo: async () => {
          const report = await api.undo(moved.changeset);
          if (!report.restored.length) throw new Error("not undone");
        },
      }),
    );
  return { error, busy, move };
}

/** Give the go for a waiting stage task, sending the request version that was read. */
export function useGo() {
  const { t } = useWords();
  const { error, busy, run } = useRowAction();
  const go = (request: StageRequest) =>
    run(
      () => api.stageGo(request.id, request.version),
      () => ({ message: t("toast.stage_go") }),
    );
  return { error, busy, go };
}
