"""How well the app's own token count matches what each account really counts (design 6.16, "Estimates learn from use").

The app counts tokens from characters (about four to a token). Real services count differently, by model, and a
command-line agent adds a fixed amount of its own text to every request. Both are kept per account on this computer, in
the workspace's private folder, beside the other results of the account check:

- the **ratio** of real tokens to the app's own count, per account and model: measured at the account check by one
  count request on a fixed sample (for an adapter that can count without running the request), then moved by every
  finished run whose service reported its input tokens (a running average over the last runs, `ai.estimates.
  calibration_runs`), with no extra call;
- the **fixed overhead** per request of an adapter that adds its own text to every request, measured at the check from
  its small call's reported input tokens, less what the call's own text counts.

An account that can't count and reports nothing has ratio 1 and no overhead. Every estimate of a price goes through
`tokens_for`. What is kept is data about this computer, not a setting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.state_file import changing, write_whole

STATE_FILE = "ai-calibration.json"

#: A ratio outside these bounds is a measurement that went wrong (a near-empty text, an overhead not yet measured), so
#: it is never kept.
RATIO_BOUNDS = (0.2, 10.0)
#: The most recent ratios kept for an account's model, whatever `calibration_runs` says.
KEPT_SAMPLES = 200

#: The fixed text the account check counts. It is plain prose, long enough that a small fixed cost per request doesn't
#: move the ratio, and it is never sent to a model to be run.
SAMPLE_INSTRUCTIONS = "This is a measurement of how a request is counted."
SAMPLE_REQUEST = " ".join(
    [
        "A small team keeps a shared list of the work in front of it. Every morning one person reads the new messages,"
        " files each one against the piece of work it belongs to, and writes down what is waiting on whom.",
        "Some messages ask a question, some give a date, and some only say that a thing is done. The team checks the"
        " dates against its calendar, asks the person who owns a task whether it moved, and drops what nobody needs.",
        "At the end of the week the list is read aloud, short items first. Numbers such as 12, 45 and 2031 appear, as"
        " do words that are long or rare: reconciliation, provisional, itinerary.",
        "When a date slips, the owner says why in a sentence, and the reader of the list decides whether anyone else"
        " needs to hear about it.",
    ]
    * 3
)


def estimate_tokens(chars: int) -> int:
    """A rough token count from characters: about four characters per token in English text, rounded up."""
    return -(-chars // 4)


@dataclass(frozen=True)
class Calibration:
    """What is known about how an account's model counts: the ratio of real tokens to the app's own count and the
    fixed tokens its adapter adds to every request."""

    ratio: float = 1.0
    overhead: int = 0


def tokens_for(chars: int, calibration: Calibration | None = None) -> int:
    """The tokens a request of this many characters is expected to use on an account: the app's own count times the
    account model's ratio, rounded up, plus the account's fixed overhead per request."""
    found = calibration or Calibration()
    return -(-round(estimate_tokens(chars) * found.ratio * 1000) // 1000) + found.overhead


def scaled(tokens: int, calibration: Calibration | None = None) -> int:
    """The same for a count the caller already made with the app's own measure: times the ratio, plus the overhead."""
    found = calibration or Calibration()
    return -(-round(max(0, tokens) * found.ratio * 1000) // 1000) + found.overhead


def _path(where: Any) -> Path:
    return Path(where.private_dir) / STATE_FILE


def _read(where: Any) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_path(where).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return (
        {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(data, dict) else {}
    )


def _write(where: Any, data: dict[str, dict[str, Any]]) -> None:
    write_whole(_path(where), json.dumps(data, sort_keys=True, indent=2) + "\n")


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _samples(row: Any) -> list[float]:
    found = row.get("samples") if isinstance(row, dict) else None
    return [x for x in (_number(v) for v in found) if x is not None] if isinstance(found, list) else []


def lookup(where: Any, account: str, model: str, runs: int = 20) -> Calibration:
    """The calibration of an account's model: the average of the last `runs` ratios kept (1 when there are none) and
    the account's fixed overhead (0 when none was measured)."""
    row = _read(where).get(account, {})
    models = row.get("models") if isinstance(row.get("models"), dict) else {}
    samples = _samples(models.get(model))[-max(1, runs) :]
    ratio = sum(samples) / len(samples) if samples else 1.0
    overhead = _number((row.get("overhead") or {}).get("tokens")) if isinstance(row.get("overhead"), dict) else None
    return Calibration(ratio, max(0, round(overhead)) if overhead is not None else 0)


def measured(where: Any, account: str) -> dict[str, Any]:
    """What is kept for an account, for a screen or a report: its overhead and when it was measured, and for each model
    its last ratio and when the check measured it."""
    return _read(where).get(account, {})


def _bounded(ratio: float) -> bool:
    return RATIO_BOUNDS[0] <= ratio <= RATIO_BOUNDS[1]


def record_check(
    where: Any,
    account: str,
    model: str,
    *,
    counted: int | None,
    sample_chars: int,
    now: datetime | None = None,
) -> float | None:
    """Keep the ratio an account check measured for a model: `counted` real tokens for a sample of `sample_chars`
    characters. The measurement replaces the ratios kept so far for the model. Returns the ratio, or None when
    nothing was counted (an account that can't count keeps what it had, or starts at 1)."""
    if counted is None or counted <= 0 or sample_chars <= 0:
        return None
    ratio = counted / estimate_tokens(sample_chars)
    if not _bounded(ratio):
        return None
    stamp = (now or datetime.now(UTC)).isoformat()
    with changing(_path(where)):
        data = _read(where)
        row = dict(data.get(account) or {})
        models = dict(row.get("models") or {})
        models[model] = {"samples": [ratio], "measured_by": "count", "measured_at": stamp, "updated_at": stamp}
        row["models"] = models
        data[account] = row
        _write(where, data)
    return ratio


def record_overhead(
    where: Any, account: str, *, reported: int | None, text_tokens: int, now: datetime | None = None
) -> int | None:
    """Keep an adapter's fixed overhead per request, as the account check measured it: the input tokens its small call
    reported, less what the call's own text counts. Returns the overhead, or None when the call reported nothing."""
    if reported is None or reported < 0:
        return None
    overhead = max(0, reported - max(0, text_tokens))
    stamp = (now or datetime.now(UTC)).isoformat()
    with changing(_path(where)):
        data = _read(where)
        row = dict(data.get(account) or {})
        row["overhead"] = {"tokens": overhead, "measured_at": stamp}
        data[account] = row
        _write(where, data)
    return overhead


def learn_from_run(
    where: Any,
    account: str,
    model: str,
    *,
    input_chars: int,
    input_tokens: int | None,
    now: datetime | None = None,
) -> float | None:
    """Move an account model's ratio by one finished run whose service reported its input tokens, after taking the
    account's fixed overhead off. A run that reported nothing, or whose ratio is out of bounds, leaves it. Returns the
    run's ratio, or None when it wasn't used."""
    if input_tokens is None or input_tokens <= 0 or input_chars <= 0:
        return None
    with changing(_path(where)):
        data = _read(where)
        row = dict(data.get(account) or {})
        overhead = row.get("overhead")
        fixed = _number(overhead.get("tokens")) if isinstance(overhead, dict) else None
        real = input_tokens - (fixed or 0)
        if real <= 0:
            return None
        ratio = real / estimate_tokens(input_chars)
        if not _bounded(ratio):
            return None
        stamp = (now or datetime.now(UTC)).isoformat()
        models = dict(row.get("models") or {})
        kept = dict(models.get(model) or {})
        kept["samples"] = [*_samples(kept), ratio][-KEPT_SAMPLES:]
        kept["updated_at"] = stamp
        models[model] = kept
        row["models"] = models
        data[account] = row
        _write(where, data)
    return ratio
