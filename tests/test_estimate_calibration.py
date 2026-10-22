"""Estimates learn from use (design 6.16): how an account's model counts tokens, compared with the app's own count, is
measured at the account check (one count of a fixed sample, for an adapter that can count; a command-line program's
fixed overhead per request from the check's own small call), kept on this computer, corrected by every run that reports
its input tokens, and used by every estimate of a price. Accounts and prices come from tests/fixtures/ai/ai.yaml; the
adapters are small fakes, so nothing touches a network."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from engine.ai import calibration
from engine.ai.adapters import ADAPTERS
from engine.ai.adapters.cli_agent import CliAgentAdapter
from engine.ai.calibration import (
    Calibration,
    estimate_tokens,
    learn_from_run,
    lookup,
    measured,
    record_check,
    record_overhead,
    scaled,
    tokens_for,
)
from engine.ai.check_cost import CALL_INPUT_TOKENS, cost
from engine.ai.checked import Folder, remember
from engine.ai.router import Router
from engine.ai.smoke import account_test
from engine.ai.task import AiResult, AiTask, CountNotOffered
from engine.config import load_config
from engine.config.schema import ProviderSettings
from engine.storage import Store

AI_CONFIG = Path(__file__).parent / "fixtures" / "ai"
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
ENV = {"MAIN_KEY": "main-secret", "BACKUP_KEY": "backup-secret"}
ACCOUNT, MODEL = "main", "main-small"
OVERHEAD = 12_000


def task_of(chars: int) -> AiTask:
    """A task whose packet is exactly this many characters."""
    return AiTask(kind="notes", instructions="", stable="", request="x" * chars, output_schema={}, expected_output=100)


SMALL, LARGE = task_of(40), task_of(4000)


class Account:
    """A fake adapter. `counts`: the real tokens it reports for a request as a multiple of the app's own count (None:
    it has no count request). `reads`: the input tokens its answers report, as a multiple of the app's own count plus
    `extra` (None: it reports nothing)."""

    def __init__(self, counts=None, reads=None, extra=0, overhead=False):
        if counts is not None:
            self.count_tokens = lambda task, model: round(estimate_tokens(task.size) * counts)
        if overhead:
            self.adds_overhead = True
        self.reads, self.extra = reads, extra

    def run(self, task, model):
        tokens = None if self.reads is None else round(estimate_tokens(task.size) * self.reads) + self.extra
        return AiResult(text='{"ok": true}', model_served=model, seconds=0.0, input_tokens=tokens, output_tokens=5)


@pytest.fixture
def cfg():
    return load_config(AI_CONFIG, env={})


@pytest.fixture
def where(tmp_path):
    return Folder(tmp_path / ".cockpit")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "ai.db")
    yield s
    s.close()


def checked(cfg, where, adapter):
    """The account check as Settings runs it, and what it kept."""
    results = account_test(cfg, ENV, ACCOUNT, lambda name, settings, secret: adapter)
    remember(where, cfg, results)
    return results


def router_on(cfg, store, adapter):
    class NoCatalog:
        def model(self, provider, model_id, fetch):
            return None

    return Router(cfg, store, env=ENV, adapter_factory=lambda n, s, k: adapter, now=lambda: NOW, catalogs=NoCatalog())


def where_of(store):
    return Folder(store.path.parent / ".cockpit")


# ---- the account check ----------------------------------------------------------------------------------------------


def test_an_account_that_counts_gets_the_ratio_of_real_tokens_to_the_apps_own_count_at_its_check(cfg, where):
    results = checked(cfg, where, Account(counts=1.5))
    part = next(r for r in results if r.part == "calibration")
    assert part.ok and "counted a sample" in part.detail
    found = lookup(where, ACCOUNT, MODEL)
    assert found.ratio == pytest.approx(1.5, abs=0.01)
    assert found.overhead == 0
    assert measured(where, ACCOUNT)["models"][MODEL]["measured_at"], "when it was measured is kept"


def test_an_account_that_cannot_count_and_reports_nothing_starts_at_ratio_one_and_no_overhead(cfg, where):
    results = checked(cfg, where, Account())
    part = next(r for r in results if r.part == "calibration")
    assert part.ok and "doesn't count" in part.detail
    assert lookup(where, ACCOUNT, MODEL) == Calibration(1.0, 0)
    assert tokens_for(400, lookup(where, ACCOUNT, MODEL)) == estimate_tokens(400)


def test_an_account_that_reports_tokens_but_adds_nothing_of_its_own_gets_no_overhead_from_its_check(cfg, where):
    checked(cfg, where, Account(reads=3.0))
    assert lookup(where, ACCOUNT, MODEL).overhead == 0


def test_the_native_adapter_counts_through_its_service_and_its_check_keeps_the_ratio(cfg, where):
    address = cfg.ai.providers[ACCOUNT].base_url
    # The native adapter is the one whose service lists each model's capabilities.
    name, native_class = next((n, c) for n, c in ADAPTERS.items() if getattr(c, "reads_capabilities", False))
    settings = ProviderSettings(adapter=name, base_url=address, models={"small": MODEL})

    # The service counts three times what the app's own count of the request would be.
    def count(request):
        text = json.loads(request.content)["messages"][0]["content"]
        return httpx.Response(200, json={"input_tokens": 3 * estimate_tokens(len(text))})

    counted = httpx.MockTransport(count)
    native = native_class(settings, "k", transport=counted)

    class Native(Account):
        count_tokens = native.count_tokens

    results = checked(cfg, where, Native())
    part = next(r for r in results if r.part == "calibration")
    assert part.ok
    assert lookup(where, ACCOUNT, MODEL).ratio > 1.0


def test_an_adapter_without_a_count_says_it_isnt_offered_and_the_check_still_passes(cfg, where):
    class Uncounted(Account):
        def count_tokens(self, task, model):
            raise CountNotOffered("not offered")

    results = checked(cfg, where, Uncounted())
    part = next(r for r in results if r.part == "calibration")
    assert part.ok and "isn't offered" in part.detail
    assert lookup(where, ACCOUNT, MODEL).ratio == 1.0


def test_a_command_line_agents_fixed_overhead_is_what_its_check_call_reported_less_what_its_text_counts(cfg, where):
    assert CliAgentAdapter.adds_overhead is True
    results = checked(cfg, where, Account(reads=1.0, extra=OVERHEAD, overhead=True))
    part = next(r for r in results if r.part == "calibration")
    assert "fixed overhead" in part.detail
    found = lookup(where, ACCOUNT, MODEL)
    assert found.overhead == OVERHEAD
    assert found.ratio == 1.0, "an agent that can't count keeps ratio 1 until its runs say otherwise"
    assert measured(where, ACCOUNT)["overhead"]["measured_at"]


def test_a_program_that_reports_nothing_at_its_check_has_no_overhead_and_the_check_says_why(cfg, where):
    results = checked(cfg, where, Account(overhead=True))
    part = next(r for r in results if r.part == "calibration")
    assert "no fixed overhead is known" in part.detail
    assert lookup(where, ACCOUNT, MODEL).overhead == 0


def test_a_check_that_found_no_network_measures_nothing(cfg, where):
    results = checked(cfg, where, Account(counts=2.0))
    offline = [r.__class__(**{**r.__dict__, "offline": True}) for r in results]
    other = Folder(where.private_dir.parent / "other" / ".cockpit")
    remember(other, cfg, offline)
    assert lookup(other, ACCOUNT, MODEL) == Calibration()


# ---- corrected from use ---------------------------------------------------------------------------------------------


def test_runs_that_report_tokens_move_the_ratio_and_runs_that_do_not_leave_it(cfg, store):
    where = where_of(store)
    record_check(where, ACCOUNT, MODEL, counted=1000, sample_chars=4000)  # ratio 1
    cfg.ai.estimates.calibration_runs = 2
    cfg.ai.budgets.per_day_usd = 100
    reading = Account(reads=3.0)
    router = router_on(cfg, store, reading)
    router.call(LARGE, request_id="R1")
    assert lookup(where, ACCOUNT, MODEL, 2).ratio == pytest.approx(2.0)  # (1 + 3) / 2: the check and the run
    router.call(LARGE, request_id="R2")
    assert lookup(where, ACCOUNT, MODEL, 2).ratio == pytest.approx(3.0)  # the last two: both runs
    mute = router_on(cfg, store, Account(reads=None))
    mute.call(LARGE, request_id="R3")
    assert lookup(where, ACCOUNT, MODEL, 2).ratio == pytest.approx(3.0), "a run that reported nothing changes nothing"
    reading.reads = 1.0
    router.call(LARGE, request_id="R4")
    assert lookup(where, ACCOUNT, MODEL, 2).ratio == pytest.approx(2.0)  # the last two: 3 and 1
    assert router.calibration(router_choice(router)).ratio == pytest.approx(2.0), "the router reads the setting's runs"


def router_choice(router):
    from engine.ai.router import choices

    return choices(router.cfg, "notes", "internal")[0]


def test_the_agents_overhead_is_taken_off_a_runs_reported_tokens_before_the_ratio_moves(where):
    record_overhead(where, ACCOUNT, reported=OVERHEAD + 10, text_tokens=10)
    ratio = learn_from_run(where, ACCOUNT, MODEL, input_chars=4000, input_tokens=OVERHEAD + 2000)
    assert ratio == pytest.approx(2.0)
    assert lookup(where, ACCOUNT, MODEL).ratio == pytest.approx(2.0)


def test_a_run_whose_ratio_is_out_of_bounds_or_that_reports_nothing_is_not_taken_in(where):
    assert learn_from_run(where, ACCOUNT, MODEL, input_chars=40, input_tokens=100_000) is None
    assert learn_from_run(where, ACCOUNT, MODEL, input_chars=0, input_tokens=100) is None
    assert learn_from_run(where, ACCOUNT, MODEL, input_chars=400, input_tokens=None) is None
    record_overhead(where, ACCOUNT, reported=500, text_tokens=0)
    assert learn_from_run(where, ACCOUNT, MODEL, input_chars=400, input_tokens=400) is None, "less than the overhead"
    assert lookup(where, ACCOUNT, MODEL) == Calibration(1.0, 500)


def test_each_models_ratio_is_kept_apart(where):
    learn_from_run(where, ACCOUNT, "model-a", input_chars=400, input_tokens=200)
    learn_from_run(where, ACCOUNT, "model-b", input_chars=400, input_tokens=50)
    assert lookup(where, ACCOUNT, "model-a").ratio == pytest.approx(2.0)
    assert lookup(where, ACCOUNT, "model-b").ratio == pytest.approx(0.5)
    assert lookup(where, "other", "model-a").ratio == 1.0


# ---- estimates use it -----------------------------------------------------------------------------------------------


def test_the_estimate_of_a_small_run_includes_the_agents_overhead(cfg, store):
    router = router_on(cfg, store, Account())
    bare = router.estimate(SMALL)
    record_overhead(where_of(store), ACCOUNT, reported=OVERHEAD, text_tokens=0)
    assert router.estimate(SMALL) - bare == pytest.approx(OVERHEAD * 1.0 / 1e6)  # the price is $1 per million read
    expected = (tokens_for(SMALL.size, Calibration(1.0, OVERHEAD)) * 1.0 + 100 * 2.0) / 1e6
    assert router.estimate(SMALL) == pytest.approx(expected)


def test_estimates_multiply_by_the_account_models_ratio(cfg, store):
    router = router_on(cfg, store, Account())
    record_check(where_of(store), ACCOUNT, MODEL, counted=2000, sample_chars=4000)  # twice the app's own count
    expected = (estimate_tokens(LARGE.size) * 2 * 1.0 + 100 * 2.0) / 1e6
    assert router.estimate(LARGE) == pytest.approx(expected)
    assert router.estimate_for("notes", 1000, 100) == pytest.approx((2000 * 1.0 + 100 * 2.0) / 1e6)


def test_estimate_for_adds_the_overhead_to_the_callers_token_count(cfg, store):
    router = router_on(cfg, store, Account())
    record_overhead(where_of(store), ACCOUNT, reported=OVERHEAD, text_tokens=0)
    assert router.estimate_for("notes", 10, 0) == pytest.approx((10 + OVERHEAD) * 1.0 / 1e6)


def test_the_cost_of_checking_an_account_counts_the_overhead_and_ratio_of_each_call(cfg, where):
    class NoCatalog:
        def model(self, provider, model_id, fetch):
            return None

    plain = cost(cfg, ACCOUNT, NoCatalog())
    assert cost(cfg, ACCOUNT, NoCatalog(), where) == pytest.approx(plain)  # nothing measured yet
    record_overhead(where, ACCOUNT, reported=OVERHEAD, text_tokens=0)
    from engine.ai.check_cost import size

    calls = size(cfg).calls
    assert cost(cfg, ACCOUNT, NoCatalog(), where) - plain == pytest.approx(calls * OVERHEAD * 1.0 / 1e6)
    assert CALL_INPUT_TOKENS > 0


def test_scaled_and_tokens_for_round_up_and_default_to_the_apps_own_count():
    assert tokens_for(401) == 101 and scaled(101) == 101
    assert tokens_for(400, Calibration(1.5, 7)) == 157
    assert scaled(100, Calibration(1.25, 0)) == 125
    assert scaled(-5, Calibration(2.0, 3)) == 3


# ---- kept values survive a restart ----------------------------------------------------------------------------------


def test_what_was_kept_is_read_back_from_the_private_folder_by_a_fresh_start(cfg, store):
    where = where_of(store)
    record_check(where, ACCOUNT, MODEL, counted=1250, sample_chars=4000, now=NOW)
    record_overhead(where, ACCOUNT, reported=OVERHEAD + 5, text_tokens=5, now=NOW)
    learn_from_run(where, ACCOUNT, MODEL, input_chars=4000, input_tokens=OVERHEAD + 1750, now=NOW)
    kept = json.loads((where.private_dir / calibration.STATE_FILE).read_text(encoding="utf-8"))
    assert kept[ACCOUNT]["overhead"] == {"tokens": OVERHEAD, "measured_at": NOW.isoformat()}
    fresh = router_on(cfg, store, Account())  # a new router and a new folder object: nothing is held in memory
    found = fresh.calibration(router_choice(fresh))
    assert found.overhead == OVERHEAD
    assert found.ratio == pytest.approx((1.25 + 1.75) / 2)


def test_a_damaged_file_reads_as_nothing_measured(where):
    where.private_dir.mkdir(parents=True)
    (where.private_dir / calibration.STATE_FILE).write_text("{not json", encoding="utf-8")
    assert lookup(where, ACCOUNT, MODEL) == Calibration()


def test_the_runs_setting_has_a_default_and_a_description(cfg):
    from engine.config.schema import EstimateSettings

    field = EstimateSettings.model_fields["calibration_runs"]
    assert field.default == 20 and field.description
