// Amounts of money in plain words; the currency symbol and the wording around it come from the sheet.
import { useWords } from "./wording";

/** An amount to two decimals, or "less than a cent" when it would round to nothing. */
export function useMoney() {
  const { t } = useWords();
  return (usd: number) => (usd < 0.005 ? t("money.under_cent") : t("money.usd", { amount: usd.toFixed(2) }));
}

/** A total to two decimals; zero is $0.00 and a sum under a cent is still shown as an amount. */
export function useTotal() {
  const { t } = useWords();
  return (usd: number) => t("money.usd", { amount: usd.toFixed(2) });
}

/** "About $0.80" for an estimate, or null when there isn't one. */
export function useEstimate() {
  const { t } = useWords();
  const money = useMoney();
  return (usd: number | null | undefined) =>
    usd == null ? null : usd < 0.005 ? t("cost.under_cent") : t("cost.about", { amount: money(usd) });
}

/** An amount with at least two significant digits, so a small price is not lost to rounding: 0.004 stays 0.004. */
export function useSmallMoney() {
  const { t } = useWords();
  return (usd: number) => {
    const places = usd > 0 ? Math.min(8, Math.max(2, 1 - Math.floor(Math.log10(usd)))) : 2;
    const text = usd.toFixed(places).replace(/(\.\d\d)(\d*?)0+$/, "$1$2");
    return t("money.usd", { amount: text });
  };
}
