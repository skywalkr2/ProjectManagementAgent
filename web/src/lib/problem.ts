// A refusal from the server in plain words: its own text when it gave one, otherwise a general message.
import { ApiError } from "./api";

type T = (key: string, vars?: Record<string, string | number>) => string;

const REFUSALS = new Set([409, 413, 422]);

export function problemText(err: unknown, t: T): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return t("error.signed_out");
    if (REFUSALS.has(err.status) && err.detail) return err.detail;
    return t("error.failed", { detail: err.detail }).trim();
  }
  return t("error.failed", { detail: "" }).trim();
}
