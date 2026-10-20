// Under the accent color in Settings → Appearance: the measured contrast of the text on it, and a warning in words when it
// fails WCAG AA (design 7.9, 7.10). It follows what is typed, before it is saved.
import { accentContrast } from "../lib/theme";
import { useWords } from "../lib/wording";

export function BrandContrast(props: { color: string }) {
  const { t } = useWords();
  const found = accentContrast(props.color);
  if (!found) return null;
  const ratio = found.ratio.toFixed(1);
  return (
    <p className={found.ok ? "hint" : "problem-note"} role="status" aria-label={t("brand.contrast_title")}>
      {t(found.ok ? "brand.contrast_ok" : "brand.contrast_fail", { ratio })}
    </p>
  );
}
