// The time spent looking over the assistant's work (design 6.20, "Measured"): a screen that does so counts the seconds it
// was open and in view, and says so once when the person leaves it. The count is the app's own, kept on the person's
// computer; nothing is measured outside the app, and a failure to say so is never shown.
import { useEffect } from "react";
import { api, type S } from "./api";

type Screen = S["ReviewTimeIn"]["screen"];

export function useReviewTime(screen: Screen, on = true): void {
  useEffect(() => {
    if (!on) return;
    let counted = 0;
    let since: number | null = document.visibilityState === "visible" ? Date.now() : null;
    const stop = () => {
      if (since !== null) counted += Date.now() - since;
      since = null;
    };
    const change = () => {
      if (document.visibilityState === "visible") since = since ?? Date.now();
      else stop();
    };
    document.addEventListener("visibilitychange", change);
    return () => {
      document.removeEventListener("visibilitychange", change);
      stop();
      const seconds = Math.round(counted / 1000);
      if (seconds >= 1) void api.reviewTime({ screen, seconds }).catch(() => undefined);
    };
  }, [screen, on]);
}
