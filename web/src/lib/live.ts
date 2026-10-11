// Live updates: the server's event stream says when anything changed, and every query refreshes. No polling.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { EVENTS_PATH } from "./api";

export type LiveState = "connecting" | "live" | "offline";

/** `hellos` counts how many times the stream has (re)connected, so a caller can wait for the next one. */
export function useLive(): { state: LiveState; lastUpdate: Date | null; hellos: number } {
  const client = useQueryClient();
  const [state, setState] = useState<LiveState>("connecting");
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [hellos, setHellos] = useState(0);
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(EVENTS_PATH);
    source.addEventListener("hello", () => {
      setState("live");
      setHellos((n) => n + 1);
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
  return { state, lastUpdate, hellos };
}
