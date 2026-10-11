// Starting what a plugin offers, from any screen: a person action opens its review; a kind of AI work starts at once
// and says so in a toast. Render `review` once beside the buttons.
import { useCallback } from "react";
import type { ActionTarget } from "../components/ActionReview";
import { useActionReview } from "../components/ActionReview";
import { api } from "./api";
import { useAct } from "./act";
import type { Offer } from "./plugin-actions";
import { useWords } from "./wording";

export function usePluginRun() {
  const { t } = useWords();
  const act = useAct();
  const { start, review } = useActionReview();
  const run = useCallback(
    (offer: Offer, target: ActionTarget, returnTo?: () => HTMLElement | null | undefined) => {
      if (offer.is === "action") {
        start({ name: offer.name, label: offer.label, on: offer.on }, target, returnTo);
        return;
      }
      void act(
        () => api.startTask(offer.name, target),
        () => ({ message: t("task.started", { what: offer.label }) }),
      );
    },
    [act, start, t],
  );
  return { run, review };
}
