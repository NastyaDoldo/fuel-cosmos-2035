"""Стандартный сценарий и обязательный стресс-тест на одном плане."""

import math
from pathlib import Path

from fuelloop.core.engine import load_plan, run
from fuelloop.core.loaders import load_dataset
from fuelloop.core.scenarios import apply_scenario, load_scenarios

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIGS = ROOT / "configs"


def setup():
    ds = load_dataset(DATA)
    scens = load_scenarios(CONFIGS / "scenarios.json")
    plan = load_plan(CONFIGS / "plan_standard.json")
    return ds, scens, plan


def test_standard_scenario_feasible():
    ds, scens, plan = setup()
    res = run(apply_scenario(ds, scens["standard"], "standard"), plan)
    assert res["violations"] == [], f"нарушения: {res['violations']}"
    for y, v in res["years"].items():
        assert v["deficit"] == 0.0, y
        assert math.isclose(v["service_total"], 1.0)
        assert math.isclose(v["service_critical"], 1.0)
        assert v["reserve_cover"] in ("physical_stock", "emergency_contract")
        assert v["overflow_events"] == 0
    assert res["totals"]["capex_total"] <= 2800.0


def test_stress_scenario_changes_applied():
    ds, scens, plan = setup()
    res = run(apply_scenario(ds, scens["stress"], "stress"), plan)
    y38 = res["years"]["2038"]
    assert y38["demand_total"] == 287.5
    assert math.isclose(y38["demand_critical"], 195.5)
    a = y38["channels"]["A_earth_core"]
    assert a["price_mln_per_t"] == 7.75
    assert a["variable_payment"] == 7.75 * 190
    d = y38["channels"]["D_lunar_isru"]
    assert d["inflow_t"] == 33.0
    assert d["delivery_share"] == 0.55


def test_stress_no_payment_refund_for_isru():
    ds, scens, plan = setup()
    std = run(apply_scenario(ds, scens["standard"], "standard"), plan)
    strs = run(apply_scenario(ds, scens["stress"], "stress"), plan)
    std_d = std["years"]["2038"]["channels"]["D_lunar_isru"]
    strs_d = strs["years"]["2038"]["channels"]["D_lunar_isru"]
    assert std_d["variable_payment"] == strs_d["variable_payment"] == 180.0
    assert strs_d["inflow_t"] < std_d["inflow_t"]


def test_stress_deficits_shown_not_hidden():
    ds, scens, plan = setup()
    res = run(apply_scenario(ds, scens["stress"], "stress"), plan)
    assert res["years"]["2038"]["deficit"] > 0
    assert res["years"]["2039"]["deficit"] > 0
    assert res["totals"]["min_service_total"] < 0.97
    assert any(c["check"] == "service_total" for c in res["stress_findings"])
    assert res["violations"] == []


def test_stress_reserve_covered_by_emergency_contract_2038():
    ds, scens, plan = setup()
    res = run(apply_scenario(ds, scens["stress"], "stress"), plan)
    v38 = res["years"]["2038"]
    assert v38["reserve_cover"] == "emergency_contract"
    assert v38["emergency_role"] == "reserve"


def test_stress_reserve_depleted_in_late_years_is_reported():
    ds, scens, plan = setup()
    res = run(apply_scenario(ds, scens["stress"], "stress"), plan)
    for y in ("2039", "2040"):
        v = res["years"][y]
        assert v["reserve_cover"] == "insufficient", y
    assert any(c["check"] == "reserve_45d" for c in res["stress_findings"])
    assert all(c["check"] != "reserve_45d" for c in res["violations"])


def test_stress_loss_cap_respected_with_zbo():
    ds, scens, plan = setup()
    res = run(apply_scenario(ds, scens["stress"], "stress"), plan)
    for y in ("2038", "2039", "2040"):
        assert res["years"][y]["loss_rate"] <= 0.02 + 1e-12
        assert all(c["ok"] for c in res["years"][y]["checks"] if c["check"] == "loss_rate_cap")


def test_stress_without_zbo_hits_loss_cap():
    ds, scens, plan = setup()
    plan["years"][2036]["investments"]["zbo_pay_mln"] = 0.0
    res = run(apply_scenario(ds, scens["stress"], "stress"), plan)
    assert any(c["check"] == "loss_rate_cap" for c in res["stress_findings"])


def test_stress_costs_more_than_standard():
    ds, scens, plan = setup()
    std = run(apply_scenario(ds, scens["standard"], "standard"), plan)
    strs = run(apply_scenario(ds, scens["stress"], "stress"), plan)
    assert strs["totals"]["expenses_npv"] > std["totals"]["expenses_npv"]
    assert strs["years"]["2040"]["channels"]["A_earth_core"]["price_mln_per_t"] == 6.2


def test_scenario_application_does_not_mutate_source():
    ds, scens, plan = setup()
    before = ds.demand[2038]["total"]
    apply_scenario(ds, scens["stress"], "stress")
    assert ds.demand[2038]["total"] == before == 250.0
    assert ds.scenario_kind == "standard"
