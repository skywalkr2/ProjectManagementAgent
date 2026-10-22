"""A newer model is asked about, or moved to after a check, never switched to unchecked (design 6.16): the weekly
look at each account's models and prices, the one Today line per account with the cost change at the current use,
the check that comes before any move on its own (estimated first, held above the configured amount, a failed one
leaves the tier as it was), Switch through the settings' own switch, Not now kept until a different model appears,
and Keep and Switch back for a move made on its own. Families and ids come from the catalog fixture and are made up;
nothing calls a network."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

import engine.evaluate as ev
from api.app import create_app
from engine.ai import model_watch, native_move, switch_check
from engine.ai.task import ModelInfo
from engine.config import load_config
from engine.setup import known_endpoints
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

CLAIMS = yaml.safe_load((Path(__file__).parent / "fixtures" / "ai" / "catalog-claims.yaml").read_text("utf-8"))
SERVICE = next(e for e in known_endpoints() if e["id"] == CLAIMS["native_adapter"]["entry"])
SMALL = SERVICE["tier_presets"]["routine"]["family"]
LARGE = SERVICE["tier_presets"]["deep"]["family"]
HARDEST = SERVICE["tier_presets"]["hardest"]["family"]
NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
CASES = ("close-action",)
CURRENT, NEWER, NEWEST = f"x-{SMALL}-1", f"x-{SMALL}-2", f"x-{SMALL}-3"
BIG = f"x-{LARGE}-1"
CHEAP, SAME, DEAR = (0.5, 2.0), (1.0, 5.0), (3.0, 9.0)
HOSTED = "https" + "://models.example.com/v1"
RUN = WriteContext("engine", "trusted", "test")


def listing(prices=None, extra=()):
    """What the service lists: the tier models and a few more, each with a price where the table gives one."""
    prices = {CURRENT: SAME, BIG: (2.0, 8.0), **(prices or {})}
    ids = [CURRENT, BIG, f"x-{LARGE}-0", *extra, f"x-other-{99}"]
    return {
        i: ModelInfo(input_per_million=prices[i][0], output_per_million=prices[i][1]) if i in prices else ModelInfo()
        for i in ids
    }


class Lister:
    def __init__(self, models):
        self.models = models

    def catalog(self):
        return self.models


def start(tmp_path, monkeypatch, follow=True, confirm=None):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    path = ws.config_dir / "ai.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["providers"]["acct"] = {
        "adapter": native_move.GENERIC,
        "kind": SERVICE["id"],
        "base_url": HOSTED,
        "models": {"default": CURRENT, "harder": BIG},
        "allowed_data": ["open", "internal", "restricted"],
    }
    raw["tiers"]["routine"] = {"use": "acct/default", "fallback": [], "escalate_to": "deep"}
    raw["tiers"]["deep"] = {"use": "acct/harder"}
    raw["models"] = {"follow_newest": follow, "check_every_days": 7, "use_days": 7}
    if confirm is not None:
        raw.setdefault("budgets", {})["confirm_above_usd"] = confirm
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    store.close()
    app = create_app(ws, cfg, "t", start_worker=False)
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer t"
    return ws, client


class Watch:
    """One look, with the service's list, the check's price and the check itself in place of the real ones."""

    def __init__(self, ws, models, estimate=(0.05, 40), passes=True):
        self.ws, self.models, self.estimate, self.passes = ws, models, estimate, passes
        self.estimated, self.checked, self.tier_at_check = [], [], None

    def run(self, now=NOW):
        cfg = load_config(self.ws.config_dir, env={})
        store = Store(self.ws.db_path, cfg=cfg)
        try:
            return model_watch.run(
                self.ws,
                store,
                cfg,
                {},
                now=now,
                factory=lambda *a: Lister(self.models),
                estimator=self.price,
                evaluator=self.check,
            )
        finally:
            store.close()

    def price(self, cfg, ws, ref, env=None, ai_config=None):
        self.estimated.append((ref, ai_config.read_text() if ai_config else None))
        return self.estimate

    def check(self, ref, cfg, ws, env, most_private=None, ai_config=None):
        self.checked.append(ref)
        self.tier_at_check = used(ws)["routine"]
        assert (
            ai_config is not None
            and ref.partition("/")[2] in yaml.safe_load(ai_config.read_text())["providers"]["acct"]["models"]
        )
        only = list(CASES)
        if not self.passes:
            original = ev.load_cases
            ev.load_cases = lambda t: [
                {**c, "expect": [*c.get("expect", []), {"op": "action.add", "text_has": ["never-present"]}]}
                for c in original(t)
            ]
            try:
                return ev.evaluate(DEMO_B, stub=True, runs=1, env={}, only=only)
            finally:
                ev.load_cases = original
        return ev.evaluate(DEMO_B, stub=True, runs=1, env={}, only=only)


def used(ws):
    return {n: t.use for n, t in load_config(ws.config_dir, env={}).ai.tiers.items()}


def api(client, ws):
    return load_config(ws.config_dir, env={}).server.base_path.rstrip("/") + "/api"


def today(client, ws, kind="model_watch"):
    client.app.state.worker.apply_live()  # the app takes in changed live settings as its worker does
    return [x for x in client.get(f"{api(client, ws)}/today/queue").json() if x["kind"] == kind]


def runs(ws, tier="routine", n=3, tokens=(1_000_000, 200_000), at=NOW - timedelta(hours=5)):
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    for i in range(n):
        data = {
            "task": "notes",
            "provider": "acct",
            "model": CURRENT,
            "tier": tier,
            "outcome": "ok",
            "started_at": (at - timedelta(minutes=i)).isoformat(),
            "input_tokens": tokens[0],
            "output_tokens": tokens[1],
        }
        with store.transaction() as tx:
            tx.create("run", data, RUN)
    store.close()


def fp(client, ws):
    return client.get(f"{api(client, ws)}/settings").json()["fingerprint"]


@pytest.fixture
def lower(tmp_path, monkeypatch):
    ws, client = start(tmp_path, monkeypatch)
    runs(ws)
    return ws, client


# ---- what is newer -------------------------------------------------------------------------------------------------


def test_a_newer_model_of_the_same_family_gives_one_line_with_the_cost_change_and_nothing_else_does(
    tmp_path, monkeypatch
):
    ws, client = start(tmp_path, monkeypatch, follow=False)
    runs(ws)  # 3 runs of a million tokens in and 200,000 out over 7 days
    watch = Watch(ws, listing({NEWER: DEAR}, extra=[NEWER, f"x-{LARGE}-0"]))
    assert watch.run() == []
    (line,) = today(client, ws)
    assert (line["group"], line["account"], line["state"], line["names"]) == ("decide", "acct", "newer", ["routine"])
    assert line["candidates"] == {"routine": NEWER} and line["reason"] == "costs_more"
    # 3 runs over 7 days: (3M * 3.0 + 0.6M * 9.0) / 7 against (3M * 1.0 + 0.6M * 5.0) / 7, per day
    assert line["usd_per_day"] == pytest.approx(((3 * 3.0 + 0.6 * 9.0) - (3 * 1.0 + 0.6 * 5.0)) / 7, abs=1e-3)
    assert used(ws)["routine"] == "acct/default", "nothing switches without the person"


def test_nothing_changed_gives_no_line_and_another_family_is_never_offered(tmp_path, monkeypatch):
    ws, client = start(tmp_path, monkeypatch)
    Watch(ws, listing(extra=[f"x-other-{1000}", f"x-{HARDEST}-50"])).run()  # newer, but of no tier's family
    assert today(client, ws) == [] and today(client, ws, "model_moved") == []
    assert used(ws) == {
        "routine": "acct/default",
        "deep": "acct/harder",
        **{k: v for k, v in used(ws).items() if k not in ("routine", "deep")},
    }
    state = model_watch.read(Store(ws.db_path, cfg=load_config(ws.config_dir, env={})))
    assert all(not offers for offers in state["offers"].values())


def test_the_newest_of_several_newer_models_is_the_one_offered(tmp_path, monkeypatch):
    ws, client = start(tmp_path, monkeypatch, follow=False)
    Watch(ws, listing({NEWER: CHEAP, NEWEST: CHEAP}, extra=[NEWER, NEWEST])).run()
    assert today(client, ws)[0]["candidates"] == {"routine": NEWEST}


def test_the_listing_order_alone_never_says_a_model_is_newer(tmp_path, monkeypatch):
    ws, client = start(tmp_path, monkeypatch, follow=False)
    models = {f"{SMALL}-latest": ModelInfo(), f"{SMALL}-current": ModelInfo()}
    cfg_text = (ws.config_dir / "ai.yaml").read_text().replace(CURRENT, f"{SMALL}-current")
    (ws.config_dir / "ai.yaml").write_text(cfg_text)
    Watch(ws, models).run()
    assert today(client, ws) == []


def test_the_look_is_due_after_the_configured_days_and_a_failed_listing_is_tried_again_soon(tmp_path, monkeypatch):
    ws, client = start(tmp_path, monkeypatch)
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert model_watch.due(store, cfg, NOW)
    Watch(ws, listing()).run()
    assert not model_watch.due(store, cfg, NOW + timedelta(days=6))
    assert model_watch.due(store, cfg, NOW + timedelta(days=7))
    Watch(ws, {}).run(NOW + timedelta(days=8))  # the service couldn't be read
    assert not model_watch.due(store, cfg, NOW + timedelta(days=8, minutes=30))
    assert model_watch.due(store, cfg, NOW + timedelta(days=8, minutes=model_watch.RETRY_MINUTES))
    store.close()


# ---- the setting on and off, the price, the check ---------------------------------------------------------------


def test_with_the_setting_on_a_newer_model_that_costs_less_moves_only_after_a_passed_check(lower):
    ws, client = lower
    watch = Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER]))
    assert watch.run() == ["routine"]
    assert watch.checked == [f"acct/{NEWER}"] and watch.tier_at_check == "acct/default", "checked before it was written"
    assert used(ws)["routine"] == f"acct/{NEWER}" and used(ws)["deep"] == "acct/harder"
    assert load_config(ws.config_dir, env={}).ai.providers["acct"].models[NEWER] == NEWER
    assert today(client, ws) == []
    (moved,) = today(client, ws, "model_moved")
    assert (moved["tier"], moved["account"], moved["text"]) == ("routine", "acct", "acct")
    assert moved["usd_per_day"] < 0
    # The estimate came first, from a copy of the settings that held the new model.
    assert watch.estimated and NEWER in watch.estimated[0][1]


def test_the_same_price_moves_too(lower):
    ws, client = lower
    assert Watch(ws, listing({NEWER: SAME}, extra=[NEWER])).run() == ["routine"]
    assert used(ws)["routine"] == f"acct/{NEWER}"
    (moved,) = today(client, ws, "model_moved")
    assert moved["usd_per_day"] == 0


def test_a_price_lower_on_one_side_and_higher_on_the_other_is_not_lower(lower):
    ws, client = lower
    assert Watch(ws, listing({NEWER: (0.1, 9.0)}, extra=[NEWER])).run() == []
    assert today(client, ws)[0]["reason"] == "costs_more"


def test_a_higher_price_asks_with_the_setting_on_and_nothing_is_checked(lower):
    ws, client = lower
    watch = Watch(ws, listing({NEWER: DEAR}, extra=[NEWER]))
    assert watch.run() == [] and watch.checked == [] and watch.estimated == []
    (line,) = today(client, ws)
    assert line["reason"] == "costs_more" and line["usd_per_day"] > 0
    assert used(ws)["routine"] == "acct/default"


def test_a_price_not_known_asks_with_the_setting_on(lower):
    ws, client = lower
    models = listing(extra=[NEWER])  # no price for the new model
    watch = Watch(ws, models)
    assert watch.run() == [] and watch.checked == []
    (line,) = today(client, ws)
    assert line["reason"] == "price_unknown" and line["usd_per_day"] is None
    assert used(ws)["routine"] == "acct/default"


def test_a_price_in_the_settings_takes_precedence_over_the_listing_as_the_router_resolves_it(lower):
    ws, client = lower
    path = ws.config_dir / "ai.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["prices"] = {f"acct/{CURRENT}": {"input_per_million": 4.0, "output_per_million": 4.0}}
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    # The listing says the new one is cheaper than the listed price of the current one, but the settings price the
    # current one at four in and four out, which the new one exceeds on output: it costs more.
    Watch(ws, listing({NEWER: DEAR}, extra=[NEWER])).run()
    assert today(client, ws)[0]["reason"] == "costs_more"


def test_with_the_setting_off_a_cheaper_model_still_only_asks(tmp_path, monkeypatch):
    ws, client = start(tmp_path, monkeypatch, follow=False)
    runs(ws)
    watch = Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER]))
    assert watch.run() == [] and watch.checked == []
    (line,) = today(client, ws)
    assert line["reason"] == "asks" and line["usd_per_day"] < 0
    assert used(ws)["routine"] == "acct/default"


def test_a_failed_check_leaves_the_tier_as_it_was_and_the_line_says_why(lower):
    ws, client = lower
    watch = Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER]), passes=False)
    assert watch.run() == [] and watch.checked == [f"acct/{NEWER}"]
    assert used(ws)["routine"] == "acct/default"
    assert (
        used(ws)["routine"] == "acct/default"
        and NEWER not in load_config(ws.config_dir, env={}).ai.providers["acct"].models
    )
    assert today(client, ws, "model_moved") == []
    (line,) = today(client, ws)
    assert line["reason"] == "check_failed" and line["count"] >= 1 and line["candidates"] == {"routine": NEWER}
    # The next look doesn't run the same check again on the same model.
    again = Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER]), passes=True)
    again.run(NOW + timedelta(days=7))
    assert again.checked == []
    assert today(client, ws)[0]["reason"] == "check_failed"


def test_a_check_that_cannot_finish_is_never_a_pass(lower):
    ws, client = lower
    watch = Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER]))

    def broken(*args, **more):
        raise RuntimeError("no way to run it")

    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    model_watch.run(
        ws, store, cfg, {}, now=NOW, factory=lambda *a: Lister(watch.models), estimator=watch.price, evaluator=broken
    )
    store.close()
    assert used(ws)["routine"] == "acct/default"
    line = today(client, ws)[0]
    assert line["reason"] == "check_failed" and line["check_failed"] is True


def test_a_check_above_the_amount_asked_about_or_with_no_known_cost_waits_for_the_person(tmp_path, monkeypatch):
    for estimate in ((5.0, 40), (None, 0)):
        ws, client = start(tmp_path / str(estimate[0]), monkeypatch, confirm=1.0)
        runs(ws)
        watch = Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER]), estimate=estimate)
        assert watch.run() == [] and watch.checked == []
        (line,) = today(client, ws)
        assert line["reason"] == "check_cost" and line["estimate_usd"] == estimate[0]
        assert used(ws)["routine"] == "acct/default"


# ---- Switch, Not now, Keep and Switch back ---------------------------------------------------------------------


def test_switch_goes_through_the_settings_own_switch_with_its_check_and_nothing_changes_without_it(
    tmp_path, monkeypatch
):
    ws, client = start(tmp_path, monkeypatch, follow=False)
    runs(ws)
    Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER])).run()
    (line,) = today(client, ws)
    assert used(ws)["routine"] == "acct/default"
    calls = []
    monkeypatch.setattr(
        switch_check,
        "evaluate_on",
        lambda ref, cfg, ws_, env, *a, **k: (
            calls.append(ref) or Watch(ws, {}).check(ref, cfg, ws_, env, ai_config=_alias(ws, ref))
        ),
    )
    models = {**load_config(ws.config_dir, env={}).ai.providers["acct"].models, NEWER: NEWER}
    body = {"fingerprint": fp(client, ws), "models": models, "use": {"routine": NEWER}}
    done = client.post(f"{api(client, ws)}/ai/accounts/acct/switch-check", json=body)
    assert done.status_code == 200, done.text
    assert done.json()["checking"] is True
    client.app.state.worker._switching.join(timeout=60)
    assert used(ws)["routine"] == f"acct/{NEWER}" and calls == [f"acct/{NEWER}"]
    assert today(client, ws) == [], "once the tier is on that model the line has nothing left to say"


def _alias(ws, ref):
    import tempfile

    path = Path(tempfile.mkdtemp()) / "ai.yaml"
    path.write_text((ws.config_dir / "ai.yaml").read_text())
    return path


def test_not_now_is_kept_until_a_different_newer_model_appears(tmp_path, monkeypatch):
    ws, client = start(tmp_path, monkeypatch, follow=False)
    runs(ws)
    Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER])).run()
    assert len(today(client, ws)) == 1
    assert client.post(f"{api(client, ws)}/ai/model-watch/acct/newer/not-now").status_code == 200
    assert today(client, ws) == []
    Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER])).run(NOW + timedelta(days=7))
    assert today(client, ws) == [], "the same model is not asked about again"
    Watch(ws, listing({NEWER: CHEAP, NEWEST: CHEAP}, extra=[NEWER, NEWEST])).run(NOW + timedelta(days=14))
    assert today(client, ws)[0]["candidates"] == {"routine": NEWEST}
    assert client.post(f"{api(client, ws)}/ai/model-watch/other/newer/not-now").status_code == 404


def test_switch_back_restores_the_tiers_model_with_undo_and_the_line_goes(lower):
    ws, client = lower
    Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER])).run()
    assert used(ws)["routine"] == f"acct/{NEWER}"
    back = client.post(f"{api(client, ws)}/ai/switch/routine/back", json={"fingerprint": fp(client, ws)})
    assert back.status_code == 200, back.text
    assert used(ws)["routine"] == "acct/default" and today(client, ws, "model_moved") == []
    saved = back.json()
    undo = {
        "changes": {x["key"]: x["before"] for x in saved["changes"]},
        "reset": [],
        "fingerprint": saved["fingerprint"],
    }
    assert client.post(f"{api(client, ws)}/settings", json=undo).status_code == 200
    assert used(ws)["routine"] == f"acct/{NEWER}"


def test_keep_clears_the_line_and_the_move_stays(lower):
    ws, client = lower
    Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER])).run()
    assert len(today(client, ws, "model_moved")) == 1
    assert client.post(f"{api(client, ws)}/ai/switch/routine/keep").status_code == 200
    assert today(client, ws, "model_moved") == [] and used(ws)["routine"] == f"acct/{NEWER}"
    assert client.post(f"{api(client, ws)}/ai/switch/routine/keep").status_code == 404


def test_a_move_the_person_changed_since_has_no_line(lower):
    ws, client = lower
    Watch(ws, listing({NEWER: CHEAP}, extra=[NEWER])).run()
    changed = {"changes": {"ai.tiers.routine.use": "acct/harder"}, "reset": [], "fingerprint": fp(client, ws)}
    assert client.post(f"{api(client, ws)}/settings", json=changed).status_code == 200
    assert today(client, ws, "model_moved") == []


# ---- a price rise on the current model ---------------------------------------------------------------------------


def test_a_price_rise_on_the_current_model_is_reported_and_a_fall_is_not(tmp_path, monkeypatch):
    ws, client = start(tmp_path, monkeypatch)
    runs(ws)
    Watch(ws, listing()).run()  # the first look only notes the price
    assert today(client, ws) == []
    runs(ws, at=NOW + timedelta(days=7) - timedelta(hours=5))
    Watch(ws, listing({CURRENT: (1.5, 5.0)})).run(NOW + timedelta(days=7))
    (line,) = today(client, ws)
    assert line["state"] == "price" and line["names"] == ["routine"] and line["candidates"] == {}
    assert line["usd_per_day"] == pytest.approx((3 * 0.5) / 7, abs=1e-3)
    assert used(ws)["routine"] == "acct/default", "a price rise involves no switch"
    assert client.post(f"{api(client, ws)}/ai/model-watch/acct/price/not-now").status_code == 200
    assert today(client, ws) == []
    Watch(ws, listing({CURRENT: (0.5, 2.0)})).run(NOW + timedelta(days=14))  # a fall
    assert today(client, ws) == []
