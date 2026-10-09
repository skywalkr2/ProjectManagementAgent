// Running an action: call the server, refresh, and say what happened in a toast (with Undo when it can be undone).
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { ApiError } from "./api";
import { useToasts, type ToastInput } from "./toasts";
import { useWords } from "./wording";

export function useAct() {
  const client = useQueryClient();
  const { push } = useToasts();
  const { t } = useWords();
  return useCallback(
    async <T,>(run: () => Promise<T>, after?: (result: T) => Omit<ToastInput, "undo"> & { undo?: () => Promise<unknown> }) => {
      try {
        const result = await run();
        await client.invalidateQueries();
        if (after) {
          const toast = after(result);
          const undo = toast.undo;
          push({
            ...toast,
            undo: undo
              ? async () => {
                  await undo();
                  await client.invalidateQueries();
                }
              : undefined,
          });
        }
        return result;
      } catch (err) {
        const detail = err instanceof ApiError ? err.detail : "";
        const signedOut = err instanceof ApiError && err.status === 401;
        push({ message: signedOut ? t("error.signed_out") : t("error.failed", { detail }) });
        return undefined;
      }
    },
    [client, push, t],
  );
}
