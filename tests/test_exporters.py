"""Проверка выгрузок CSV/XLSX."""

from pathlib import Path

from fuelloop.core import apply_scenario, load_dataset, load_plan, load_scenarios, run
from fuelloop.io_layer.exporters import export_all, results_to_frames

ROOT = Path(__file__).resolve().parents[1]


def _std_results():
    ds = load_dataset(ROOT / "data")
    scens = load_scenarios(ROOT / "configs" / "scenarios.json")
    plan = load_plan(ROOT / "configs" / "plan_standard.json")
    return ds, scens, plan, run(apply_scenario(ds, scens["standard"], "standard"), plan)


def test_frames_complete():
    _, _, _, res = _std_results()
    frames = results_to_frames(res)
    assert set(frames) == {"plan", "channels", "checks", "kpi", "assumptions"}
    assert len(frames["plan"]) == 6
    assert len(frames["channels"]) > 0
    assert len(frames["assumptions"]) == len(res["assumptions"])


def test_export_csv_xlsx(tmp_path):
    ds, scens, plan, std = _std_results()
    strs = run(apply_scenario(ds, scens["stress"], "stress"), plan)
    comp = export_all({"standard": std, "stress": strs}, tmp_path, plans={"standard": plan})
    assert len(comp) == 2
    for name in (
        "plan_standard.csv",
        "plan_stress.csv",
        "checks_stress.csv",
        "kpi_standard.csv",
        "scenario_comparison.csv",
        "fuelloop_results.xlsx",
        "plan_snapshot_standard.json",
    ):
        assert (tmp_path / name).exists(), name
    assert (tmp_path / "fuelloop_results.xlsx").stat().st_size > 5000
