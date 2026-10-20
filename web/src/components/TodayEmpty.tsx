// What Today says when nothing needs the person (design 7.7), by where the setup stands: with no AI service it says to connect
// one, with one but nothing yet worked on it says what to hand in, and only once the assistant has worked on something does
// it say that nothing needs them and offer "Missed one".
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { NothingNeedsYou } from "./Coverage";
import { MissedOneLine } from "./MissedOne";

export function TodayEmpty(props: { className?: string; onContinueSetup?: () => void; onHandIn?: () => void }) {
  const { t } = useWords();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  if (!status.data) return null;
  const noAi = status.data.ai.state === "not_set_up" || status.data.ai.state === "stand_in";
  if (noAi) {
    return (
      <p className={props.className} data-queue-empty="connect">
        {t("queue.empty.connect")}{" "}
        {props.onContinueSetup && (
          <Button size="sm" variant="primary" onClick={props.onContinueSetup}>
            {t("queue.empty.continue_setup")}
          </Button>
        )}
      </p>
    );
  }
  if (status.data.assistant.last_run_at === null) {
    return (
      <p className={props.className} data-queue-empty="first">
        {t("queue.empty.hand_in")}{" "}
        {props.onHandIn && (
          <Button size="sm" variant="primary" onClick={props.onHandIn}>
            {t("handin.open")}
          </Button>
        )}
      </p>
    );
  }
  return (
    <>
      <NothingNeedsYou className={props.className} />
      <MissedOneLine className={props.className} />
    </>
  );
}
