"""Learning pairs and the day-30 scenario (design 6.22 "Proving it", 6.16): fictional fixtures that check the assistant
doesn't repeat a corrected mistake, and doesn't over-learn either.

A pair is a file in a workspace's `pairs/` folder. It runs in a fresh copy of the workspace, in two halves.

    id, title
    negative: true            # the later output must not change, however much the person kept
    pending: <why>            # the gap in the code that stops it passing; it is run only when named, and a test says
                              # it still fails, so the flag goes the day the gap is closed
    first:                    # (a) the mistake, the correction, what is learned
      received: '2026-10-08'  # when the input arrived, and the same keys a golden case has for its input:
      pasted / note / project / typed_on / watched, and `attached` (files read as the app reads attachments)
      given / given_file      # starting records (the evals folder's shared files are named by `given_file`)
      label: <name>           # lets a later step name this input's change
      wrong: {summary, ops}   # the mistake: a fixed answer, applied without any model (`fixed` is the same, for an
                              # input whose fixed answer is right). Leave it out when the proposal comes from the run
                              # itself (a term, who answers); that run is then the account's, and may be scored with
                              # expect / forbid / allow / exact / hostile / injected as a golden case is.
      before: [{received, <input keys>, answer: {...}, label}]  # inputs before it, with fixed answers
      then: [{received, <input keys>, answer: {...}, label}]    # more inputs after it, with fixed answers
      correction:             # what the person does, through the same code the screens use
        kind: sent_back | undone | answered | moved | dropped | picked_owner | not_a_project | part_of |
              new_person | set_aside
        note: ...             # the person's words; of: <label> (default: the first input's change)
        # moved/picked_owner/answered/dropped name a record: id or @action, @question, @event, @fact, @held_question
        # (the first one the input's change made); person / into / form / as the kind needs
      expect_proposal: none | [{op, text_has, person, team, topic_has, negative, term, audience, origin, trust,
                                projects, scope, optional}]
      keep: true | false | discard   # what the person does with each proposal: Keep, nothing, Discard
      allow_active: true      # only when the person's own act makes something active at once (comment why)
      expect_learning: false  # no learning request may be queued
    later:                    # (b) a later, similar input, scored exactly like a golden case
      received, <input keys>, expect, forbid, allow, exact, hostile, injected
      packet_has / packet_lacks: [words]   # words the packet the account reads holds, or must not hold
      expect_proposal: none | [...]        # what the later input itself may propose
      then: [{received, <input keys>}]     # more inputs of the same batch; every op counts together
    ideal:                    # the stand-in answers that make the stub run pass: no cost, and the plumbing is checked
      first: {...}            # the first run's answer when `wrong` is left out
      learn: {...}            # the learning run's answer
      later: {...} | [{...}, ...]   # the later input's answer, then one for each of its `then`

`cockpit evaluate --pairs` runs each pair N times on the person's account. The first input's mistake and the setup
inputs are fixed answers; the learning run, the later input and a proposal from an input are the account's. The report
gives the pass rate per pair, the account, the agent's program version and what the later run was given from what was
learned. With the stub, each stage answers from `ideal`, so every pair runs in the test suite.

A scenario (a file in `scenarios/`) is one input against the workspace as it is (day 1) and against it after a month
of history (day 30): `history` is a list of steps (`input` with a fixed answer, `correct` with its `learn` answer and
`keep`, or `keep_all` alone, which keeps or discards every proposal waiting), `day1` and `day30` are scored like a
golden case, and `differences` lists what the history must change, each as an op that appears on one day and not on the
other.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from engine import knowledge, learn
from engine.ai.adapters import make_adapter
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import apply_as_person, pick_owner
from engine.config import Config
from engine.corrections import answered_assistant
from engine.dispatcher import process, send_back, signal, undo_changeset
from engine.evaluate import (
    AdapterFactory,
    Report,
    RunResult,
    _create_starting_records,
    _describe,
    _forbidden,
    _hand_in_case,
    _hostile_findings,
    _matches,
    _matching,
    _read_program_versions,
    _summarize,
    _unexpected,
    received_of,
    starting_records,
)
from engine.extract import EXTENSIONS, read_file
from engine.extract import fixtures as file_fixtures
from engine.next_steps import NewPersonForm, add_new_person, file_under, not_a_project
from engine.records import REGISTRY
from engine.storage import Store, StoreError, WriteContext
from engine.workspace import Workspace, init_workspace
from engine.yaml_load import load_yaml

#: The kinds an entry the assistant learned can be: the four kinds of knowledge and standing rules.
ENTRY_KINDS: tuple[str, ...] = (*knowledge.KINDS, "rule")
#: The kind of entry each op that proposes one makes.
OP_ENTRY = {**knowledge.OP_KIND, "rule.add": "rule"}
CORRECTIONS = (
    "sent_back",
    "undone",
    "answered",
    "moved",
    "dropped",
    "picked_owner",
    "not_a_project",
    "part_of",
    "new_person",
    "set_aside",
)
KEEPS = (True, False, "discard")
INPUT_KEYS = ("received", "pasted", "note", "project", "typed_on", "watched", "attached", "label")
_PERSON = WriteContext(actor="pm", trust="trusted", op="pair.person")
_FILE_KINDS = {
    "presentation": (file_fixtures.presentation, "x.pptx"),
    "document": (file_fixtures.document, "x.docx"),
    "pdf": (file_fixtures.pdf, "x.pdf"),
}


# ---- loading ---------------------------------------------------------------------------------------------------------


def _load_folder(template: Path, name: str) -> list[dict[str, Any]]:
    found = []
    for path in sorted((template / name).glob("*.yaml")):
        loaded = load_yaml(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"{path.name}: should hold one mapping")
        if loaded.get("id") != path.stem:
            raise ValueError(f"{path.name}: its id is {loaded.get('id')!r}; name the file after the id")
        found.append(loaded)
    return found


def load_pairs(template: Path) -> list[dict[str, Any]]:
    """The pairs in a workspace's `pairs/` folder, each checked."""
    pairs = _load_folder(template, "pairs")
    for pair in pairs:
        _check_pair(template, pair)
    return pairs


def load_scenarios(template: Path) -> list[dict[str, Any]]:
    """The scenarios in a workspace's `scenarios/` folder, each checked."""
    scenarios = _load_folder(template, "scenarios")
    for scenario in scenarios:
        _check_scenario(template, scenario)
    return scenarios


def _need(where: str, spec: Any, key: str, kind: type | tuple[type, ...] = dict) -> Any:
    value = spec.get(key) if isinstance(spec, dict) else None
    if not isinstance(value, kind):
        raise ValueError(f"{where}: {key} is missing or isn't the right shape")
    return value


def _check_input(where: str, spec: Any, *, answer: bool = False) -> None:
    if not isinstance(spec, dict):
        raise ValueError(f"{where}: an input is a mapping")
    received_of({"id": where, **spec})
    if not any(spec.get(k) for k in ("pasted", "note", "watched")):
        raise ValueError(f"{where}: an input needs pasted text, a note or a watched item")
    if answer and not isinstance(spec.get("answer"), dict):
        raise ValueError(f"{where}: a fixed input carries its `answer`")
    for attached in spec.get("attached") or []:
        if attached.get("kind") not in _FILE_KINDS:
            raise ValueError(f"{where}: an attached file is one of {', '.join(_FILE_KINDS)}")


def _check_proposals(where: str, spec: Any) -> None:
    if spec in (None, "none"):
        return
    if not isinstance(spec, list) or not all(isinstance(s, dict) and s.get("op") in OP_ENTRY for s in spec):
        raise ValueError(f"{where}: expect_proposal is `none` or a list of entries, each naming its op")


def _check_scoring(where: str, spec: dict[str, Any]) -> None:
    if not isinstance(spec.get("exact", True), bool):
        raise ValueError(f"{where}: exact is true or false")
    if not all(isinstance(op, str) for op in spec.get("allow", [])):
        raise ValueError(f"{where}: allow is a list of op names")
    if spec.get("injected") and not spec.get("hostile"):
        raise ValueError(f"{where}: injected names people only a hostile case checks; add hostile: true")
    if not spec.get("expect") and not spec.get("forbid"):
        raise ValueError(f"{where}: say what is expected or forbidden")


def _check_correction(where: str, spec: Any) -> None:
    if not isinstance(spec, dict) or spec.get("kind") not in CORRECTIONS:
        raise ValueError(f"{where}: a correction is one of {', '.join(CORRECTIONS)}")


def _fixed_answer(first: Mapping[str, Any]) -> Any:
    """The first input's fixed answer (`wrong`, or `fixed`), or None when the account reads it."""
    return first.get("wrong", first.get("fixed"))


def _check_pair(template: Path, pair: dict[str, Any]) -> None:
    where = f"pair {pair['id']}"
    first, later, ideal = _need(where, pair, "first"), _need(where, pair, "later"), _need(where, pair, "ideal")
    _check_input(f"{where} first", first)
    starting_records(template, {"id": pair["id"], **first})
    if not isinstance(pair.get("negative", False), bool):
        raise ValueError(f"{where}: negative is true or false")
    if "pending" in pair and not (isinstance(pair["pending"], str) and pair["pending"].strip()):
        raise ValueError(f"{where}: pending says what is missing in the code")
    fixed = _fixed_answer(first)
    if ("wrong" in first or "fixed" in first) and not isinstance(fixed, dict):
        raise ValueError(f"{where}: wrong is an answer: a summary and its ops")
    if fixed is None:
        _need(f"{where} ideal", ideal, "first")
    if first.get("expect") or first.get("forbid"):
        _check_scoring(f"{where} first", first)
    for key in ("before", "then"):
        for n, step in enumerate(first.get(key) or []):
            _check_input(f"{where} first.{key}[{n}]", step, answer=True)
    if first.get("correction") is not None:
        _check_correction(f"{where} first", first["correction"])
        if first.get("expect_learning", True):
            _need(f"{where} ideal", ideal, "learn")
    if first.get("keep", False) not in KEEPS:
        raise ValueError(f"{where}: keep is true, false or discard")
    _check_proposals(f"{where} first", first.get("expect_proposal"))
    _check_input(f"{where} later", later)
    _check_scoring(f"{where} later", later)
    _check_proposals(f"{where} later", later.get("expect_proposal"))
    inputs = 1 + len(later.get("then") or [])
    for n, step in enumerate(later.get("then") or []):
        _check_input(f"{where} later.then[{n}]", step)
    answers = ideal.get("later")
    answers = answers if isinstance(answers, list) else [answers]
    if len(answers) != inputs or not all(isinstance(a, dict) for a in answers):
        raise ValueError(f"{where}: ideal.later needs one answer for each of the {inputs} later inputs")
    for key in ("packet_has", "packet_lacks"):
        if not all(isinstance(w, str) for w in later.get(key, [])):
            raise ValueError(f"{where}: {key} is a list of words")


def _check_scenario(template: Path, scenario: dict[str, Any]) -> None:
    where = f"scenario {scenario['id']}"
    _check_input(f"{where} input", _need(where, scenario, "input"))
    starting_records(template, {"id": scenario["id"], **scenario})
    ideal = _need(where, scenario, "ideal")
    for day in ("day1", "day30"):
        _check_scoring(f"{where} {day}", _need(where, scenario, day))
        _need(f"{where} ideal", ideal, day)
    for n, step in enumerate(_need(where, scenario, "history", list)):
        if sum(key in step for key in ("input", "correct", "keep_all")) != 1:
            raise ValueError(f"{where} history[{n}]: a step is an `input`, a `correct` or a `keep_all`")
        if "keep_all" in step:
            if step["keep_all"] not in (True, "discard"):
                raise ValueError(f"{where} history[{n}]: keep_all is true or discard")
        elif "input" in step:
            _check_input(f"{where} history[{n}]", step["input"], answer=True)
        else:
            _check_correction(f"{where} history[{n}]", step["correct"])
            _need(f"{where} history[{n}]", step, "learn")
    for n, diff in enumerate(_need(where, scenario, "differences", list)):
        if diff.get("day") not in (1, 30) or not isinstance(diff.get("expect"), dict) or not diff.get("why"):
            raise ValueError(f"{where} differences[{n}]: say the day (1 or 30), the op it expects, and why")


# ---- one run ---------------------------------------------------------------------------------------------------------


class _Stop(Exception):
    """A stage can't go on; its words are the failure."""


@dataclass
class _Done:
    request: str
    changeset: str | None


def _stub_flags() -> dict[str, Any]:
    return {
        "ai.providers.stub": {
            "adapter": "stub",
            "models": {"default": "scripted"},
            "allowed_data": ["open", "internal", "restricted"],
        },
        "ai.tiers.routine.use": "stub/default",
        "ai.tiers.routine.fallback": [],
        "ai.tiers.deep.use": "stub/default",
        "ai.tiers.deep.fallback": [],
    }


class _Play:
    """One workspace and what happens in it: inputs handed in and run, corrections made, proposals kept."""

    def __init__(
        self,
        template: Path,
        tmp: Path,
        name: str,
        *,
        account: str | None,
        stub: bool,
        env: Mapping[str, str],
        ai_config: Path | None,
        on_wait: Callable[[float], None] | None,
    ) -> None:
        self.name, self.stub, self.env, self.on_wait = name, stub, env, on_wait
        self.ws: Workspace = init_workspace(tmp / "ws", template=template, git=False)
        if ai_config is not None:
            shutil.copyfile(ai_config, self.ws.config_dir / "ai.yaml")
        flags: dict[str, Any] = {"ai.budgets.first_go": False}  # a run is unattended, so it never waits for a first go
        self.fixed: Config = self.ws.config(env={}, flags=flags | _stub_flags())
        if stub:
            self.live = self.fixed
        else:
            chosen: dict[str, Any] = {}
            for tier in ("routine", "deep") if account else ():
                chosen |= {f"ai.tiers.{tier}.use": account, f"ai.tiers.{tier}.fallback": []}
            self.live = self.ws.config(env={}, flags=flags | chosen)
        self.store = Store(self.ws.db_path)
        self.now: datetime | None = None
        self.live_requests: set[str] = set()
        self.labels: dict[str, str] = {}
        self.first_changeset: str | None = None
        self.last_changeset: str | None = None

    def close(self) -> None:
        self.store.close()
        set_responder(None)

    # -- time and ids

    def at(self, spec: Mapping[str, Any]) -> datetime:
        """The moment an input arrives: its own day, or later than anything that already happened."""
        when = received_of({"id": self.name, **spec})
        self.now = when if self.now is None or when > self.now else self.now
        return self.now

    def tick(self) -> datetime:
        """An hour after the last thing that happened, for what the person does next."""
        assert self.now is not None
        self.now = self.now + timedelta(hours=1)
        return self.now

    def made(self, changeset: str, kind: str) -> str:
        cs = self.store.read().get("changeset", changeset)
        for outcome in cs.data["ops"] if cs is not None else []:
            for record in outcome.get("records") or []:
                if record["kind"] == kind:
                    return record["id"]
        raise _Stop(f"the input's change made no {kind} to refer to")

    def held_index(self, changeset: str, op: str) -> int:
        cs = self.store.read().get("changeset", changeset)
        for outcome in cs.data["ops"] if cs is not None else []:
            if outcome["status"] == "held" and outcome["op"]["op"] == op:
                return outcome["index"]
        raise _Stop(f"the input's change holds no {op}")

    def ref(self, value: Any, changeset: str | None) -> Any:
        """A record the correction names: its id, or `@kind` for the first record of that kind the change made, or
        `@held_question` for the question its first held op waits on."""
        if not (isinstance(value, str) and value.startswith("@")):
            return value
        if changeset is None:
            raise _Stop("there is no change to take a record from")
        word = value[1:]
        if word == "held_question":
            cs = self.store.read().get("changeset", changeset)
            found = next((o["question"] for o in cs.data["ops"] if o["status"] == "held" and o.get("question")), None)
            if found is None:
                raise _Stop("the input's change holds no question")
            return found
        return self.made(changeset, word)

    def changeset_of(self, label: str | None) -> str:
        found = self.labels.get(label) if label else self.first_changeset
        if found is None:
            raise _Stop("there is no earlier change to correct")
        return found

    # -- inputs

    def hand_in(self, spec: Mapping[str, Any], changeset: str | None) -> str:
        case: dict[str, Any] = {"id": self.name, **{k: v for k, v in spec.items() if k in INPUT_KEYS}}
        if case.get("typed_on"):
            case["typed_on"] = {k: self.ref(v, changeset) for k, v in case["typed_on"].items()}
        if spec.get("attached"):
            case["pasted"] = _with_files(case.get("pasted", ""), spec["attached"])
        return _hand_in_case(self.ws, self.store, self.fixed, case, self.at(spec))

    def run_input(self, spec: Mapping[str, Any], answer: Mapping[str, Any] | None, *, live: bool) -> _Done:
        """Hand an input in and let the assistant read it: with the account when `live`, else with the fixed answer."""
        request = self.hand_in(spec, self.last_changeset)
        return _Done(request, self.process(request, answer, live=live))

    def process(self, request: str, answer: Mapping[str, Any] | None, *, live: bool) -> str | None:
        cfg = self.live if live else self.fixed
        if live:
            self.live_requests.add(request)
        if answer is not None and (self.stub or not live):
            set_responder(lambda task, body=dict(answer): json.dumps(body))
        elif self.stub or not live:
            raise _Stop("no stand-in answer for this stage")
        else:
            set_responder(None)
        try:
            router = Router(cfg, self.store, env=self.env, on_wait=self.on_wait)
            done = process(self.ws, self.store, cfg, router, request, now=self.now)
        finally:
            set_responder(None)
        if done is not None:
            self.last_changeset = done
        return done

    def waiting_reason(self, request: str) -> str:
        found = self.store.read().get("request", request)
        return (found.data.get("waiting") if found is not None else None) or "it did not finish"

    def refused(self, request: str) -> bool:
        runs = [r for r in self.store.read().list("run") if r.data.get("request") == request]
        return bool(runs) and runs[-1].data.get("error_kind") in ("rate_limited", "quota")

    # -- corrections, learning, keeping

    def correct(self, spec: Mapping[str, Any]) -> list[str]:
        """Make a correction as the person would, through the code the screens use. Returns the signals it recorded."""
        before = {s.id for s in self.store.read().list("signal")}
        cs = self.changeset_of(spec.get("of"))
        cfg, kind, note = self.fixed, spec["kind"], spec.get("note") or ""
        when = self.tick()
        ref = lambda key: self.ref(spec.get(key), cs)  # noqa: E731
        try:
            if kind == "sent_back":
                send_back(self.store, cs, note, now=when, undo_first=spec.get("undo", True))
            elif kind == "undone":
                undo_changeset(self.store, cs)
            elif kind == "answered":
                if answered_assistant(self.store, cfg, ref("id"), note) is None:
                    raise _Stop("the answer was a bare confirmation, so nothing is recorded")
            elif kind == "moved":
                apply_as_person(
                    self.store,
                    cfg,
                    [{"op": "question.move", "id": ref("id"), "to": ref("person")}],
                    "Asked someone else",
                )
            elif kind == "dropped":
                op = "question.drop" if str(ref("id")).startswith("Q-") else "action.drop"
                apply_as_person(self.store, cfg, [{"op": op, "id": ref("id"), "reason": note}], "Dropped")
            elif kind == "picked_owner":
                pick_owner(self.store, ref("id"), ref("person"))
            elif kind == "not_a_project":
                not_a_project(self.store, cfg, cs, self.held_index(cs, "project.add"), now=when)
            elif kind == "part_of":
                file_under(self.store, cfg, cs, self.held_index(cs, "project.add"), ref("into"), now=when)
            elif kind == "new_person":
                form = NewPersonForm(**spec["form"])
                add_new_person(self.store, cfg, self.ws, ref("id"), form, now=when)
            elif kind == "set_aside":
                request = self.store.read().get("changeset", cs).data["request"]
                self._set_aside(request)
                signal(self.store, "set_aside", [request], note="Set aside by hand", now=when)
        except StoreError as err:
            raise _Stop(f"the correction {kind} was refused: {err}") from None
        return [s.id for s in self.store.read().list("signal") if s.id not in before]

    def _set_aside(self, request: str) -> None:
        with self.store.transaction() as tx:
            found = tx.get("request", request)
            tx.update("request", request, {"set_aside": {"section": "personal"}}, _PERSON, read_version=found.version)

    def learn_from(self, signals: list[str], answer: Mapping[str, Any] | None) -> list[str]:
        """Let the assistant learn from each correction, as the app queues it. Returns the learning requests run."""
        ran = []
        for signal_id in signals:
            request = learn.learn_request(self.store.read(), signal_id)
            if request is None or request.data["state"] == "done":
                continue
            self.process(request.id, answer, live=True)
            ran.append(request.id)
        return ran

    def entries(self) -> dict[str, Any]:
        view = self.store.read()
        return {s.id: s for kind in ENTRY_KINDS for s in view.list(kind)}

    def decide(self, ids: list[str], how: Any) -> None:
        """Keep or discard proposals as the person does: the same edit and signal as the screens make."""
        person = self.fixed.workspace.user.person
        if person is None or how is False:
            return
        for entry_id in ids:
            kind = knowledge.kind_of(entry_id) or "rule"
            found = self.store.read().get(kind, entry_id)
            if found is None or found.data["status"] != "proposed":
                continue
            if how is True:
                fields, summary, signal_kind = (
                    knowledge.keep_fields(found, person, self.store.clock()),
                    "Kept what was learned",
                    "kept",
                )
            else:
                fields = knowledge.discard_fields(found, None)
                summary, signal_kind = "Discarded what was learned", "discarded"
            edit = {"op": "record.edit", "record": {"kind": kind, "id": entry_id}, "fields": fields}
            apply_as_person(self.store, self.fixed, [{**edit, "read_version": found.version}], summary)
            signal(self.store, signal_kind, [entry_id], now=self.tick())

    def packet_text(self, request: str) -> str:
        """What the account would read for a queued request: its stable part and its request."""
        from engine.packet import build

        built = build(self.ws, self.store, self.live, request, self.now.date())
        return built.task.stable + "\n" + built.task.request

    def given(self, request: str) -> list[str]:
        """What the runs of a request were given from what was learned, one line per entry."""
        view = self.store.read()
        ids: list[str] = []
        for run in view.list("run"):
            if run.data.get("request") == request:
                ids += list((run.data.get("knowledge") or {}).get("given") or [])
        lines = []
        for entry_id in dict.fromkeys(ids):
            kind = learn.kind_of_id(REGISTRY, entry_id)
            found = view.get(kind, entry_id) if kind else None
            data = found.data if found is not None else {}
            text = data.get("text") or " ".join(str(data.get(k, "")) for k in ("term", "meaning")).strip()
            lines.append(f"{entry_id}: {text}".strip())
        return lines


def _with_files(text: str, attached: list[dict[str, Any]]) -> str:
    """The input's text with each attached file read as text, in the same blocks a watched item's files are in."""
    blocks = [text.strip()]
    for spec in attached:
        build, default_name = _FILE_KINDS[spec["kind"]]
        name = spec.get("name") or default_name
        kwargs = {k: v for k, v in spec.items() if k in ("title", "body", "note")}
        media_type = EXTENSIONS[Path(name).suffix.lower()]
        read = read_file(build(**kwargs), name, media_type, max_chars=20000, max_bytes=10**7)
        blocks.append(f"Attached file: {name}\n{read.text}\nEnd of attached file: {name}")
    return "\n\n".join(b for b in blocks if b)


# ---- checking what came out ------------------------------------------------------------------------------------------


def _has(text: str, words: list[str]) -> bool:
    return all(w.lower() in text.lower() for w in words)


def _entry_matches(spec: Mapping[str, Any], stored: Any) -> bool:
    data = stored.data
    if OP_ENTRY.get(spec["op"]) != stored.kind:
        return False
    if data["status"] != spec.get("status", "proposed"):
        return False
    wording = " ".join(str(data.get(k, "")) for k in ("text", "term", "meaning", "topic", "observation"))
    if not _has(wording, spec.get("text_has", [])) or not _has(str(data.get("topic", "")), spec.get("topic_has", [])):
        return False
    for key in ("person", "team", "term", "audience", "origin", "trust"):
        if key in spec and data.get(key) != spec[key]:
            return False
    if "negative" in spec and bool(data.get("negative")) != bool(spec["negative"]):
        return False
    target = data.get("applies_to") or {}
    if "scope" in spec and target.get("scope", "workspace") != spec["scope"]:
        return False
    return "projects" not in spec or sorted(target.get("projects") or []) == sorted(spec["projects"])


def _describe_entry(stored: Any) -> str:
    data = stored.data
    return f"{stored.kind}({data.get('text', '')[:60]!r}, {data['status']}, {data.get('origin')}, {data.get('trust')})"


def _proposal_findings(label: str, spec: Any, new: list[Any]) -> list[str]:
    """What is wrong with the entries a stage made, given what it was expected to propose. `none` means no entry at
    all; a spec with `optional` may also come to nothing, but anything made must match one."""
    if spec in (None,):
        return []
    if spec == "none":
        return [f"{label}: nothing should be learned, but {_describe_entry(s)} was made" for s in new]
    specs = list(spec)
    found: list[str] = []
    used: set[str] = set()
    for item in specs:
        hit = next((s for s in new if s.id not in used and _entry_matches(item, s)), None)
        if hit is not None:
            used.add(hit.id)
        elif not item.get("optional"):
            found.append(f"{label}: no proposal like {_describe(item)}")
    found += [f"{label}: unexpected {_describe_entry(s)}" for s in new if s.id not in used]
    return found


def _score(
    spec: Mapping[str, Any], outcomes: list[dict[str, Any]], store: Store, request: str, people_before: int
) -> tuple[list[str], list[str], list[str]]:
    """Missing, forbidden and extra ops of a stage, as a golden case scores them."""
    case = {"id": "pair", **spec}
    missing = [_describe(e) for e in spec.get("expect", []) if not _matches(e, outcomes, store, request)]
    forbidden = [_describe(f) for f in spec.get("forbid", []) if _forbidden(f, outcomes, store, people_before)]
    if spec.get("hostile"):
        forbidden += _hostile_findings(case, outcomes, store)
    extra = _unexpected(case, outcomes, store, request) if spec.get("exact", True) else []
    return missing, forbidden, extra


def _outcomes(store: Store, changesets: list[str | None]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for cs in changesets:
        if cs is not None:
            found += store.read().get("changeset", cs).data["ops"]
    return found


def _usage(play: _Play) -> tuple[list[str], float, float]:
    """The accounts, the cost and the seconds of the runs the person's own account made."""
    runs = [r.data for r in play.store.read().list("run") if r.data.get("request") in play.live_requests]
    return (
        sorted({f"{r['provider']}/{r['model']}" for r in runs}),
        sum(r.get("cost_usd") or 0.0 for r in runs),
        sum(r.get("seconds") or 0.0 for r in runs),
    )


def _versions(play: _Play, versions: dict[str, str | None] | None, factory: AdapterFactory) -> None:
    if versions is not None and not play.stub:
        providers = {
            r.data["provider"] for r in play.store.read().list("run") if r.data.get("request") in play.live_requests
        }
        _read_program_versions(play.live, providers, versions, factory)


# ---- a pair ----------------------------------------------------------------------------------------------------------


def _run_pair(
    template: Path, pair: dict[str, Any], n: int, *, versions: dict[str, str | None] | None, **how: Any
) -> RunResult:
    factory: AdapterFactory = how.pop("adapter_factory")
    with tempfile.TemporaryDirectory() as tmp:
        play = _Play(template, Path(tmp), pair["id"], **how)
        try:
            return _play_pair(play, template, pair, n, versions, factory)
        finally:
            play.close()


def _play_pair(
    play: _Play, template: Path, pair: dict[str, Any], n: int, versions: dict[str, str | None] | None, factory: Any
) -> RunResult:
    first, later, ideal = pair["first"], pair["later"], pair["ideal"]
    negative = bool(pair.get("negative"))
    problems: list[str] = []
    forbidden: list[str] = []
    extra: list[str] = []
    request = ""
    given: list[str] = []

    def result(passed: bool, **more: Any) -> RunResult:
        accounts, cost, seconds = _usage(play)
        _versions(play, versions, factory)
        return RunResult(
            pair["id"],
            n,
            passed,
            problems,
            forbidden,
            extra,
            cost_usd=cost,
            seconds=seconds,
            accounts=accounts,
            given=given,
            negative=negative,
            **more,
        )

    def stopped(why: str, request_id: str | None = None, **more: Any) -> RunResult:
        if request_id is not None and play.refused(request_id):
            return result(False, error=why, not_run=True, **more)
        return result(False, error=why, **more)

    try:
        records = starting_records(template, {"id": pair["id"], **first})
        if records:
            _create_starting_records(play.store, pair["id"], records)
        before = set(play.entries())

        # (a) the mistake
        for step in first.get("before") or []:
            done = play.run_input(step, step["answer"], live=False)
            if done.changeset is None:
                return stopped(f"a setup input didn't finish: {play.waiting_reason(done.request)}")
            if step.get("label"):
                play.labels[step["label"]] = done.changeset
        wrong = _fixed_answer(first)
        people_first = len(play.store.read().list("person"))
        start = play.run_input(first, wrong if wrong is not None else ideal["first"], live=wrong is None)
        if start.changeset is None:
            return stopped(f"the first input didn't finish: {play.waiting_reason(start.request)}", start.request)
        play.first_changeset = start.changeset
        if first.get("label"):
            play.labels[first["label"]] = start.changeset
        if first.get("expect") or first.get("forbid"):
            miss, forbidden, extra = _score(
                first, _outcomes(play.store, [start.changeset]), play.store, start.request, people_first
            )
            problems += [f"first: missing {m}" for m in miss]
        for step in first.get("then") or []:
            done = play.run_input(step, step["answer"], live=False)
            if done.changeset is None:
                return stopped(f"a setup input didn't finish: {play.waiting_reason(done.request)}")
            if step.get("label"):
                play.labels[step["label"]] = done.changeset
        if first.get("correction") is not None:
            signals = play.correct(first["correction"])
            queued = play.learn_from(signals, ideal.get("learn"))
            if first.get("expect_learning", True) is False and queued:
                problems.append("first: learning was queued for a correction that teaches nothing")
            if first.get("expect_learning", True) and not queued and first.get("expect_proposal") not in (None, "none"):
                problems.append("first: the correction queued no learning")
        learned = [s for i, s in play.entries().items() if i not in before and s.data["status"] != "discarded"]
        problems += _proposal_findings("first", first.get("expect_proposal"), learned)
        active = [s for s in learned if s.data["status"] == "active"]
        if active and not first.get("allow_active"):
            problems += [f"first: {_describe_entry(s)} became active without the person's Keep" for s in active]
        play.decide([s.id for s in learned], first.get("keep", False))

        # (b) the later input
        steps = [later, *(later.get("then") or [])]
        answers = ideal["later"] if isinstance(ideal["later"], list) else [ideal["later"]]
        known = set(play.entries())
        people_before = len(play.store.read().list("person"))
        changesets: list[str | None] = []
        request = ""
        for index, (step, answer) in enumerate(zip(steps, answers, strict=True)):
            handed = play.hand_in(step, play.last_changeset)
            if index == 0:
                request = handed
                text = play.packet_text(handed)
                problems += [
                    f"later: the packet doesn't hold {w!r}" for w in later.get("packet_has", []) if w not in text
                ]
                problems += [f"later: the packet holds {w!r}" for w in later.get("packet_lacks", []) if w in text]
            done = play.process(handed, answer, live=True)
            if done is None:
                return stopped(f"the later input didn't finish: {play.waiting_reason(handed)}", handed)
            changesets.append(done)
        given = play.given(request)
        outcomes = _outcomes(play.store, changesets)
        miss, forbidden, extra = _score(later, outcomes, play.store, request, people_before)
        problems += [f"later: missing {m}" for m in miss]
        new = [s for i, s in play.entries().items() if i not in known and s.data["status"] != "discarded"]
        problems += _proposal_findings("later", later.get("expect_proposal"), new)
    except _Stop as err:
        return stopped(str(err), request or None)
    passed = not problems and not forbidden and not extra
    return result(
        passed,
        got=[] if passed else [_summarize(o) for o in _outcomes(play.store, changesets)],
        refused=sum(o["status"] == "refused" for o in outcomes),
        held=sum(o["status"] == "held" for o in outcomes),
    )


# ---- a scenario ------------------------------------------------------------------------------------------------------


def _history(play: _Play, scenario: dict[str, Any]) -> None:
    """A month of fictional history, played with fixed answers: inputs, and corrections that were kept."""
    for step in scenario["history"]:
        if "input" in step:
            done = play.run_input(step["input"], step["input"]["answer"], live=False)
            if done.changeset is None:
                raise _Stop(f"a history input didn't finish: {play.waiting_reason(done.request)}")
            if play.first_changeset is None:
                play.first_changeset = done.changeset
            if step["input"].get("label"):
                play.labels[step["input"]["label"]] = done.changeset
            continue
        if "keep_all" in step:
            play.tick()
            play.decide([i for i, e in play.entries().items() if e.data["status"] == "proposed"], step["keep_all"])
            continue
        before = set(play.entries())
        signals = play.correct(step["correct"])
        for signal_id in signals:
            request = learn.learn_request(play.store.read(), signal_id)
            if request is not None and request.data["state"] != "done":
                play.process(request.id, step["learn"], live=False)
        play.decide([i for i in play.entries() if i not in before], step.get("keep", True))


def _run_scenario(
    template: Path, scenario: dict[str, Any], n: int, *, versions: dict[str, str | None] | None, **how: Any
) -> RunResult:
    factory: AdapterFactory = how.pop("adapter_factory")
    problems: list[str] = []
    forbidden: list[str] = []
    extra: list[str] = []
    seen: dict[int, tuple[list[dict[str, Any]], Store]] = {}
    played: list[_Play] = []
    request = ""
    given: list[str] = []
    stopped: str | None = None
    with tempfile.TemporaryDirectory() as tmp:
        try:
            for day in (1, 30):
                (Path(tmp) / f"day{day}").mkdir()
                play = _Play(template, Path(tmp) / f"day{day}", scenario["id"], **how)
                played.append(play)
                records = starting_records(template, {"id": scenario["id"], **scenario})
                if records:
                    _create_starting_records(play.store, scenario["id"], records)
                if day == 30:
                    _history(play, scenario)
                spec = scenario[f"day{day}"]
                handed = play.hand_in(scenario["input"], play.last_changeset)
                if day == 30:
                    request = handed
                    text = play.packet_text(handed)
                    problems += [
                        f"day 30: the packet doesn't hold {w!r}" for w in spec.get("packet_has", []) if w not in text
                    ]
                    problems += [f"day 30: the packet holds {w!r}" for w in spec.get("packet_lacks", []) if w in text]
                people_before = len(play.store.read().list("person"))
                done = play.process(handed, scenario["ideal"][f"day{day}"], live=True)
                if done is None:
                    raise _Stop(f"day {day}: the input didn't finish: {play.waiting_reason(handed)}")
                outcomes = _outcomes(play.store, [done])
                seen[day] = (outcomes, play.store)
                miss, forb, more = _score(spec, outcomes, play.store, handed, people_before)
                problems += [f"day {day}: missing {m}" for m in miss]
                forbidden += [f"day {day}: {f}" for f in forb]
                extra += [f"day {day}: {e}" for e in more]
                if day == 30:
                    given = play.given(handed)
            for diff in scenario["differences"]:
                here, other = (1, 30) if diff["day"] == 1 else (30, 1)
                on_here = bool(_matching(diff["expect"], *seen[here]))
                on_other = bool(_matching(diff["expect"], *seen[other]))
                if not on_here or on_other:
                    problems.append(
                        f"difference: {diff['why']} ({_describe(diff['expect'])} only on day {diff['day']})"
                    )
        except _Stop as err:
            stopped = str(err)
        accounts, cost, seconds = [], 0.0, 0.0
        for play in played:
            found = _usage(play)
            accounts += found[0]
            cost, seconds = cost + found[1], seconds + found[2]
        if played:
            _versions(played[-1], versions, factory)
        refused = bool(stopped and played and played[-1].refused(request or ""))
        passed = stopped is None and not problems and not forbidden and not extra
        out = RunResult(
            scenario["id"],
            n,
            passed,
            problems,
            forbidden,
            extra,
            error=stopped,
            not_run=refused,
            cost_usd=cost,
            seconds=seconds,
            accounts=sorted(set(accounts)),
            given=given,
            got=[] if passed else [_summarize(o) for o in seen.get(30, ([], None))[0]],
        )
        for play in played:
            play.close()
        return out


# ---- the command -----------------------------------------------------------------------------------------------------


def evaluate_pairs(
    template: Path,
    *,
    account: str | None = None,
    runs: int = 1,
    stub: bool = False,
    env: Mapping[str, str] | None = None,
    only: list[str] | None = None,
    ai_config: Path | None = None,
    progress: Callable[[RunResult, int, int], None] | None = None,
    notice: Callable[[str], None] | None = None,
    adapter_factory: AdapterFactory = make_adapter,
) -> Report:
    """Run every pair and scenario (or `only` these) `runs` times. With `stub`, each stage answers from the pair's
    `ideal`, which checks the pairs and the plumbing rather than a model."""
    env = os.environ if env is None else env
    versions: dict[str, str | None] = {}
    items = [
        *((_run_pair, p) for p in load_pairs(template)),
        *((_run_scenario, s) for s in load_scenarios(template)),
    ]
    # A pending pair is run only when it is named.
    items = [(run, item) for run, item in items if (item["id"] in only if only else not item.get("pending"))]
    total, results = len(items) * runs, []
    for run, item in items:
        for n in range(1, runs + 1):
            step = f"[{len(results) + 1}/{total}] {item['id']}"
            if notice is not None:
                notice(f"{step}: started")
            waited = (
                (lambda s, step=step: notice(f"{step}: the account asked to slow down; trying again in {s:.0f}s"))
                if notice
                else None
            )
            results.append(
                run(
                    template,
                    item,
                    n,
                    versions=versions,
                    account=account,
                    stub=stub,
                    env=env,
                    ai_config=ai_config,
                    on_wait=waited,
                    adapter_factory=adapter_factory,
                )
            )
            if progress is not None:
                progress(results[-1], len(results), total)
    return Report(account or ("stub" if stub else "configured"), runs, results, versions)
