// Live updates: the server's event stream says when anything changed, and every query refreshes. No polling.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { EVENTS_PATH } from "./api";

export type LiveState = "connecting" | "live" | "offline";

export function useLive(): { state: LiveState; lastUpdate: Date | null } {
  const client = useQueryClient();
  const [state, setState] = useState<LiveState>("connecting");
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(EVENTS_PATH);
    source.addEventListener("hello", () => {
      setState("live");
      setLastUpdate(new Date());
      void client.invalidateQueries();
    });
    source.addEventListener("changed", () => {
      setLastUpdate(new Date());
      void client.invalidateQueries();
    });
    source.onerror = () => setState("offline");
    return () => source.close();
  }, [client]);
  return { state, lastUpdate };
}
