// Value lists: the values a field may take. The lists are read once and shared; a change to one acts at once and offers
// Undo, like every other reversible action.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, type S } from "./api";
import { problemText } from "./problem";
import { useToasts } from "./toasts";
import { useWords } from "./wording";

export type ValueList = S["ValueListView"];

export function useValueLists() {
  return useQuery({ queryKey: ["lists"], queryFn: api.valueLists });
}

/** Whether a list offers a value, ignoring capitals. */
export function offers(values: string[], value: string): string | undefined {
  const wanted = value.trim().toLocaleLowerCase();
  return values.find((v) => v.toLocaleLowerCase() === wanted);
}

/** Run a change to a list: refresh what is shown and offer Undo. Returns the problem in plain words when the server
 * refused it, and an empty string when it went through, so the caller can show the problem beside what was typed. */
export function useListChange() {
  const client = useQueryClient();
  const { push } = useToasts();
  const { t } = useWords();
  return useCallback(
    async (run: () => Promise<S["Applied"]>, message: string): Promise<string> => {
      try {
        const done = await run();
        await client.invalidateQueries();
        push({
          message,
          undo: async () => {
            const report = await api.undo(done.changeset);
            await client.invalidateQueries();
            if (!report.restored.length) throw new Error("not undone");
          },
        });
        return "";
      } catch (err) {
        return problemText(err, t);
      }
    },
    [client, push, t],
  );
}
