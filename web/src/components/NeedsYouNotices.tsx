// A browser notice for what comes into Today's Decide group while the app is open (design 7.19), when notices and the
// browser are on and the person has allowed them. What was waiting when the app opened is not announced: the person is
// looking at it. It carries the server's words, a count and never what an item is about.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "../lib/api";
import { notifyState, showNotification } from "../lib/notify";

export function useNeedsYouNotices() {
  const waiting = useQuery({ queryKey: ["notifications-waiting"], queryFn: api.notificationsWaiting });
  // The items the person has been told about, or was looking at when the app opened.
  const told = useRef<Set<string> | null>(null);
  const data = waiting.data;
  useEffect(() => {
    if (!data) return;
    if (told.current === null) {
      told.current = new Set(data.keys);
      return;
    }
    const before = told.current;
    const ready = data.browser && notifyState() === "granted";
    // In quiet hours, or before the browser allows them, an item stays news until it can be shown.
    if (ready && data.keys.some((key) => !before.has(key))) showNotification(data.message, undefined, "needs-you");
    told.current = new Set(ready ? data.keys : data.keys.filter((key) => before.has(key)));
  }, [data]);
}
