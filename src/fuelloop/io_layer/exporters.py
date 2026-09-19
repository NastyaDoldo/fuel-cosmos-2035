"""Выгрузка результатов в CSV/XLSX."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _plan_frame(res: dict) -> pd.DataFrame:
    rows = []
    for y, v in res["years"].items():
        rows.append(
            {
                "year": int(y),
                "demand_total_t": v["demand_total"],
                "demand_critical_t": v["demand_critical"],
                "inflow_gross_t": v["inflow_gross"],
                "losses_t": v["losses"],
                "loss_rate": v["loss_rate"],
                "served_t": v["served"],
                "served_critical_t": v["served_critical"],
                "deficit_t": v["deficit"],
                "deficit_critical_t": v["deficit_critical"],
                "service_total": v["service_total"],
                "service_critical": v["service_critical"],
                "stock_start_t": v["stock_start"],
                "stock_end_t": v["stock_end"],
                "stock_min_t": v["stock_min"],
                "stock_max_t": v["stock_max"],
                "storage_capacity_t": v["storage_capacity"],
                "overflow_events": v["overflow_events"],
                "reserve_required_t": v["reserve_required_t"],
                "reserve_cover": v["reserve_cover"],
                "emergency_role": v["emergency_role"],
                "capex_mln": sum(v["capex"].values()),
                "capex_cumulative_mln": v["capex_cumulative"],
                "opex_extra_zbo_mln": v["opex_extra"]["zbo"],
                "opex_extra_isru_mln": v["opex_extra"]["lunar_isru"],
                "variable_cost_mln": v["variable_cost"],
                "reserve_fees_mln": v["reserve_fees"],
                "storage_cost_mln": v["storage_cost"],
                "expenses_operating_mln": v["expenses_operating"],
                "expenses_total_mln": v["expenses_total"],
                "expenses_npv_mln": v["expenses_npv"],
            }
        )
    return pd.DataFrame(rows)


def _channels_frame(res: dict) -> pd.DataFrame:
    rows = []
    for y, v in res["years"].items():
        for cid, c in v["channels"].items():
            rows.append({"year": int(y), "channel": cid, **c})
    return pd.DataFrame(rows)


def _checks_frame(res: dict) -> pd.DataFrame:
    rows = []
    for y, v in res["years"].items():
        for c in v["checks"]:
            rows.append({"year": int(y), **c})
    return pd.DataFrame(rows)


def _kpi_frame(res: dict) -> pd.DataFrame:
    return pd.DataFrame({"metric": list(res["totals"]), "value": list(res["totals"].values())})


def comparison_frame(results_by_scenario: dict) -> pd.DataFrame:
    rows = []
    for sid, res in results_by_scenario.items():
        t = res["totals"]
        rows.append(
            {
                "scenario": sid,
                "expenses_total_mln": round(t["expenses_total"], 2),
                "expenses_npv_mln": round(t["expenses_npv"], 2),
                "capex_total_mln": t["capex_total"],
                "deficit_total_t": round(t["deficit_total"], 2),
                "min_service_total": round(t["min_service_total"], 4),
                "min_service_critical": round(t["min_service_critical"], 4),
                "hard_violations": len(res["violations"]),
                "stress_findings": len(res["stress_findings"]),
            }
        )
    return pd.DataFrame(rows)


def results_to_frames(res: dict) -> dict:
    return {
        "plan": _plan_frame(res),
        "channels": _channels_frame(res),
        "checks": _checks_frame(res),
        "kpi": _kpi_frame(res),
        "assumptions": pd.DataFrame({"assumption": res["assumptions"]}),
    }


def export_plan_snapshot(plan: dict, out_dir: str | Path, sid: str) -> None:
    snap = dict(plan)
    snap["years"] = {str(k): v for k, v in plan["years"].items()}
    with open(Path(out_dir) / f"plan_snapshot_{sid}.json", "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)


def export_all(
    results_by_scenario: dict,
    out_dir: str | Path,
    plans: dict | None = None,
    xlsx_name: str = "fuelloop_results.xlsx",
) -> pd.DataFrame:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frames: dict[str, dict] = {}
    for sid, res in results_by_scenario.items():
        f = results_to_frames(res)
        for name, df in f.items():
            df.to_csv(out / f"{name}_{sid}.csv", index=False, encoding="utf-8-sig")
        if plans and sid in plans:
            export_plan_snapshot(plans[sid], out, sid)
        frames[sid] = f
    comp = comparison_frame(results_by_scenario)
    comp.to_csv(out / "scenario_comparison.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(out / xlsx_name, engine="openpyxl") as xl:
        for sid, f in frames.items():
            for name, df in f.items():
                df.to_excel(xl, sheet_name=f"{name[:18]}_{sid[:10]}", index=False)
        comp.to_excel(xl, sheet_name="comparison", index=False)
    return comp
