"""Реестр рисков, чувствительность, Монте-Карло."""

from pathlib import Path

from fuelloop.core import apply_scenario, load_dataset, load_plan, load_scenarios, run
from fuelloop.core.risks import build_risk_register, monte_carlo, sensitivity_analysis

ROOT = Path(__file__).resolve().parents[1]


def _setup():
    ds = load_dataset(ROOT / "data")
    scens = load_scenarios(ROOT / "configs" / "scenarios.json")
    plan = load_plan(ROOT / "configs" / "plan_standard.json")
    results = {
        sid: run(apply_scenario(ds, scens[sid], sid), plan) for sid in ("standard", "stress")
    }
    return ds, scens, plan, results


def test_risk_register():
    ds, _, plan, results = _setup()
    reg = build_risk_register(ds, plan, results)
    assert len(reg) == 8
    assert list(reg["id"]) == [f"R{i}" for i in range(1, 9)]
    assert (reg["probability"] >= 0).all()
    assert reg["mitigation"].str.len().min() > 10
    r3 = reg.loc[reg["id"] == "R3"].iloc[0]
    assert r3["impact_mln"] > 0


def test_sensitivity():
    ds, scens, plan, _ = _setup()
    sens = sensitivity_analysis(ds, plan, scens["standard"], "standard")
    assert len(sens) == 7 + 5 + 5 + 3
    base = sens[(sens["parameter"] == "demand_multiplier") & (sens["value"] == 1.0)].iloc[0]
    assert base["hard_violations"] == 0
    high = sens[(sens["parameter"] == "demand_multiplier") & (sens["value"] == 1.2)].iloc[0]
    assert high["breaks_constraints"] == "да"
    disc = sens[sens["parameter"] == "discount_rate"]
    assert disc["npv_mln"].is_monotonic_decreasing


def test_monte_carlo_seeded():
    ds, scens, plan, _ = _setup()
    mc1 = monte_carlo(ds, plan, scens["standard"], "standard", n=60, seed=42)
    mc2 = monte_carlo(ds, plan, scens["standard"], "standard", n=60, seed=42)
    assert mc1 == mc2
    assert mc1["n"] == 60 and mc1["seed"] == 42
    assert 0.0 <= mc1["p_deficit_positive"] <= 1.0
    assert mc1["npv_p90"] >= mc1["npv_p50"]
    assert mc1["deficit_p90"] >= mc1["deficit_p50"]
