// The demo label: a strip above the header on every screen when the workspace holds made-up data. It is part of the
// page (not a message), can't be dismissed, and says "Demo" in words so the status never rests on color.
import { useWords } from "../lib/wording";

export function DemoStrip() {
  const { t } = useWords();
  return (
    <aside className="demo-strip" aria-label={t("demo.region")}>
      <strong className="demo-tag">{t("demo.label")}</strong>
      <span>{t("demo.text")}</span>
    </aside>
  );
}
