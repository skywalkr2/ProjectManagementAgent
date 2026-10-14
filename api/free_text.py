"""Where the free text a person types goes (design 6.5): the one place every route that takes it is declared.

Anything the person types that could change the work is an input, so a route that takes free text either hands it to
the assistant or says why it stays local. The self-check (`engine/selfcheck/free_text.py`) lists the routes whose
request has free text, by the rule written there, and fails for any route not declared here, or declared here and gone.

A route key is the method and the path as the API's schema writes it. A declaration is one of:
- `to_assistant`: the text becomes an input the assistant reads, either through `engine.intake.note_as_input` (a note
  on an action or question) or because the route itself queues the work with the text.
- `local_only`: the text is a name, a label, an address or a setting kept as the person's own record, or a choice among
  items; nothing the assistant should read as a note.
"""

from __future__ import annotations

from dataclasses import dataclass

TO_ASSISTANT = "to_assistant"
LOCAL_ONLY = "local_only"


@dataclass(frozen=True)
class Declared:
    kind: str
    reason: str


def _to(reason: str) -> Declared:
    return Declared(TO_ASSISTANT, reason)


def _local(reason: str) -> Declared:
    return Declared(LOCAL_ONLY, reason)


_ACCOUNT = "an AI account's settings: names, addresses and options kept as the person's configuration"
_SETTING = "settings kept as the person's configuration"
_DETAILS = "details of a record the person keeps for reading"

ROUTES: dict[str, Declared] = {
    # A note on an action or a question: handed in as the person's own words.
    "POST /api/actions/{action_id}/status": _to("the note typed with Mark done or reopen, through the note helper"),
    "POST /api/followups/{person}/actions/{action_id}/finished": _to(
        "the note typed with They finished it, through the note helper"
    ),
    "POST /api/followups/{person}/actions/{action_id}/followed-up": _to(
        "the note typed with Followed up, through the note helper"
    ),
    "POST /api/questions/{qid}/pick-owner": _to("the note typed with the owner's pick, through the note helper"),
    "POST /api/questions/{qid}/answer": _to("a written answer or a note with a pick, through the note helper"),
    "POST /api/records/edit": _to("text added to an action's notes goes through the note helper"),
    "POST /api/items/{kind}/{id}/change": _to(
        "the note asking for a change to an action, question, decision, calendar entry or fact is queued as an input "
        "about that item, through the note helper"
    ),
    # Routes that queue the assistant's work with the person's text.
    "POST /api/handin": _to("the person's note and pasted material become an input"),
    "POST /api/ask": _to("a question to the assistant is queued as an ask"),
    "POST /api/changesets/{cs_id}/send-back": _to("the note on the changes sent back is queued with the new run"),
    "POST /api/questions/{qid}/reply": _to("a pasted reply is handed in with a note saying which question it answers"),
    "POST /api/task-kinds/{name}/start": _to("the note on a started piece of work is queued with it"),
    # Local: the text is the person's own record or setting.
    "POST /api/followups/{person}/mark-sent": _local(
        "the message as sent, compared with the draft for a quality signal; not a note"
    ),
    "POST /api/questions/{qid}/reword": _local(
        "the person's own new wording of a question, kept as the question's text and recorded as a correction; not a "
        "note"
    ),
    "POST /api/questions/{qid}/drop": _local(
        "the reason the person dropped a question, kept with it and with the correction; not a note"
    ),
    "POST /api/texts/edit": _local("the person's own edit of a long text, kept as their version of it"),
    "POST /api/knowledge/{entry_id}/keep": _local(
        "the person's own wording of an entry they keep: it is guidance because they kept it, never an input for the "
        "assistant to read as a note"
    ),
    "POST /api/knowledge/{entry_id}/narrow": _local(
        "the person's own limit on what a rule or entry applies to, kept as its scope; not a note"
    ),
    "POST /api/knowledge/{entry_id}/discard": _local(
        "the reason the person discarded a proposal, kept with it so the same one isn't shown again; not a note"
    ),
    "POST /api/organizations": _local(_DETAILS),
    "POST /api/organizations/{oid}": _local(_DETAILS),
    "POST /api/projects": _local(_DETAILS),
    "POST /api/projects/{prj}": _local(_DETAILS),
    "POST /api/settings": _local(_SETTING),
    "POST /api/ai/accounts": _local(_ACCOUNT),
    "POST /api/data-forms/{name}/file": _local("the values of a data file the person edits as configuration"),
    "POST /api/data-forms/{name}/remove": _local("the values of a data file the person edits as configuration"),
    "POST /api/watch/sources": _local(_SETTING),
    "POST /api/watch/sources/{source_id}": _local(_SETTING),
}
