// The assistant's state on Today (design 7.7): one plain row when the assistant can't do its work yet, saying what is
// wrong in plain words, the provider's own reason when there is one, and what to do. Nothing shows when all is well.
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useWords } from "../lib/wording";

export function AssistantNotice() {
  const { t } = useWords();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const ai = status.data?.ai;
  if (!ai || ai.state === "ok") return null;
  const what =
    ai.state === "failing"
      ? ai.detail
        ? t("ai.failing.what", { reason: ai.detail })
        : t("ai.failing.what_unknown")
      : t(ai.state === "untested" ? "ai.untested.what" : "ai.not_set_up.what");
  return (
    <section className="notice" aria-labelledby="ai-notice-title" data-ai-state={ai.state}>
      <span className="mark" aria-hidden="true">
        !
      </span>
      <div className="notice-text">
        <p>
          <strong id="ai-notice-title">
            <span className="sr">{t("ai.needs_attention")}: </span>
            {t(ai.state === "failing" ? "ai.failing.title" : ai.state === "untested" ? "ai.untested.title" : "ai.not_set_up.title")}
          </strong>
        </p>
        <p>{what}</p>
        <p className="hint">
          {t(ai.state === "failing" ? "ai.failing.todo" : ai.state === "untested" ? "ai.untested.todo" : "ai.not_set_up.todo")}
        </p>
      </div>
    </section>
  );
}
