"""Follow-ups by person (design 7.5): what each person has from the PM, and one clean message to copy.

The PM comes first (decisions and the PM's own actions), then everyone else A to Z. A copied message has a greeting,
the questions (numbered when there are several), the person's action items with project and due date, and a closing
line; its wording comes from config/language.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from engine.cleaning import normalize
from engine.config import Config
from engine.dispatcher import signal
from engine.names import People
from engine.storage import Store, WriteContext

_PM = WriteContext(actor="pm", trust="trusted", op="followup")

#: Questions that hold an item until the PM says who: answered on the item itself.
ROUTING = ("held-op", "owner")


@dataclass
class Section:
    person: str
    name: str
    is_pm: bool
    questions: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""
    to_send: int = 0


def sections(store: Store, cfg: Config, today: date) -> list[Section]:
    people = People(store, cfg)
    projects = {p.id: p.data["name"] for p in store.read().list("project")}
    by_person: dict[str, Section] = {}

    def section(pid: str) -> Section:
        if pid not in by_person:
            by_person[pid] = Section(pid, people.name(pid), pid == people.pm)
        return by_person[pid]

    for q in store.read().list("question"):
        d = q.data
        if d["status"] not in ("open", "sent"):
            continue
        if (d.get("resolves") or {}).get("kind") in ROUTING:
            continue  # answered where the item waits (What changed), so it isn't shown twice
        sent = datetime.fromisoformat(d["sent_at"]).date() if d.get("sent_at") else None
        waiting = (today - sent).days if sent else None
        section(d["to"]).questions.append(
            {
                "id": q.id,
                "title": d["title"],
                "text": d.get("text", ""),
                "links": d.get("links", []),
                "kind": d["kind"],
                "status": d["status"],
                "sent": sent.isoformat() if sent else None,
                "waiting_days": waiting,
                "options": d.get("options", []),
                "resolves": d.get("resolves"),
            }
        )
    for a in store.read().list("action"):
        d = a.data
        if d["status"] != "open":
            continue
        for owner in d.get("owners", []):
            told = d.get("told", {}).get(owner["person"])
            section(owner["person"]).actions.append(
                {
                    "id": a.id,
                    "text": d["text"],
                    "due": d.get("due"),
                    "project": d.get("project"),
                    "project_name": projects.get(d.get("project"), ""),
                    "told": told,
                    "told_days": (today - date.fromisoformat(told)).days if told else None,
                }
            )
    for s in by_person.values():
        s.actions.sort(key=lambda a: (a["due"] or "9999", a["text"]))
        if not s.is_pm:
            s.to_send = sum(q["status"] == "open" for q in s.questions) + sum(a["told"] is None for a in s.actions)
            s.message = compose(s, cfg, people)
    return sorted(by_person.values(), key=lambda s: (not s.is_pm, s.name.lower()))


def compose(s: Section, cfg: Config, people: People) -> str:
    words = cfg.language.messages
    questions = [q for q in s.questions if q["status"] == "open"]
    actions = [a for a in s.actions if a["told"] is None]
    if not questions and not actions:
        return ""
    lines = [words.greeting.format(first_name=people.first_name(s.person)), ""]
    for n, q in enumerate(questions, 1):
        prefix = f"{n}. " if len(questions) > 1 else ""
        lines.append(prefix + q["title"])
        if q["text"]:
            lines.append(q["text"])
        lines += [f"{link['label']}: {link['url']}" for link in q["links"]]
        lines.append("")
    if actions:
        lines.append(words.actions_heading)
        for a in actions:
            bits = [a["project_name"]] if a["project_name"] else []
            if a["due"]:
                bits.append("due " + date.fromisoformat(a["due"]).strftime(words.date_format))
            lines.append(f"- {a['text']}" + (f" ({', '.join(bits)})" if bits else ""))
        lines.append("")
    lines.append(words.closing)
    return "\n".join(lines)


def mark_sent(
    store: Store, cfg: Config, person: str, *, sent_text: str | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Record that the person's open questions and untold actions went out. If the PM edited the message before
    sending, that is recorded as a quality signal. Returns the counts and the ids, which `unmark_sent` takes."""
    now = now or datetime.now(UTC)
    today = now.date()
    current = next((s for s in sections(store, cfg, today) if s.person == person), None)
    if current is None:
        return {"questions": 0, "actions": 0, "question_ids": [], "action_ids": []}
    counts: dict[str, Any] = {"questions": 0, "actions": 0, "question_ids": [], "action_ids": []}
    with store.transaction() as tx:
        for q in current.questions:
            if q["status"] == "open":
                rec = tx.get("question", q["id"])
                tx.update(
                    "question", q["id"], {"status": "sent", "sent_at": now.isoformat()}, _PM, read_version=rec.version
                )
                counts["questions"] += 1
                counts["question_ids"].append(q["id"])
        for a in current.actions:
            if a["told"] is None:
                rec = tx.get("action", a["id"])
                told = {**rec.data.get("told", {}), person: today.isoformat()}
                tx.update("action", a["id"], {"told": told}, _PM, read_version=rec.version)
                counts["actions"] += 1
                counts["action_ids"].append(a["id"])
    if sent_text is not None and normalize(sent_text) != normalize(current.message):
        signal(store, "draft_edited", [person], note=sent_text, now=now)
    return counts


def unmark_sent(store: Store, person: str, question_ids: list[str], action_ids: list[str]) -> None:
    """Undo a Mark sent: the questions are open again and the person is no longer marked as told."""
    with store.transaction() as tx:
        for qid in question_ids:
            rec = tx.get("question", qid)
            if rec is not None and rec.data["status"] == "sent":
                tx.update("question", qid, {"status": "open", "sent_at": None}, _PM, read_version=rec.version)
        for aid in action_ids:
            rec = tx.get("action", aid)
            if rec is not None and person in rec.data.get("told", {}):
                told = {k: v for k, v in rec.data["told"].items() if k != person}
                tx.update("action", aid, {"told": told}, _PM, read_version=rec.version)
