// Wording helpers for files: sizes and accepted types in plain words.
import { useWords } from "./wording";

export function useSize() {
  const { t } = useWords();
  return (bytes: number): string => {
    const one = (n: number) => (n >= 10 || Number.isInteger(n) ? Math.round(n) : Math.round(n * 10) / 10);
    if (bytes < 1024) return t("size.b", { n: bytes });
    if (bytes < 1024 ** 2) return t("size.kb", { n: one(bytes / 1024) });
    if (bytes < 1024 ** 3) return t("size.mb", { n: one(bytes / 1024 ** 2) });
    return t("size.gb", { n: one(bytes / 1024 ** 3) });
  };
}

/** A list of media types as words ("PNG images, plain text and PDF documents"); a type the sheet doesn't name shows as it is. */
export function useTypeWords() {
  const { t, has } = useWords();
  return (types: string[]): string => {
    const words = types.map((type) => (has(`media.${type}`) ? t(`media.${type}`) : type));
    if (words.length < 2) return words.join("");
    return t("media.list", { first: words.slice(0, -1).join(", "), last: words[words.length - 1] });
  };
}
