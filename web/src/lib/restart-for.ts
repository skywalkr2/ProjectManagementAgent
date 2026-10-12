// What waits for a restart, said in plain words from the status and the settings' own labels.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { RESTART_OWN, restartWhat } from "./settings";
import { useWords } from "./wording";

/** A sentence naming what a restart would bring in, or an empty text when the app doesn't say. */
export function useRestartWhat(): string {
  const { t, has } = useWords();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const keys = status.data?.restart_for ?? [];
  // The labels are only needed when a setting is what waits.
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: keys.some((k) => !RESTART_OWN[k]) });
  return restartWhat(keys, settings.data?.items ?? [], t, has);
}
