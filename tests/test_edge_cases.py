"""Граничные значения: нулевой спрос, нулевой запас, превышение мощности, переполнение."""

import copy

from tests.test_manual_control import make_dataset, make_plan

from fuelloop.core.engine import run


def test_zero_demand():
    ds = make_dataset()
    ds.demand[2035]["total"] = 0.0
    ds.demand[2035]["critical"] = 0.0
    ds.demand[2035]["crit_share"] = 0.0
    plan = make_plan(volume=0.0, ordered=0.0)
    res = run(ds, plan)
    y = res["years"]["2035"]
    assert y["served"] == 0.0
    assert y["deficit"] == 0.0
    assert y["service_total"] == 1.0
    assert y["storage_cost"] == 0.0
    rc = next(c for c in y["checks"] if c["check"] == "reserve_45d")
    assert rc["ok"] is True
    assert rc["limit"] == 0.0


def test_zero_stock_no_orders():
    ds = make_dataset()
    plan = make_plan(volume=0.0, ordered=0.0)
    res = run(ds, plan)
    y = res["years"]["2035"]
    assert y["served"] == 0.0
    assert y["deficit"] == 100.0
    assert y["stock_end"] == 0.0
    assert y["service_total"] == 0.0
    checks = {c["check"]: c for c in y["checks"]}
    assert checks["service_total"]["ok"] is False
    assert checks["reserve_45d"]["ok"] is False
    assert res["violations"]


def test_ordered_exceeds_capacity_clamped():
    ds = make_dataset()
    ds.channels["A_test"] = copy.deepcopy(ds.channels["B_earth_flex"])
    ds.channels["A_test"].id = "A_test"
    ds.channels["A_test"].capacity = 190.0
    plan = make_plan(volume=0.0, ordered=0.0)
    plan["years"][2035]["channels"] = {"A_test": {"reserved_t": 250.0, "ordered_t": 250.0}}
    res = run(ds, plan)
    y = res["years"]["2035"]
    assert y["channels"]["A_test"]["ordered_t"] == 190.0
    assert y["inflow_gross"] == 190.0
    assert any(c["check"] == "ordered_exceeds_capacity" for c in res["violations"])


def test_storage_overflow_flagged_not_clamped():
    ds = make_dataset(capacity=70.0)
    ds.demand[2035]["total"] = 0.0
    ds.demand[2035]["critical"] = 0.0
    plan = make_plan(volume=65.0, ordered=50.0)
    res = run(ds, plan)
    y = res["years"]["2035"]
    expected_post = 65.0 + 50.0 * 0.955
    assert y["overflow_events"] == 1
    assert abs(y["overflow_max"] - (expected_post - 70.0)) < 1e-9
    assert y["stock_end"] == expected_post
    assert any(c["check"] == "storage_capacity" and not c["ok"] for c in res["violations"])


def test_stock_never_negative():
    ds = make_dataset()
    plan = make_plan(volume=0.0, ordered=10.0)
    res = run(ds, plan)
    y = res["years"]["2035"]
    assert y["served"] == 9.55
    assert y["stock_end"] == 0.0
    assert y["deficit"] == 90.45
