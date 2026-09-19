"""Заведомо невыполнимые планы должны помечаться как невыполнимые."""

import copy
from pathlib import Path

from fuelloop.core.engine import load_plan, run
from fuelloop.core.loaders import load_dataset
from fuelloop.core.scenarios import apply_scenario, load_scenarios

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIGS = ROOT / "configs"


def baseline():
    ds = load_dataset(DATA)
    scen = load_scenarios(CONFIGS / "scenarios.json")["standard"]
    plan = load_plan(CONFIGS / "plan_standard.json")
    return ds, scen, plan


def test_emergency_more_than_two_consecutive_years():
    ds, scen, plan = baseline()
    for y in (2035, 2036, 2037):
        plan["years"][y]["channels"]["E_emergency"] = {"reserved_t": 20.0, "ordered_t": 20.0}
    res = run(apply_scenario(ds, scen, "standard"), plan)
    em = [c for c in res["violations"] if c["check"] == "emergency_consecutive_years"]
    assert em, "план с E 3 года подряд должен быть невыполнимым"
    assert em[0]["value"] == 3


def test_capex_limit_breach():
    ds, scen, plan = baseline()
    plan["years"][2036]["investments"]["zbo_pay_mln"] = 2000.0
    res = run(apply_scenario(ds, scen, "standard"), plan)
    capex = [c for c in res["violations"] if c["check"] == "capex_cumulative"]
    assert capex, "CAPEX 2000 в 2036 должен нарушить лимит 1800"
    assert any(c["value"] > 1800.0 for c in capex)


def test_isru_without_financing():
    ds, scen, plan = baseline()
    plan["years"][2036]["investments"]["isru_pay_mln"] = 0.0
    plan["years"][2037]["investments"]["isru_pay_mln"] = 0.0
    res = run(apply_scenario(ds, scen, "standard"), plan)
    av = [c for c in res["violations"] if c["check"] == "channel_availability"]
    assert av, "ISRU без финансирования должен быть недоступен"
    assert all("isru_not_funded" in c["note"] for c in av)
    y2038 = res["years"]["2038"]
    assert y2038["channels"]["D_lunar_isru"]["inflow_t"] == 0.0
    assert y2038["service_total"] < 0.97


def test_empty_plan_marked_infeasible():
    ds, scen, plan = baseline()
    empty = copy.deepcopy(plan)
    for y in empty["years"]:
        empty["years"][y]["channels"] = {}
        empty["years"][y]["investments"] = {}
    res = run(apply_scenario(ds, scen, "standard"), empty)
    checks = {c["check"] for c in res["violations"]}
    assert "service_total" in checks
    assert "service_critical" in checks
    assert "reserve_45d" in checks


def test_channel_before_availability():
    ds, scen, plan = baseline()
    plan["years"][2035]["channels"]["D_lunar_isru"] = {"reserved_t": 50.0, "ordered_t": 50.0}
    res = run(apply_scenario(ds, scen, "standard"), plan)
    av = [c for c in res["violations"] if c["check"] == "channel_availability"]
    assert av and "before_start_year" in av[0]["note"]
    assert res["years"]["2035"]["channels"]["D_lunar_isru"]["inflow_t"] == 0.0
