// The short tag for what came from outside (design 7.7, 12.8): "Outside" to look at, the full phrase as its name for a
// screen reader and in its tooltip. Where the content itself is shown (the inspector, the source block) the full phrase
// stays on the screen instead.
import { useWords } from "../lib/wording";
import { Pill } from "./Pill";

export function OutsideTag() {
  const { t } = useWords();
  const full = t("source.outside");
  return (
    <span title={full} data-outside="">
      <Pill tone="neutral" describedAs={full}>
        {t("source.outside_short")}
      </Pill>
    </span>
  );
}
