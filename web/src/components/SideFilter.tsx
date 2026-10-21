// The All / Personal / <business> choice beside the heading of Today and of Follow-ups (design 6.32). It is there only for
// a person who has set a business; the pick is the same on both screens and is remembered on this browser.
import { useSideFilter, type SideChoice } from "../lib/sides";
import { useWords } from "../lib/wording";
import { SegmentedControl } from "../ui/SegmentedControl";

export function SideFilter() {
  const { t } = useWords();
  const filter = useSideFilter();
  if (!filter.offered || !filter.business) return null;
  return (
    <SegmentedControl<SideChoice>
      label={t("sides.filter.label")}
      value={filter.choice}
      onChange={filter.set}
      options={[
        { value: "all", label: t("sides.filter.all") },
        { value: "personal", label: t("sides.filter.personal") },
        { value: "business", label: filter.business },
      ]}
    />
  );
}
