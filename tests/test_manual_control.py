"""Независимый ручной контрольный пример (все числа посчитаны вручную)."""

import math

from fuelloop.core.engine import run
from fuelloop.core.loaders import Channel, Dataset


def make_dataset(capacity=120.0):
    return Dataset(
        years=[2035],
        demand={
            2035: {
                "total": 100.0,
                "critical": 80.0,
                "low_total": 80.0,
                "high_total": 110.0,
                "crit_share": 0.8,
            }
        },
        channels={
            "B_earth_flex": Channel(
                id="B_earth_flex",
                name="B Earth-Flex",
                capacity=110.0,
                var_cost=8.9,
                reserve_rate=0.15,
                top_share=0.0,
                lead_time_months=4.0,
                reliability={"default": 0.985},
                start_year=2035,
                requires_investment=None,
                max_consecutive_base_years=None,
            )
        },
        storage={
            "base_storage": {
                "capacity_t": capacity,
                "loss_rate": 0.045,
                "storage_cost_mln_per_t_year": 0.72,
            },
            "zbo": {
                "capex_mln": 180.0,
                "available_from": 2036,
                "lead_years": 1.0,
                "capacity_after_t": 120.0,
                "loss_rate_after": 0.012,
                "extra_opex_mln_per_year": 12.0,
            },
        },
        investments={
            "lunar_isru": {
                "capex_total_mln": 1250.0,
                "funding_deadline_year": 2037,
                "start_year": 2038,
                "extra_opex_mln_per_year": 70.0,
            },
            "earth_new": {
                "option_fee_mln": 90.0,
                "exercise_mln": 270.0,
                "lead_time_months": 24,
                "capacity_t_per_year": 130.0,
            },
        },
        constraints={
            "steps_per_year": 1,
            "days_per_year": 365,
            "discount_rate_real": 0.10,
            "reserve_days": 45,
            "min_service_critical": 0.99,
            "min_service_total": 0.97,
            "capex_limit_by_2037_mln": 1800.0,
            "capex_limit_total_mln": 2800.0,
            "emergency_max_consecutive_years": 2,
            "emergency_activation_days": 42,
            "serving_policy": "critical_first",
        },
    )


def make_plan(volume=0.0, ordered=100.0):
    return {
        "plan_id": "manual",
        "initial_stock": {"volume_t": volume, "source_channel": "B_earth_flex", "payment_time": 0.0},
        "years": {
            2035: {
                "channels": {"B_earth_flex": {"reserved_t": 100.0, "ordered_t": ordered}},
                "investments": {},
            }
        },
    }


def test_manual_control_single_step():
    ds = make_dataset()
    res = run(ds, make_plan(volume=0.0, ordered=100.0))
    y = res["years"]["2035"]

    inflow = 100.0
    losses = inflow * 0.045
    available = inflow - losses

    assert math.isclose(y["inflow_gross"], 100.0)
    assert math.isclose(y["losses"], 4.5)
    assert math.isclose(y["served"], 95.5)
    assert math.isclose(y["deficit"], 4.5)
    assert math.isclose(y["stock_end"], 0.0)

    assert math.isclose(y["service_total"], 0.955)
    assert math.isclose(y["service_critical"], 1.0)
    assert math.isclose(y["served_critical"], 80.0)

    var = 8.9 * max(100.0, 0.0)
    res_pay = 0.15 * 100.0
    avg_stock = available**2 / (2.0 * 100.0)
    storage = 0.72 * avg_stock

    assert math.isclose(y["channels"]["B_earth_flex"]["variable_payment"], var)
    assert math.isclose(y["channels"]["B_earth_flex"]["reserve_payment"], res_pay)
    assert math.isclose(y["storage_cost"], storage)
    assert math.isclose(y["expenses_total"], var + res_pay + storage)

    expected_npv = (var + res_pay + storage) / 1.1**0.5
    assert math.isclose(y["expenses_npv"], expected_npv)

    reserve_check = next(c for c in y["checks"] if c["check"] == "reserve_45d")
    assert reserve_check["ok"] is False
    assert math.isclose(reserve_check["limit"], 100.0 * 45 / 365, abs_tol=1e-6)


def test_manual_control_with_initial_stock():
    ds = make_dataset()
    res = run(ds, make_plan(volume=10.0, ordered=100.0))
    y = res["years"]["2035"]

    assert math.isclose(y["losses"], 4.5)
    assert math.isclose(y["served"], 100.0)
    assert math.isclose(y["deficit"], 0.0)
    assert math.isclose(y["stock_end"], 5.5)

    avg_stock = (10.0 + 100.0 - 4.5) - 50.0
    storage = 0.72 * avg_stock
    assert math.isclose(y["storage_cost"], storage)

    total = 890.0 + 15.0 + storage
    assert math.isclose(y["expenses_total"], total)

    init_cost = 10.0 * 8.9
    assert math.isclose(res["totals"]["initial_stock_cost"], init_cost)
    expected_npv = init_cost + total / 1.1**0.5
    assert math.isclose(res["totals"]["expenses_npv"], expected_npv)
