"""Оркестратор расчёта: план оператора x сценарий -> результаты по годам."""

from __future__ import annotations

import json
import math
from pathlib import Path

from .balance import run_balance
from .economics import channel_variable_payment, npv, reserve_payment
from .scenarios import Dataset

CAPEX_LIMIT_YEAR = 2037

ASSUMPTIONS = [
    "Временной шаг: помесячно (12 шагов/год, 365 дней), спрос равномерный, поступления в начале шага",
    "Потери = валовый приток (throughput) x коэффициент действующего хранилища, начисляются один раз при поступлении",
    "В стандартном сценарии поставки приходят по плану; надёжность НЕ умножается на объёмы (учтена в реестре рисков)",
    "Дефицит распределяется по политике critical_first: критический спрос обслуживается первым",
    "Начальный запас: явная закупка по цене канала-источника, оплата в t=0, в CAPEX не входит",
    "Хранение: 0.72 млн у.е./т-год x средневзвешенный по времени физический запас",
    "Переменный платёж = цена x max(отбор, доля take-or-pay x зарезервированный объём периода)",
    "Резервный платёж = тариф x зарезервированная мощность периода (отдельно от переменного платежа)",
    "Take-or-pay не прибавляется повторно к уже оплаченному минимуму",
    "В стрессе недопоставка ISRU не возвращает платежей",
    "OPEX ZBO/ISRU начисляется с полного года после ввода",
    "NPV расходов: реальная ставка, операционные потоки и CAPEX дисконтируются на середину года платежа",
]


def load_plan(path: str | Path) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        plan = json.load(f)
    plan["years"] = {int(k): v for k, v in plan["years"].items()}
    return plan


def _check(name, ok, value, limit, note="", kind="hard"):
    return {
        "check": name,
        "ok": bool(ok),
        "value": round(float(value), 6),
        "limit": limit,
        "kind": kind,
        "note": note,
    }


def _service(served: float, demand: float) -> float:
    return 1.0 if demand <= 1e-12 else served / demand


def run(ds: Dataset, plan: dict) -> dict:
    cons = ds.constraints
    steps = int(cons.get("steps_per_year", 12))
    days = float(cons.get("days_per_year", 365))
    disc = float(cons.get("discount_rate_real", 0.10))
    reserve_days = float(cons.get("reserve_days", 45))
    em_max = int(cons.get("emergency_max_consecutive_years", 2))
    em_activation = float(cons.get("emergency_activation_days", 42))
    policy = cons.get("serving_policy", "critical_first")
    min_total = float(cons.get("min_service_total", 0.97))
    min_crit = float(cons.get("min_service_critical", 0.99))
    capex_lim_1 = float(cons.get("capex_limit_by_2037_mln", 1800.0))
    capex_lim_total = float(cons.get("capex_limit_total_mln", 2800.0))

    base_st = ds.storage["base_storage"]
    zbo = ds.storage["zbo"]
    isru_inv = ds.investments["lunar_isru"]
    service_kind = "target" if ds.scenario_kind == "stress" else "hard"
    t0 = ds.years[0]

    em_cid = next(
        (cid for cid, ch in ds.channels.items() if ch.max_consecutive_base_years is not None),
        None,
    )

    init = plan.get("initial_stock", {})
    init_volume = float(init.get("volume_t", 0.0))
    init_src = init.get("source_channel")
    init_cost = init_volume * ds.price(init_src, ds.years[0]) if init_src and init_volume > 0 else 0.0
    flows: list[tuple[float, float]] = [(float(init.get("payment_time", 0.0)), init_cost)]

    stock = init_volume
    years_out: dict[int, dict] = {}
    all_checks: list[dict] = []
    cum_capex = 0.0
    em_run = 0
    isru_funded = 0.0
    zbo_pay_year = None
    en_fee_year = None
    en_ex_year = None

    for y in ds.years:
        py = plan["years"].get(y, {})
        ch_plan = py.get("channels", {})
        inv = py.get("investments", {})
        d = ds.demand[y]
        demand = float(d["total"])
        crit = float(d["critical"])
        checks: list[dict] = []

        zbo_pay = float(inv.get("zbo_pay_mln", 0.0))
        isru_pay = float(inv.get("isru_pay_mln", 0.0))
        en_fee = float(inv.get("earth_new_option_mln", 0.0))
        en_ex = float(inv.get("earth_new_exercise_mln", 0.0))
        if zbo_pay > 0 and zbo_pay_year is None:
            zbo_pay_year = y
        if en_fee > 0 and en_fee_year is None:
            en_fee_year = y
        if en_ex > 0 and en_ex_year is None:
            en_ex_year = y

        zbo_operating = zbo_pay_year is not None and y >= zbo_pay_year + float(zbo["lead_years"])
        loss_rate = zbo["loss_rate_after"] if zbo_operating else base_st["loss_rate"]
        capacity = zbo["capacity_after_t"] if zbo_operating else base_st["capacity_t"]
        cap_y = ds.loss_cap.get(y)
        loss_rate_eff = min(loss_rate, cap_y) if cap_y is not None else loss_rate
        if cap_y is not None and loss_rate > cap_y + 1e-12:
            checks.append(
                _check("loss_rate_cap", False, loss_rate, cap_y,
                       "режим потерь действующего хранилища выше предела сценария", "target")
            )

        isru_operating = isru_funded >= isru_inv["capex_total_mln"] - 1e-9 and y >= isru_inv["start_year"]

        def available(cid: str) -> tuple[bool, str]:
            ch = ds.channels[cid]
            if ds.is_disabled(cid, y):
                return False, "channel_disabled"
            if y < ch.start_year:
                return False, "before_start_year"
            req = ch.requires_investment
            if req == "lunar_isru":
                if y < isru_inv["start_year"]:
                    return False, "isru_not_commissioned"
                if not isru_operating:
                    return False, "isru_not_funded"
            if req == "earth_new":
                if en_fee_year is None or en_ex_year is None or en_fee_year > en_ex_year:
                    return False, "earth_new_not_purchased"
                if y < en_ex_year + math.ceil(ch.lead_time_months / 12):
                    return False, "earth_new_not_ready"
            return True, ""

        lines: dict[str, dict] = {}
        inflow_total = 0.0
        var_total = 0.0
        res_total = 0.0
        em_reserved = 0.0
        em_ordered = False

        for cid, cp in ch_plan.items():
            ch = ds.channels[cid]
            reserved = float(cp.get("reserved_t", 0.0))
            ordered = float(cp.get("ordered_t", 0.0))
            ok, reason = available(cid)
            if not ok:
                checks.append(_check("channel_availability", False, ordered, 0.0, f"{cid}: {reason}"))
                ordered = 0.0
                reserved = 0.0
            if ordered > ch.capacity + 1e-9:
                checks.append(_check("ordered_exceeds_capacity", False, ordered, ch.capacity, cid))
                ordered = ch.capacity
            share = ds.isru_share.get(y, 1.0) if ch.requires_investment == "lunar_isru" else 1.0
            inflow = ordered * share
            price = ds.price(cid, y)
            var_pay = channel_variable_payment(price, ordered, ch.top_share, reserved)
            res_pay = reserve_payment(ch.reserve_rate, reserved)
            lines[cid] = {
                "reserved_t": reserved,
                "ordered_t": ordered,
                "inflow_t": inflow,
                "price_mln_per_t": price,
                "variable_payment": var_pay,
                "reserve_payment": res_pay,
                "available": ok,
                "delivery_share": share,
            }
            inflow_total += inflow
            var_total += var_pay
            res_total += res_pay
            if cid == em_cid:
                em_reserved = reserved
                em_ordered = ordered > 1e-12

        if em_ordered:
            em_run += 1
        else:
            em_run = 0
        if em_run > em_max:
            checks.append(_check("emergency_consecutive_years", False, em_run, em_max, f"{em_cid} как базовый канал"))

        bal = run_balance(stock, inflow_total, loss_rate_eff, demand, capacity, steps, days)
        storage_cost = base_st["storage_cost_mln_per_t_year"] * bal["stock_days_sum"] / days

        served = bal["served"]
        deficit = bal["deficit"]
        if policy == "proportional" or demand <= 1e-12:
            served_crit = crit * _service(served, demand)
        else:
            served_crit = min(crit, served)
        service_total = _service(served, demand)
        service_crit = _service(served_crit, crit)
        deficit_crit = crit - served_crit

        reserve_required = demand * reserve_days / days
        shortfall = reserve_required - stock
        if stock >= reserve_required - 1e-9:
            reserve_ok, cover = True, "physical_stock"
        elif em_reserved >= shortfall - 1e-9 and em_activation <= reserve_days:
            reserve_ok, cover = True, "emergency_contract"
        else:
            reserve_ok, cover = False, "insufficient"
        checks.append(
            _check("reserve_45d", reserve_ok, stock, round(reserve_required, 6), cover, service_kind)
        )
        checks.append(
            _check("service_total", service_total >= min_total - 1e-9, service_total, min_total, "", service_kind)
        )
        checks.append(
            _check("service_critical", service_crit >= min_crit - 1e-9, service_crit, min_crit, "", service_kind)
        )
        checks.append(
            _check("storage_capacity", bal["overflow_events"] == 0, bal["post_receipt_peak"], capacity,
                   f"overflow_events={bal['overflow_events']}")
        )

        capex_lines = {
            "zbo": zbo_pay,
            "lunar_isru": isru_pay,
            "earth_new_option": en_fee,
            "earth_new_exercise": en_ex,
        }
        capex_year = sum(capex_lines.values())
        cum_capex += capex_year
        if y <= isru_inv["funding_deadline_year"]:
            isru_funded += isru_pay
        capex_limit = capex_lim_1 if y <= CAPEX_LIMIT_YEAR else capex_lim_total
        checks.append(_check("capex_cumulative", cum_capex <= capex_limit + 1e-6, cum_capex, capex_limit))

        opex_zbo = zbo["extra_opex_mln_per_year"] if zbo_operating else 0.0
        opex_isru = isru_inv["extra_opex_mln_per_year"] if isru_operating else 0.0
        operating_cost = var_total + res_total + storage_cost + opex_zbo + opex_isru
        expenses = operating_cost + capex_year
        t_flow = y - t0 + 0.5
        flows.append((t_flow, operating_cost))
        flows.append((t_flow, capex_year))

        if em_ordered:
            em_role = "base"
        elif em_reserved > 0:
            em_role = "reserve"
        else:
            em_role = "none"

        years_out[y] = {
            "demand_total": demand,
            "demand_critical": crit,
            "reserve_required_t": reserve_required,
            "channels": lines,
            "inflow_gross": inflow_total,
            "losses": bal["losses"],
            "loss_rate": loss_rate_eff,
            "served": served,
            "served_critical": served_crit,
            "deficit": deficit,
            "deficit_critical": deficit_crit,
            "service_total": service_total,
            "service_critical": service_crit,
            "stock_start": stock,
            "stock_end": bal["stock_end"],
            "stock_min": bal["stock_min"],
            "stock_max": bal["stock_max"],
            "storage_capacity": capacity,
            "overflow_events": bal["overflow_events"],
            "overflow_max": bal["overflow_max"],
            "reserve_cover": cover,
            "emergency_role": em_role,
            "emergency_consecutive": em_run,
            "capex": capex_lines,
            "capex_cumulative": cum_capex,
            "opex_extra": {"zbo": opex_zbo, "lunar_isru": opex_isru},
            "variable_cost": var_total,
            "reserve_fees": res_total,
            "storage_cost": storage_cost,
            "expenses_operating": operating_cost,
            "expenses_total": expenses,
            "expenses_npv": npv([(t_flow, expenses)], disc),
            "checks": checks,
        }
        all_checks.extend(checks)
        stock = bal["stock_end"]

    totals = {
        "expenses_total": sum(a for _, a in flows),
        "expenses_npv": npv(flows, disc),
        "initial_stock_cost": init_cost,
        "capex_total": cum_capex,
        "fuel_variable_total": sum(v["variable_cost"] for v in years_out.values()),
        "reserve_fees_total": sum(v["reserve_fees"] for v in years_out.values()),
        "storage_cost_total": sum(v["storage_cost"] for v in years_out.values()),
        "opex_extra_total": sum(
            v["opex_extra"]["zbo"] + v["opex_extra"]["lunar_isru"] for v in years_out.values()
        ),
        "losses_total": sum(v["losses"] for v in years_out.values()),
        "deficit_total": sum(v["deficit"] for v in years_out.values()),
        "min_service_total": min(v["service_total"] for v in years_out.values()),
        "min_service_critical": min(v["service_critical"] for v in years_out.values()),
    }

    violations = [c for c in all_checks if c["kind"] == "hard" and not c["ok"]]
    findings = [c for c in all_checks if c["kind"] == "target" and not c["ok"]]

    return {
        "scenario_id": ds.scenario_id,
        "scenario_kind": ds.scenario_kind,
        "plan_id": plan.get("plan_id", ""),
        "years": {str(k): v for k, v in years_out.items()},
        "totals": totals,
        "violations": violations,
        "stress_findings": findings,
        "assumptions": ASSUMPTIONS,
    }
