"""What each model can do, measured: the capability matrix (design 6.16, "What a model can do, measured").

Every evaluation run adds to it. A case, pair or scenario names the skills it proves (`engine/skills.py`), and each
finished run counts as one run of each of those skills for every account the run used: passes, runs, the last day, and
what the passing runs cost. The matrix is keyed by the account's model (`account/model id`, as the tier that made the
run was set up: `RunResult.models`), so
every kind of account (a service's own API, a compatible server, an aggregator, a command-line agent) is kept apart from
the others and measured the same way. Nothing is assumed from a name.

A measurement is stale when the agent program's version differs from the one measured, when it is older than
`ai.skills.stale_days`, or when the cases that measured it changed (a hash of the case ids that name the skill, kept for
each set of cases: the golden cases and the learning pairs, by the workspace they came from). A stale entry still shows
what it found, and counts as unknown for anything that routes by it. Recording over a stale entry starts it again.

The file is on this computer, in the workspace's private folder, and is never sent anywhere.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from engine.ai.checked import Folder
from engine.config import Config
from engine.skills import Skill, skills
from engine.state_file import changing, write_whole
from engine.workspace import Workspace

MATRIX_FILE = "ai-skills.json"
Reason = Literal["program", "age", "cases"]
#: How long a command-line agent's program version, read from the program itself, is reused.
VERSION_SECONDS = 600


def case_set_key(kind: str, template: str) -> str:
    """The name a set of cases is kept under: its kind (`cases`, `pairs` or `replays`) and the workspace folder it
    came from."""
    return f"{kind}:{template}"


def set_hashes(case_set: dict[str, list[str]]) -> dict[str, str]:
    """For each skill, a hash of the ids of the cases that name it."""
    by_skill: dict[str, list[str]] = {}
    for case, named in case_set.items():
        for skill in named:
            by_skill.setdefault(skill, []).append(case)
    return {skill: hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest() for skill, ids in by_skill.items()}


def _read(ws: Workspace | Folder) -> dict[str, Any]:
    try:
        data = json.loads((ws.private_dir / MATRIX_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _models(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    found = data.get("models")
    return found if isinstance(found, dict) else {}


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def stale_reason(
    entry: dict[str, Any],
    *,
    program_version: str | None,
    current_sets: dict[str, str],
    today: date,
    stale_days: int,
) -> Reason | None:
    """Why a measurement can't be trusted any more, or None. `current_sets` is the hash of the cases that now name the
    skill, for each set of cases that can be told (by `case_set_key`); a set that isn't there is not compared."""
    if entry.get("program_version") != program_version:
        return "program"
    last = _day(entry.get("last"))
    if last is not None and (today - last).days > stale_days:
        return "age"
    sets = entry.get("sets") or {}
    if any(key in sets and sets[key] != now for key, now in current_sets.items()):
        return "cases"
    return None


def record_report(
    ws: Workspace | Folder,
    report: Any,
    *,
    stale_days: int,
    today: date | None = None,
) -> None:
    """Add every finished run of a report to the matrix. A run adds one run to each skill its case names, for each
    account it used (its cost divided among them); a run that wasn't made (`not_run`) adds nothing. A report that
    doesn't say which cases it covered (`case_set`) adds nothing."""
    if not report.case_set:
        return
    today = today or datetime.now(UTC).date()
    key = case_set_key(report.kind, report.template)
    hashes = set_hashes(report.case_set)
    path = ws.private_dir / MATRIX_FILE
    with changing(path):
        data = _read(ws)
        models = _models(data)
        started: set[tuple[str, str]] = set()
        for result in report.results:
            if result.not_run or not result.models:
                continue
            share = (result.cost_usd or 0.0) / len(result.models)
            for ref in result.models:
                version = report.program_versions.get(ref.partition("/")[0])
                for skill in report.case_set.get(result.case) or []:
                    entries = models.setdefault(ref, {})
                    entry = entries.get(skill)
                    if (ref, skill) not in started:
                        started.add((ref, skill))
                        if entry is None or stale_reason(
                            entry,
                            program_version=version,
                            current_sets={key: hashes[skill]},
                            today=today,
                            stale_days=stale_days,
                        ):
                            entry = {"passes": 0, "runs": 0, "cost_passing_usd": 0.0, "sets": {}}
                    entry["program_version"] = version
                    entry["sets"] = {**entry.get("sets", {}), key: hashes[skill]}
                    entry["runs"] += 1
                    entry["last"] = today.isoformat()
                    if result.passed:
                        entry["passes"] += 1
                        entry["cost_passing_usd"] += share
                    entries[skill] = entry
        write_whole(path, json.dumps({"version": 1, "models": models}, indent=2, sort_keys=True) + "\n")


@dataclass(frozen=True)
class Standing:
    """What the matrix holds for one model and one skill."""

    skill: Skill
    runs: int
    passes: int
    last: date | None
    cost_per_pass_usd: float | None
    stale: Reason | None
    below_min: bool

    @property
    def measured(self) -> bool:
        return self.runs > 0

    @property
    def pass_rate(self) -> float | None:
        return self.passes / self.runs if self.runs else None

    def age_days(self, today: date) -> int | None:
        return (today - self.last).days if self.last else None


def standing(
    ws: Workspace | Folder,
    cfg: Config,
    ref: str,
    *,
    program_version: str | None,
    current_sets: dict[str, dict[str, str]],
    today: date | None = None,
) -> list[Standing]:
    """Every skill for one model ("account/model id"), measured or not, in the order of the skills list. `current_sets`
    maps a set of cases (`case_set_key`) to the hash of its cases for each skill."""
    today = today or datetime.now(UTC).date()
    held = _models(_read(ws)).get(ref)
    held = held if isinstance(held, dict) else {}
    found = []
    for skill in skills():
        entry = held.get(skill.id)
        if not isinstance(entry, dict) or not entry.get("runs"):
            found.append(Standing(skill, 0, 0, None, None, None, False))
            continue
        runs, passes = int(entry["runs"]), int(entry.get("passes", 0))
        reason = stale_reason(
            entry,
            program_version=program_version,
            current_sets={key: by_skill[skill.id] for key, by_skill in current_sets.items() if skill.id in by_skill},
            today=today,
            stale_days=cfg.ai.skills.stale_days,
        )
        found.append(
            Standing(
                skill,
                runs,
                passes,
                _day(entry.get("last")),
                float(entry.get("cost_passing_usd", 0.0)) / passes if passes else None,
                reason,
                passes / runs < cfg.ai.skills.min_score,
            )
        )
    return found


_VERSIONS: dict[str, tuple[float, str | None]] = {}


def current_program_version(
    cfg: Config, name: str, factory: Callable[[str, Any, str | None], Any], *, now: Callable[[], float] = time.monotonic
) -> str | None:
    """The version of the program a command-line agent account runs now (None for any other account, or when the
    program can't say). It is read from the program itself and reused for a few minutes, so a screen asking often
    doesn't start the program each time."""
    provider = cfg.ai.providers.get(name)
    if provider is None or provider.adapter != "cli-agent":
        return None
    key = hashlib.sha256(json.dumps(provider.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    held = _VERSIONS.get(key)
    if held is not None and now() - held[0] < VERSION_SECONDS:
        return held[1]
    version = factory(provider.adapter, provider, None).program_version()
    _VERSIONS[key] = (now(), version)
    return version


_LOADED: dict[tuple[str, str], tuple[tuple[Any, ...], dict[str, list[str]]]] = {}


def _skills_of(template: Path, kind: str) -> dict[str, list[str]] | None:
    """Each case id of a workspace's golden cases (`cases`) or its pairs and scenarios (`pairs`) with the skills it
    names; None when they don't load. Kept until one of the files changes, since reading them all takes a moment."""
    from engine.evaluate import load_cases
    from engine.pairs import load_pairs, load_scenarios
    from engine.replays import load_replays

    folders = {"cases": ("evals",), "pairs": ("pairs", "scenarios"), "replays": ("replays",)}[kind]
    signature = tuple(
        (str(p), p.stat().st_mtime_ns, p.stat().st_size) for f in folders for p in sorted((template / f).glob("*.yaml"))
    )
    held = _LOADED.get((str(template), kind))
    if held is not None and held[0] == signature:
        return held[1]
    try:
        items = {
            "cases": lambda: load_cases(template),
            "pairs": lambda: [*load_pairs(template), *load_scenarios(template)],
            "replays": lambda: load_replays(template),
        }[kind]()
    except (ValueError, OSError):
        return None
    found = {c["id"]: list(c.get("skills") or []) for c in items}
    _LOADED[(str(template), kind)] = (signature, found)
    return found


def case_sets(template: Path, packs_of: Path | None = None) -> dict[str, dict[str, str]]:
    """The hashes of the cases that name each skill, for a workspace's golden cases (with the cases of the plugins
    enabled in `packs_of`), for its learning pairs and scenarios and for its replays, as `case_set_key` names them. A
    set that doesn't load says nothing."""
    from engine.evaluate import load_pack_cases

    found: dict[str, dict[str, str]] = {}
    golden = _skills_of(template, "cases")
    if golden is not None:
        try:
            packs = {c["id"]: list(c.get("skills") or []) for c in load_pack_cases(packs_of or template)}
        except (ValueError, OSError):
            packs = None
        if packs is not None:
            found[case_set_key("cases", template.name)] = set_hashes({**golden, **packs})
    paired = _skills_of(template, "pairs")
    if paired is not None:
        found[case_set_key("pairs", template.name)] = set_hashes(paired)
    replayed = _skills_of(template, "replays")
    if replayed:
        found[case_set_key("replays", template.name)] = set_hashes(replayed)
    return found


#: The kind of work the core's own cases, learning pairs, scenarios and replays run: reading what is handed in.
CORE_KIND = "notes"


def skills_by_kind(template: Path, packs_of: Path | None = None) -> dict[str, list[str]]:
    """The skills that cases prove for each kind of work, in the order of the skills list. The core's golden cases,
    learning pairs, scenarios and replays all run the note-reading kind (`CORE_KIND`); a plugin's case runs the kind it
    names (`task`), or that same one when it names none. A kind no case runs has no entry: nothing measures it."""
    from engine.evaluate import load_pack_cases

    named: dict[str, set[str]] = {}
    for kind in ("cases", "pairs", "replays"):
        for ids in (_skills_of(template, kind) or {}).values():
            named.setdefault(CORE_KIND, set()).update(ids)
    try:
        packs = load_pack_cases(packs_of or template)
    except (ValueError, OSError):
        packs = []
    for case in packs:
        named.setdefault(str(case.get("task") or CORE_KIND), set()).update(case.get("skills") or [])
    order = [s.id for s in skills()]
    return {kind: [i for i in order if i in ids] for kind, ids in named.items() if ids}
