// What follows any saved settings (the Settings screen and the guided setup steps): the restart notice, a refresh of
// what the saved files change, and a toast that reads back what changed with Undo.
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, type S } from "./api";
import { useRestart } from "./restart";
import { formatValue, labelOf, undoBody } from "./settings";
import { useToasts } from "./toasts";
import { useWords } from "./wording";

const SHOWN = 3;

export function useAfterSave() {
  const client = useQueryClient();
  const { push } = useToasts();
  const { t, has } = useWords();
  const restart = useRestart();
  return useCallback(
    (saved: S["SettingsSaved"], opts: { message?: string } = {}): Promise<void> => {
      if (saved.restarts) restart.begin();
      const refreshed = client.invalidateQueries();
      if (!saved.changes.length) {
        push({ message: opts.message ?? t("settings.nothing_changed") });
        return refreshed;
      }
      const known = client.getQueryData<S["SettingsView"]>(["settings"])?.items ?? [];
      const label = (key: string) => {
        const item = known.find((i) => i.key === key);
        return item ? labelOf(item, t, has) : key;
      };
      const line = (c: S["SettingChangeView"]) =>
        c.is_default
          ? t("settings.saved_default", { label: label(c.key), value: formatValue(c.after, t) })
          : t("settings.saved_line", { label: label(c.key), value: formatValue(c.after, t) });
      const lines = saved.changes.slice(0, SHOWN).map(line);
      if (saved.changes.length > SHOWN) lines.push(t("settings.saved_more", { n: saved.changes.length - SHOWN }));
      push({
        message: opts.message ?? t("settings.saved", { changes: lines.join("; ") }),
        undo: async () => {
          const undone = await api.saveSettings(undoBody(saved.changes, saved.fingerprint));
          if (undone.restarts) restart.begin();
          await client.invalidateQueries();
        },
      });
      return refreshed;
    },
    [client, push, t, has, restart],
  );
}
