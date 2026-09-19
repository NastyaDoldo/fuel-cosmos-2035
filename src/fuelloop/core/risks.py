"""Реестр рисков, анализ чувствительности, Монте-Карло (seeded)."""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from .engine import run
from .scenarios import apply_scenario

RISK_COLUMNS = [
    "id",
    "risk",
    "channel",
    "year",
    "probability",
    "impact_t",
    "impact_mln",
    "severity",
    "mitigation",
    "interests",
]


def _replacement_price(ds) -> float:
    return ds.channels["E_emergency"].var_cost if "E_emergency" in ds.channels else max(
        ch.var_cost for ch in ds.channels.values()
    )


def build_risk_register(ds, plan, results_by_scenario: dict) -> pd.DataFrame:
    std = results_by_scenario.get("standard")
    strs = results_by_scenario.get("stress")
    custom = results_by_scenario.get("custom_geopolitics")
    repl = _replacement_price(ds)

    d38_ordered = 0.0
    if std:
        d38_ordered = std["years"]["2038"]["channels"].get("D_lunar_isru", {}).get("ordered_t", 0.0)
    npv_std = std["totals"]["expenses_npv"] if std else 0.0
    npv_str = strs["totals"]["expenses_npv"] if strs else 0.0
    def_2038 = strs["years"]["2038"]["deficit"] if strs else 0.0
    def_2039 = strs["years"]["2039"]["deficit"] if strs else 0.0
    throughput_2037_2040 = sum(v["inflow_gross"] for y, v in std["years"].items() if y >= "2037") if std else 0.0
    cum_capex_2037 = std["years"]["2037"]["capex_cumulative"] if std else 0.0

    rows = [
        {
            "id": "R1",
            "risk": "Недопоставка Lunar-ISRU в первый год эксплуатации (надёжность 0.78)",
            "channel": "D_lunar_isru",
            "year": "2038",
            "probability": 0.22,
            "impact_t": round(d38_ordered * 0.22, 2),
            "impact_mln": round(d38_ordered * 0.22 * (repl - 3.0), 1),
            "severity": "средняя",
            "mitigation": "Законтрактованный резерв E на 2038; поэтапный ввод мощностей ISRU; буферный запас 2037",
            "interests": "Оператор узла / лунный оператор ISRU",
        },
        {
            "id": "R2",
            "risk": "Шок недопоставки ISRU в стрессе (55%/75% плана в 2038-2039)",
            "channel": "D_lunar_isru",
            "year": "2038-2039",
            "probability": 1.0,
            "impact_t": round(def_2038 + def_2039, 2),
            "impact_mln": round((def_2038 + def_2039) * repl, 1),
            "severity": "высокая",
            "mitigation": "Опцион на доп. объёмы B/E с 2038; ранний ввод ZBO; критический спрос обслуживается первым (policy critical_first)",
            "interests": "Оператор узла / потребители топлива на орбите",
        },
        {
            "id": "R3",
            "risk": "Удорожание Earth-Core/Earth-Flex (+25% в 2038-2039, геополитика/инфляция)",
            "channel": "A_earth_core, B_earth_flex",
            "year": "2038-2039",
            "probability": 0.30,
            "impact_mln": round(max(0.0, npv_str - npv_std), 1),
            "impact_t": 0.0,
            "severity": "средняя",
            "mitigation": "Долгосрочный контракт A с фиксацией формулы цены; частичная переориентация на ISRU",
            "interests": "Оператор узла / земные поставщики",
        },
        {
            "id": "R4",
            "risk": "Задержка/отказ ZBO-модернизации: потери остаются 4.5% вместо 1.2%",
            "channel": "Хранилище",
            "year": "2037-2040",
            "probability": 0.15,
            "impact_t": round(throughput_2037_2040 * 0.033, 2),
            "impact_mln": round(throughput_2037_2040 * 0.033 * 6.5, 1),
            "severity": "средняя",
            "mitigation": "Финансирование ZBO в 2036 с годовым резервом; приёмочные испытания до пика спроса",
            "interests": "Оператор узла / подрядчик модернизации",
        },
        {
            "id": "R5",
            "risk": "Перерасход CAPEX Lunar-ISRU (+20%)",
            "channel": "D_lunar_isru",
            "year": "2035-2037",
            "probability": 0.20,
            "impact_mln": 250.0,
            "impact_t": 0.0,
            "severity": "средняя",
            "mitigation": "Поэтапное финансирование с контрольными точками; запас лимита 1800: израсходовано "
            + f"{cum_capex_2037:.0f} млн к 2037",
            "interests": "Оператор узла / инвесторы / государство",
        },
        {
            "id": "R6",
            "risk": "Невозможность использовать E как базовый канал более 2 лет подряд (контрактное ограничение)",
            "channel": "E_emergency",
            "year": "все",
            "probability": 0.10,
            "impact_t": 160.0,
            "impact_mln": round(160.0 * repl, 1),
            "severity": "низкая",
            "mitigation": "E только как резерв/авария; развитие C/D как альтернативных мощностей",
            "interests": "Оператор узла / аварийный поставщик E",
        },
        {
            "id": "R7",
            "risk": "Геополитическое отключение канала A в 2037-2038",
            "channel": "A_earth_core",
            "year": "2037-2038",
            "probability": 0.10,
            "impact_mln": round(max(0.0, custom["totals"]["expenses_npv"] - npv_std), 1) if custom else 0.0,
            "impact_t": round(custom["totals"]["deficit_total"], 1) if custom else 0.0,
            "severity": "высокая",
            "mitigation": "Диверсификация: C (после опциона), D ISRU, резерв E; сценарий custom_geopolitics в модели",
            "interests": "Оператор узла / государство / поставщик A",
        },
        {
            "id": "R8",
            "risk": "Переполнение хранилища 70 т до ZBO при сгущении поставок",
            "channel": "Хранилище",
            "year": "2035-2036",
            "probability": 0.10,
            "impact_t": 0.0,
            "impact_mln": 25.0,
            "severity": "низкая",
            "mitigation": "Помесячное сглаживание графика поставок; контроль post_receipt_peak в ядре; ZBO 120 т с 2037",
            "interests": "Оператор узла",
        },
    ]
    return pd.DataFrame(rows, columns=RISK_COLUMNS)


OVERRIDE_KEY = {
    "demand_multiplier": "demand_mult",
    "price_mult_A_B": "price_mult_ab",
    "discount_rate": "discount_rate",
    "isru_capex_mln": "isru_capex",
}


def run_with_overrides(ds, plan, scenario, sid: str, overrides: dict) -> dict:
    ds2 = copy.deepcopy(ds)
    if "demand_mult" in overrides:
        m = overrides["demand_mult"]
        for y in ds2.years:
            ds2.demand[y]["total"] *= m
            ds2.demand[y]["critical"] *= m
    if "price_mult_ab" in overrides:
        for cid in ("A_earth_core", "B_earth_flex"):
            if cid in ds2.channels:
                for y in ds2.years:
                    ds2.price_mult.setdefault(cid, {})[y] = overrides["price_mult_ab"]
    if "discount_rate" in overrides:
        ds2.constraints = dict(ds2.constraints)
        ds2.constraints["discount_rate_real"] = overrides["discount_rate"]
    if "isru_capex" in overrides:
        ds2.investments = copy.deepcopy(ds2.investments)
        ds2.investments["lunar_isru"]["capex_total_mln"] = overrides["isru_capex"]
    return run(apply_scenario(ds2, scenario, sid), plan)


def sensitivity_analysis(ds, plan, scenario, sid: str = "standard") -> pd.DataFrame:
    grids = {
        "demand_multiplier": [0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2],
        "price_mult_A_B": [0.8, 0.9, 1.0, 1.25, 1.4],
        "discount_rate": [0.06, 0.08, 0.10, 0.12, 0.14],
        "isru_capex_mln": [1000.0, 1250.0, 1500.0],
    }
    rows = []
    for param, values in grids.items():
        key = OVERRIDE_KEY[param]
        for v in values:
            r = run_with_overrides(ds, plan, scenario, f"{sid}_sens", {key: v})
            rows.append(
                {
                    "parameter": param,
                    "value": v,
                    "npv_mln": round(r["totals"]["expenses_npv"], 1),
                    "min_service_total": round(r["totals"]["min_service_total"], 4),
                    "min_service_critical": round(r["totals"]["min_service_critical"], 4),
                    "hard_violations": len(r["violations"]),
                    "breaks_constraints": "да" if r["violations"] else "нет",
                }
            )
    return pd.DataFrame(rows)


def monte_carlo(ds, plan, scenario, sid: str = "standard", n: int = 1000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    base_shares = {}
    for chg in scenario.get("changes", []):
        if chg.get("type") == "isru_actual_share":
            base_shares = {int(k): float(v) for k, v in chg["shares_by_year"].items()}

    deficits = []
    npvs = []
    svc_t = []
    svc_c = []
    for _ in range(n):
        dem_f = max(0.8, float(rng.normal(1.0, 0.06)))
        shares = {}
        for y in ds.years:
            base = base_shares.get(y, 1.0)
            lo = max(0.3, base - 0.25)
            hi = min(1.05, base + 0.10)
            shares[str(y)] = float(rng.triangular(lo, base, hi))
        sc = copy.deepcopy(scenario)
        changes = list(sc.get("changes", []))
        changes.append({"type": "demand_multiplier", "years": list(ds.years), "value": dem_f})
        changes.append({"type": "isru_actual_share", "shares_by_year": shares})
        if sc.get("kind") != "stress":
            p = float(rng.uniform(1.0, 1.25))
            changes.append(
                {
                    "type": "price_multiplier",
                    "channels": ["A_earth_core", "B_earth_flex"],
                    "years": [2038, 2039],
                    "value": p,
                }
            )
        sc["changes"] = changes
        r = run(apply_scenario(ds, sc, f"{sid}_mc"), plan)
        deficits.append(r["totals"]["deficit_total"])
        npvs.append(r["totals"]["expenses_npv"])
        svc_t.append(r["totals"]["min_service_total"])
        svc_c.append(r["totals"]["min_service_critical"])

    deficits_a = np.array(deficits)
    npvs_a = np.array(npvs)
    svc_t_a = np.array(svc_t)
    svc_c_a = np.array(svc_c)
    return {
        "n": n,
        "seed": seed,
        "distributions": "спрос N(1.0, 0.06) с обрезкой >=0.8; доля ISRU triangular(base-0.25, base, base+0.10); цены A/B в стандартном сценарии U(1.0, 1.25) в 2038-2039",
        "p_deficit_positive": float((deficits_a > 1e-9).mean()),
        "p_service_total_below_097": float((svc_t_a < 0.97).mean()),
        "p_service_critical_below_099": float((svc_c_a < 0.99).mean()),
        "deficit_p50": float(np.percentile(deficits_a, 50)),
        "deficit_p90": float(np.percentile(deficits_a, 90)),
        "deficit_p99": float(np.percentile(deficits_a, 99)),
        "npv_p50": float(np.percentile(npvs_a, 50)),
        "npv_p90": float(np.percentile(npvs_a, 90)),
        "npv_p99": float(np.percentile(npvs_a, 99)),
    }
