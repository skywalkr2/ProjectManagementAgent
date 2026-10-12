// Packs in plain words: the price, what a pack adds, reaches and keeps, and the size of its AI work. Everything here
// takes text from outside as text and returns text; the wording around it comes from the sheet.
import type { S } from "./api";

type T = (key: string, vars?: Record<string, string | number>) => string;
type Tn = (key: string, n: number, vars?: Record<string, string | number>) => string;

export type Summary = S["PackSummary"];
export type Price = S["PackPrice"];

/** A price in the words the screen uses; the amount is formatted by the caller (it knows the currency). */
export function priceText(price: Price, amount: (value: number, currency: string) => string, t: T): string {
  const base = (() => {
    if (price.model === "free") return t("addons.price.free");
    if (price.amount == null || price.model === "see_publisher") return t("addons.price.see_publisher");
    const shown = amount(price.amount, price.currency);
    if (price.model === "one_time") return t("addons.price.one_time", { amount: shown });
    if (price.period === "month") return t("addons.price.month", { amount: shown });
    if (price.period === "year") return t("addons.price.year", { amount: shown });
    return t("addons.price.subscription", { amount: shown });
  })();
  const note = price.note.trim();
  return note ? t("addons.price.with_note", { price: base, note }) : base;
}

/** What a pack adds, one line per thing, with nothing listed for a zero. */
export function addsLines(adds: Summary["adds"], t: T, tn: Tn): string[] {
  const lines: string[] = [];
  if (adds.item_types.length) lines.push(t("addons.adds.item_types", { types: adds.item_types.join(", ") }));
  if (adds.screens) lines.push(tn("addons.adds.screens", adds.screens));
  if (adds.today) lines.push(tn("addons.adds.today", adds.today));
  if (adds.ai_work) lines.push(tn("addons.adds.ai_work", adds.ai_work));
  if (adds.actions) lines.push(tn("addons.adds.actions", adds.actions));
  if (adds.setup_steps) lines.push(tn("addons.adds.setup_steps", adds.setup_steps));
  if (adds.sources) lines.push(tn("addons.adds.sources", adds.sources));
  return lines;
}

/** What a pack reaches outside the app; one line saying so when it reaches nothing. */
export function reachesLines(reaches: Summary["reaches"], t: T): string[] {
  const lines: string[] = [];
  if (reaches.sign_ins.length) lines.push(t("addons.reaches.sign_ins", { names: reaches.sign_ins.join(", ") }));
  if (reaches.hosts.length) lines.push(t("addons.reaches.hosts", { hosts: reaches.hosts.join(", ") }));
  if (reaches.programs.length) lines.push(t("addons.reaches.programs", { programs: reaches.programs.join(", ") }));
  if (reaches.keys) lines.push(t("addons.reaches.keys", { n: reaches.keys }));
  return lines.length ? lines : [t("addons.reaches.nothing")];
}

/** What a service reaches, in the plain words the walkthrough uses: no internal names, one line for each thing. */
export function serviceReachLines(reaches: Summary["reaches"], t: T, tn: Tn): string[] {
  const lines: string[] = [];
  if (reaches.sign_ins.length) lines.push(t("walkthrough.mail.reaches.sign_in"));
  if (reaches.hosts.length) lines.push(t("walkthrough.mail.reaches.hosts", { hosts: reaches.hosts.join(", ") }));
  if (reaches.programs.length) lines.push(t("walkthrough.mail.reaches.programs", { programs: reaches.programs.join(", ") }));
  if (reaches.keys) lines.push(tn("walkthrough.mail.reaches.keys", reaches.keys));
  return lines.length ? lines : [t("addons.reaches.nothing")];
}

export function keepsText(keeps: Summary["keeps"], t: T): string {
  return t(`addons.keeps.${keeps}`);
}

/** Tokens as words of AI work (0.75 words to a token), rounded to two significant figures. */
export function wordsOfWork(tokens: number): number {
  const words = Math.max(0, tokens) * 0.75;
  if (words < 100) return Math.max(1, Math.round(words));
  return Number(words.toPrecision(2));
}

/** One AI job's cost on the person's own accounts: a price, or the size of the work, or that nothing is set up for it. */
export function costText(
  cost: S["PackCost"],
  t: T,
  money: (usd: number) => string,
  size: (n: number) => string,
): string {
  if (!cost.account) return t("addons.cost.no_account", { label: cost.label });
  if (cost.usd != null) return t("addons.cost.usd", { label: cost.label, amount: money(cost.usd) });
  return t("addons.cost.size", { label: cost.label, size: size(wordsOfWork(cost.tokens)) });
}

/** A pack id from outside is only put into a copyable command when it is a plain name. */
export const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._/-]*$/;

/** The newer version a pack offers, when the one installed differs from it. */
export function updateOffered(pack: S["PackView"]): boolean {
  return pack.installed_version != null && !!pack.version && pack.installed_version !== pack.version;
}

/** An add-on whose saved setting and running state differ without a reason given: one just turned on isn't running yet,
 * one just turned off still is, and either changes at the next restart. */
export const waitsForRestart = (item: S["InstalledPackView"]) =>
  item.enabled ? item.state !== "enabled" && !item.reason : item.state === "enabled";
