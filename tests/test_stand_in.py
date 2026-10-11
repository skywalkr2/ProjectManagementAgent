"""The stand-in AI with nothing scripting it: plain rules turn a hand-in's lines into actions, needs and decisions with
their exact words, and an ask is answered by quoting the user guide, so the demo works without an account."""

import pytest
from fastapi.testclient import TestClient

from engine.ai.adapters.stand_in import answer, read
from engine.ai.adapters.stub import set_responder
from engine.config import load_config
from tests.conftest import DEMO_B

CALL = (DEMO_B / "inbox" / "call-notes.md").read_text()


def wrapped(text, source="call-notes.md"):
    return f'Today is 2030-03-04 (Monday).\n\n<untrusted source="{source}">\n{text}\n</untrusted>'


def test_lines_become_actions_needs_and_decisions_with_their_words():
    body = read(
        wrapped(
            "# Weekly call\n- Pat Doe will send the quotes by 2030-03-08.\n- I will book the room.\n"
            "- We still need the final page count.\n- Need to confirm the print slot.\n"
            "- Decided: the cover stays blue.\n- We talked about the weather."
        )
    )
    ops = body["ops"]
    assert ops[0] == {
        "op": "action.add",
        "text": "Send the quotes by 2030-03-08.",
        "owners": ["Pat Doe"],
        "due": "2030-03-08",
        "evidence": {"quote": "Pat Doe will send the quotes by 2030-03-08."},
    }
    assert ops[1]["owners"] == ["me"] and ops[1]["text"] == "Book the room."
    assert ops[2]["owners"] == [] and ops[2]["text"] == "Get the final page count."
    assert ops[3]["text"] == "Confirm the print slot."
    assert ops[4] == {
        "op": "fact",
        "text": "The cover stays blue.",
        "evidence": {"quote": "Decided: the cover stays blue."},
    }
    assert ops[5] == {"op": "note", "text": "We talked about the weather."}
    assert "5 items" in body["summary"]


def test_nothing_it_reads_is_kept_as_a_note_and_pronouns_own_nothing():
    body = read(wrapped("We will think about it."))
    assert body["ops"] == [{"op": "note", "text": "We will think about it."}]


def test_an_answer_quotes_the_first_guide_passage():
    guide = "# From the user guide\n## Backups\nBackups copy the workspace. More here."
    request = f"Today is x.\n\n{guide}\n\n<question>\nq\n</question>"
    op = answer(request, "")["ops"][0]
    assert op["cites"] == [{"quote": "Backups copy the workspace."}] and "Backups" in op["text"]


@pytest.fixture
def app(tmp_path):
    from api.app import create_app
    from engine.workspace import init_workspace

    set_responder(None)
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={})
    application = create_app(ws, cfg, "t", start_worker=False)
    c = TestClient(application)
    c.headers["Authorization"] = "Bearer t"
    yield c, cfg.server.base_path.rstrip("/") + "/api", application.state.worker, ws


def test_the_demo_reads_a_hand_in_and_answers_a_question_with_no_account(app):
    from engine.storage import Store

    c, api, worker, ws = app
    assert c.post(f"{api}/handin", json={"note": "", "pasted": CALL}).status_code == 200
    worker.run_pending()
    owned = next(line for line in CALL.splitlines() if " will " in line).lstrip("- ")
    owner, what = owned.split(" will ", 1)
    store = Store(ws.db_path)
    try:
        view = store.read()
        actions = {a.data["text"]: a.data for a in view.list("action")}
        added = actions[what[0].upper() + what[1:]]
        names = {p.id: p.data["full_name"] for p in view.list("person")}
        assert [names[o["person"]] for o in added["owners"]][0].startswith(owner)
        assert any(not a["owners"] for a in actions.values())  # "we still need" waits for an owner
    finally:
        store.close()
    asked = c.post(f"{api}/ask", json={"question": "How do backups work?"}).json()["id"]
    worker.run_pending()
    found = next(a for a in c.get(f"{api}/asks").json() if a["id"] == asked)
    assert found["answer"] and found["answer"]["cites"]
