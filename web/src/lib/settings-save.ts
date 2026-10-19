// What follows any saved settings (the Settings screen and the guided setup steps): the question about restarting when a change needs one, a refresh of
// what the saved files change, and a toast that reads back what changed with Undo.
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, type S } from "./api";
import { useRestart } from "./restart";
import { formatValue, labelForKey, undoBody } from "./settings";
import { useToasts } from "./toasts";
import { useWords } from "./wording";

const SHOWN = 3;

/** Where the newest settings fingerprint this screen knows is kept: the one a save answered with, so the next save, and an
 * Undo of an earlier one, never go out with an old one. A reload of the settings replaces it. */
const FINGERPRINT = ["settings-fingerprint"] as const;

export const rememberFingerprint = (client: QueryClient, fingerprint: string) => client.setQueryData(FINGERPRINT, fingerprint);

/** The fingerprint to save against: the newest one a save answered with, else the one the settings loaded with. */
export const knownFingerprint = (client: QueryClient, loaded?: string): string | undefined =>
  client.getQueryData<string>(FINGERPRINT) ?? loaded;

export function useAfterSave() {
  const client = useQueryClient();
  const { push } = useToasts();
  const { t, has } = useWords();
  const restart = useRestart();
  return useCallback(
    (saved: S["SettingsSaved"], opts: { message?: string } = {}): Promise<void> => {
      rememberFingerprint(client, saved.fingerprint);
      if (saved.needs_restart) restart.offer();
      const refreshed = client.invalidateQueries();
      if (!saved.changes.length) {
        push({ message: opts.message ?? t("settings.nothing_changed") });
        return refreshed;
      }
      const known = client.getQueryData<S["SettingsView"]>(["settings"])?.items ?? [];
      const label = (key: string) => labelForKey(key, known, t, has);
      const line = (c: S["SettingChangeView"]) =>
        c.is_default
          ? t("settings.saved_default", { label: label(c.key), value: formatValue(c.after, t) })
          : t("settings.saved_line", { label: label(c.key), value: formatValue(c.after, t) });
      const lines = saved.changes.slice(0, SHOWN).map(line);
      if (saved.changes.length > SHOWN) lines.push(t("settings.saved_more", { n: saved.changes.length - SHOWN }));
      push({
        message: opts.message ?? t("settings.saved", { changes: lines.join("; ") }),
        undo: async () => {
          // Saves made since then moved the fingerprint on; a change made elsewhere still gets the refusal.
          const undone = await api.saveSettings(undoBody(saved.changes, knownFingerprint(client, saved.fingerprint) ?? saved.fingerprint));
          rememberFingerprint(client, undone.fingerprint);
          if (undone.needs_restart) restart.offer();
          await client.invalidateQueries();
        },
      });
      return refreshed;
    },
    [client, push, t, has, restart],
  );
}

/** The fingerprint of the settings as they are now, read fresh, so a change made meanwhile is noticed, not overwritten. */
export function useFreshFingerprint() {
  const client = useQueryClient();
  return useCallback(
    async () => (await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 })).fingerprint,
    [client],
  );
}
