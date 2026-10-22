// What the words typed for a to-do's day are read as, asked of the server once typing pauses; nothing while empty.
import { useEffect, useState } from "react";
import { api, type S } from "./api";

export function useDayCheck(words: string): S["TodoDayView"] | null {
  const [found, setFound] = useState<{ asked: string; view: S["TodoDayView"] } | null>(null);
  const typed = words.trim();
  useEffect(() => {
    if (!typed) return;
    let current = true;
    const timer = setTimeout(() => {
      api
        .checkTodoDay({ words: typed })
        .then((view) => current && setFound({ asked: typed, view }))
        .catch(() => current && setFound(null));
    }, 250);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [typed]);
  return typed && found?.asked === typed ? found.view : null;
}
