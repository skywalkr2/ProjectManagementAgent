"""Outside content (design 6.8, 12.8): it never rewords a question, only adds a note to it, and it never routes the
person's work away from them; a sender's own "not me, ask someone" is still proposed."""

from __future__ import annotations

from tests.test_knowledge_records import app, apply, reasons  # noqa: F401  (the fixture is used by name)


def _question(store, cfg) -> str:
    pm = cfg.workspace.user.person
    cs_id, statuses = apply(store, cfg, [{"op": "question.add", "to": pm, "title": "Which paper stock?"}])
    assert statuses == ["applied"]
    return store.read().get("changeset", cs_id).data["ops"][0]["records"][0]["id"]


def test_outside_content_cannot_reword_a_question_but_can_add_a_note_to_it(app):  # noqa: F811
    _, store, cfg, _ = app
    question = _question(store, cfg)
    reword = {"op": "record.set", "kind": "question", "id": question, "field": "title", "value": "Which cover?"}
    cs_id, statuses = apply(store, cfg, [reword], origin="input", trust="untrusted")
    assert statuses == ["refused"] and "only the person rewords a question" in reasons(store, cs_id)[0]
    note = {"op": "note", "text": "The printer says only the matte stock is left.", "question": question}
    cs_id, statuses = apply(store, cfg, [note], origin="input", trust="untrusted")
    assert statuses == ["applied"]
    (kept,) = [n for n in store.read().list("note") if n.data.get("question") == question]
    assert kept.data["trust"] == "untrusted"
    assert store.read().get("question", question).data["title"] == "Which paper stock?"


def test_outside_content_never_routes_the_persons_work_away_and_a_senders_not_me_is_still_proposed(app):  # noqa: F811
    _, store, cfg, _ = app
    pm = cfg.workspace.user.person
    other = next(p.id for p in store.read().list("person") if p.id != pm)
    away = {"op": "routing.add", "text": "T.", "topic": "cover decisions", "person": pm, "negative": True}
    cs_id, statuses = apply(store, cfg, [away], origin="input", trust="untrusted")
    assert statuses == ["refused"] and "never routes work away from the person" in reasons(store, cs_id)[0]
    not_me = {"op": "routing.add", "text": "T.", "topic": "the reviewer list", "person": other}
    cs_id, statuses = apply(store, cfg, [not_me], origin="input", trust="untrusted")
    assert statuses != ["refused"]


def test_the_persons_own_note_can_file_a_question_as_already_asked_and_outside_content_cannot(app):  # noqa: F811
    _, store, cfg, _ = app
    asked = {"op": "question.mark_sent", "id": _question(store, cfg)}
    cs_id, statuses = apply(store, cfg, [asked], origin="input", trust="untrusted")
    assert statuses == ["refused"] and "only the person" in reasons(store, cs_id)[0]
    assert apply(store, cfg, [asked], origin="pm", trust="trusted")[1] == ["applied"]
