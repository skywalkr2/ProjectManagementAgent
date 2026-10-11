// What a person can start on an item or on the whole workspace, offered by the enabled plugins.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

/** The actions for one item; with no item, the ones that work on the whole workspace. */
export function usePluginActions(kind?: string, id?: string) {
  return useQuery({
    queryKey: ["plugin-actions", kind ?? null, id ?? null],
    queryFn: () => api.pluginActions(kind, id),
  });
}
