// The wording sheet: every user-facing string comes from here, with overrides from the workspace's config/ui.yaml.
import { createContext, useContext, useMemo, type ReactNode } from "react";
import sheet from "../wording/en.json";

export type Words = Record<string, string>;
export type Vars = Record<string, string | number>;

const WordsContext = createContext<{ words: Words; base: Vars }>({ words: sheet, base: {} });

export function format(words: Words, key: string, vars: Vars = {}): string {
  const template = words[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (name in vars ? String(vars[name]) : match));
}

export function WordingProvider(props: { overrides?: Words; base?: Vars; children: ReactNode }) {
  const value = useMemo(
    () => ({ words: { ...sheet, ...(props.overrides ?? {}) }, base: props.base ?? {} }),
    [props.overrides, props.base],
  );
  return <WordsContext.Provider value={value}>{props.children}</WordsContext.Provider>;
}

export function useWords() {
  const { words, base } = useContext(WordsContext);
  return useMemo(() => {
    const t = (key: string, vars: Vars = {}) => format(words, key, { ...base, ...vars });
    const tn = (key: string, n: number, vars: Vars = {}) => t(`${key}.${n === 1 ? "one" : "other"}`, { n, ...vars });
    return { t, tn };
  }, [words, base]);
}
