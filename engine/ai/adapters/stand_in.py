"""What the stand-in AI answers when nothing scripts it: plain rules over the input, so a person trying the app without
an account sees the whole loop work on their own words. It is no model and claims to be none.

Reading an input, each line is looked at on its own:
- "<Name> will <do something>" (or "is going to", "needs to", "should") becomes an action owned by that name; "I will"
  is the PM's own. A date written YYYY-MM-DD after "by", "on" or "before" becomes its due date.
- "We need <something>", "Need to <do something>" or "To do: <something>" becomes an action with no owner, which waits
  for the PM to pick one.
- "Decided: …", "Agreed: …" or "Decision: …" becomes a fact.
Every one cites its line word for word. Whatever else the input says is kept as one note.

Answering a question, it quotes the first passage of the user guide chosen for the question.
"""

from __future__ import annotations

import re
from typing import Any

_INPUT = re.compile(r"<untrusted[^>]*>\s*(.+?)\s*</untrusted>|<note>\s*(.+?)\s*</note>", re.S)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_NAME = r"[A-Z][\w'’-]+(?: [A-Z][\w'’-]+)?"
_WILL = re.compile(rf"^(?P<who>I|{_NAME}) (?:will|is going to|needs to|should) (?P<what>.+?)[.!]?$")
_NEED_TO = re.compile(r"^(?:we )?(?:still )?needs? to (?P<what>.+?)[.!]?$", re.I)
_NEED = re.compile(r"^we (?:still )?need (?P<what>.+?)[.!]?$", re.I)
_TODO = re.compile(r"^to ?do:\s*(?P<what>.+?)[.!]?$", re.I)
_DECIDED = re.compile(r"^(?:decided|agreed|decision):\s*(?P<what>.+?)\s*$", re.I)
_DUE = re.compile(r"\b(?:by|on|before) (\d{4}-\d{2}-\d{2})\b")
_NOT_NAMES = {"We", "They", "You", "He", "She", "It", "This", "That", "Someone", "Everyone", "Nobody"}


def input_lines(request: str) -> list[str]:
    """The lines of the input (outside material and the PM's note), bullets removed, headings and blanks left out."""
    lines = []
    for match in _INPUT.finditer(request):
        for raw in (match.group(1) or match.group(2) or "").splitlines():
            line = _BULLET.sub("", raw).strip()
            if line and not line.startswith(("#", "{")):
                lines.append(line)
    return lines


def _sentence(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:] + ("" if text.endswith((".", "!", "?")) else ".")


def read(request: str) -> dict[str, Any]:
    """A changeset for one input, by the rules above."""
    ops: list[dict[str, Any]] = []
    rest: list[str] = []
    for line in input_lines(request):
        will, decided = _WILL.match(line), _DECIDED.match(line)
        todo = _NEED_TO.match(line) or _TODO.match(line)
        need = _NEED.match(line)
        if will and will.group("who").split()[0] not in _NOT_NAMES:
            who = "me" if will.group("who") == "I" else will.group("who")
            op = {"op": "action.add", "text": _sentence(will.group("what")), "owners": [who]}
        elif todo:
            op = {"op": "action.add", "text": _sentence(todo.group("what")), "owners": []}
        elif need:
            op = {"op": "action.add", "text": _sentence("get " + need.group("what")), "owners": []}
        elif decided:
            op = {"op": "fact", "text": _sentence(decided.group("what"))}
        else:
            rest.append(line)
            continue
        if op["op"] == "action.add" and (due := _DUE.search(line)):
            op["due"] = due.group(1)
        op["evidence"] = {"quote": line}
        ops.append(op)
    if rest or not ops:
        ops.append({"op": "note", "text": " ".join(rest)[:2000] or "(empty input)"})
    found = sum(1 for op in ops if op["op"] != "note")
    summary = (
        f"The stand-in read {found} item{'s' if found != 1 else ''} by its rules."
        if found
        else ("The stand-in found nothing it reads by rule, so it kept the input as a note.")
    )
    return {"summary": summary, "ops": ops}


def answer(request: str, stable: str) -> dict[str, Any]:
    """An answer quoting the first sentence of the first guide passage chosen for the question."""
    guide = request.split("# From the user guide", 1)[1] if "# From the user guide" in request else ""
    guide = guide.split("<question>", 1)[0]
    section = re.search(r"^## (?P<title>.+)\n(?P<text>.+?)(?=\n## |\Z)", guide.strip(), re.S | re.M)
    if section:
        first = re.split(r"(?<=[.!?])\s", " ".join(section.group("text").split()), maxsplit=1)[0]
        return {
            "summary": "Answered from the user guide.",
            "ops": [
                {
                    "op": "answer",
                    "text": f'The stand-in can only point to the user guide. Under "{section.group("title")}" it '
                    f"says: {first}",
                    "cites": [{"quote": first}],
                }
            ],
        }
    install = stable.split("# What this install can do\n", 1)[1] if "# What this install can do\n" in stable else ""
    can_do = next((line.strip() for line in install.splitlines() if line.strip() and not line.startswith("#")), "")
    return {
        "summary": "Nothing in the user guide matched.",
        "ops": [
            {
                "op": "answer",
                "text": "The stand-in found nothing in the user guide about that. An AI account answers in its own "
                "words.",
                "cites": [{"quote": can_do or "the user guide"}],
            }
        ],
    }


def sort_mail(request: str) -> dict[str, Any]:
    """Sorting mail headers: every message is work. The stand-in reads no headers and claims no judgment, so it hides
    nothing."""
    return {"answers": [{"id": name, "answer": "work"} for name in re.findall(r'"id": "(m\d+)"', request)]}
