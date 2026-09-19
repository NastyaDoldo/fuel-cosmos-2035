"""Рабочее место оператора: Streamlit-интерфейс над расчётным ядром.

Запуск: streamlit run src/fuelloop/app/dashboard.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

ROOT = Path(__file__).resolve().parents[3]

import pandas as pd
import streamlit as st

from fuelloop.core import apply_scenario, load_dataset, load_plan, load_scenarios, run
from fuelloop.core.risks import build_risk_register, monte_carlo, sensitivity_analysis
from fuelloop.io_layer.exporters import comparison_frame, results_to_frames

st.set_page_config(page_title="Топливный космоконтур 2035", page_icon="🛰", layout="wide")


@st.cache_data(show_spinner=False)
def _load_data(data_dir: str):
    return load_dataset(data_dir)


@st.cache_data(show_spinner=False)
def _load_scenarios(cfg_dir: str):
    return load_scenarios(Path(cfg_dir) / "scenarios.json")


@st.cache_data(show_spinner=False)
def _default_plan(cfg_dir: str):
    return load_plan(Path(cfg_dir) / "plan_standard.json")


ds = _load_data(str(ROOT / "data"))
scens = _load_scenarios(str(ROOT / "configs"))
base_plan = _default_plan(str(ROOT / "configs"))

st.title("Топливный космоконтур 2035")
st.caption("Планирование снабжения орбитального топливного узла, 2035–2040. "
           "Ядро считает все цифры; интерфейс задаёт решения.")


def edit_plan() -> dict:
    plan = {
        "plan_id": "ui_plan",
        "description": "План, собранный в интерфейсе",
        "initial_stock": dict(base_plan.get("initial_stock", {})),
        "years": {},
    }
    with st.expander("Начальный запас (45-дневный резерв к 2035)", expanded=False):
        c1, c2 = st.columns([1, 2])
        vol = c1.number_input(
            "Объём, т", 0.0, 200.0,
            float(base_plan["initial_stock"].get("volume_t", 0.0)), 0.01, key="is_vol")
        src_default = base_plan["initial_stock"].get("source_channel", "B_earth_flex")
        src = c2.selectbox("Источник закупки", list(ds.channels),
                           index=list(ds.channels).index(src_default)
                           if src_default in ds.channels else 0, key="is_src")
        plan["initial_stock"] = {
            "volume_t": vol,
            "source_channel": src,
            "delivery_date": base_plan["initial_stock"].get("delivery_date", "2034-12-20"),
            "payment_time": 0.0,
        }
    for y in ds.years:
        py = base_plan["years"].get(y, {})
        with st.expander(f"Год {y}", expanded=(y == ds.years[0])):
            st.markdown("**Каналы: резерв мощности / заказанный отбор, т**")
            chs = {}
            cols = st.columns(len(ds.channels))
            for k, (cid, ch) in enumerate(ds.channels.items()):
                cur = py.get("channels", {}).get(cid, {})
                with cols[k]:
                    st.caption(f"{ch.name} (до {ch.capacity:.0f} т)")
                    r = st.number_input("резерв", 0.0, ch.capacity * 1.5,
                                        float(cur.get("reserved_t", 0.0)), 1.0,
                                        key=f"{y}_{cid}_r", label_visibility="collapsed")
                    o = st.number_input("отбор", 0.0, ch.capacity * 1.5,
                                        float(cur.get("ordered_t", 0.0)), 1.0,
                                        key=f"{y}_{cid}_o", label_visibility="collapsed")
                    chs[cid] = {"reserved_t": r, "ordered_t": o}
            chs = {cid: v for cid, v in chs.items() if v["reserved_t"] > 0 or v["ordered_t"] > 0}
            st.markdown("**Инвестиции в этом году, млн у.е.**")
            inv = py.get("investments", {})
            i1, i2, i3, i4 = st.columns(4)
            z = i1.number_input("ZBO CAPEX", 0.0, 500.0, float(inv.get("zbo_pay_mln", 0.0)), 10.0, key=f"{y}_zbo")
            isr = i2.number_input("ISRU CAPEX", 0.0, 1500.0, float(inv.get("isru_pay_mln", 0.0)), 25.0, key=f"{y}_isru")
            ef = i3.number_input("Earth-New: право", 0.0, 200.0, float(inv.get("earth_new_option_mln", 0.0)), 10.0, key=f"{y}_enf")
            ex = i4.number_input("Earth-New: реализация", 0.0, 400.0, float(inv.get("earth_new_exercise_mln", 0.0)), 10.0, key=f"{y}_ex")
            plan["years"][y] = {
                "channels": chs,
                "investments": {"zbo_pay_mln": z, "isru_pay_mln": isr,
                                "earth_new_option_mln": ef, "earth_new_exercise_mln": ex},
            }
    return plan


with st.sidebar:
    st.header("Управление")
    scenario_ids = st.multiselect(
        "Сценарии для расчёта и сравнения",
        list(scens), default=["standard", "stress"],
        help="standard и stress — обязательные; остальные исследовательские")
    st.divider()
    st.subheader("Доп. анализы")
    do_sens = st.checkbox("Чувствительность", value=False)
    do_mc = st.checkbox("Монте-Карло (n=1000)", value=False)
    do_risks = st.checkbox("Реестр рисков", value=True)
    st.divider()
    run_btn = st.button("▶ Пересчитать", type="primary", use_container_width=True)
    st.caption("Все расчёты выполняет ядро fuelloop.core. "
               "Изменения сценария применяются к копии данных.")

plan = edit_plan()

results: dict[str, dict] = {}
if run_btn or "results" not in st.session_state:
    with st.spinner("Расчёт ядра..."):
        for sid in (scenario_ids or ["standard"]):
            results[sid] = run(apply_scenario(ds, scens[sid], sid), plan)
    st.session_state["results"] = results
    st.session_state["plan"] = plan
results = st.session_state.get("results", {})
plan_used = st.session_state.get("plan", plan)

if not results:
    st.info("Задайте план слева/выше и нажмите «Пересчитать».")
    st.stop()

tab_overview, tab_scen, tab_checks, tab_risks, tab_export = st.tabs(
    ["Обзор", "Сценарии", "Проверки", "Риски и анализы", "Экспорт"])


def pick(tab_key: str) -> tuple[str, dict]:
    primary = "stress" if "stress" in results else next(iter(results))
    sel = st.selectbox(
        "Сценарий в этой вкладке",
        list(results),
        index=list(results).index(primary),
        key=f"pick_{tab_key}",
    )
    return sel, results[sel]


with tab_overview:
    sel, res = pick("overview")
    t = res["totals"]
    m = st.columns(6)
    m[0].metric("NPV расходов, млн", f"{t['expenses_npv']:.0f}")
    m[1].metric("Расходы всего, млн", f"{t['expenses_total']:.0f}")
    m[2].metric("CAPEX, млн", f"{t['capex_total']:.0f}")
    m[3].metric("Мин. обслуживание (общ.)", f"{t['min_service_total']:.1%}")
    m[4].metric("Мин. обслуживание (крит.)", f"{t['min_service_critical']:.1%}")
    m[5].metric("Дефицит, т", f"{t['deficit_total']:.1f}")

    frames = results_to_frames(res)
    pdf = frames["plan"].set_index("year")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Запас на конец года, т")
        st.line_chart(pdf[["stock_end_t", "reserve_required_t", "storage_capacity_t"]])
    with c2:
        st.subheader("Спрос vs отбор, т")
        st.bar_chart(pdf[["demand_total_t", "served_t", "inflow_gross_t"]])
    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Расходы по годам, млн")
        st.bar_chart(pdf[["variable_cost_mln", "reserve_fees_mln", "storage_cost_mln",
                          "opex_extra_zbo_mln", "opex_extra_isru_mln", "capex_mln"]])
    with c4:
        st.subheader("Обслуживание спроса, %")
        st.line_chart(pdf[["service_total", "service_critical"]])
    st.subheader("План по годам")
    st.dataframe(frames["plan"], use_container_width=True)
    with st.expander("Поставки по каналам"):
        st.dataframe(frames["channels"], use_container_width=True)

with tab_scen:
    st.subheader("Сравнение сценариев (одна база данных, один план)")
    st.dataframe(comparison_frame(results), use_container_width=True)
    st.caption("Стресс: +15% спрос (2038–2040), +25% цены A/B (2038–2039), "
               "фактические доли ISRU 55/75/100%, предел потерь 2%. "
               "99%/97% в стрессе — ориентиры устойчивости; дефицит показывается честно.")

with tab_checks:
    sel, res = pick("checks")
    st.subheader(f"Проверки ограничений — {sel}")
    chf = results_to_frames(res)["checks"]
    bad = chf[~chf["ok"]]
    st.markdown(f"**Нарушения/отклонения: {len(bad)}**")
    st.dataframe(bad if len(bad) else chf[chf["ok"]].head(20), use_container_width=True)
    with st.expander("Все проверки"):
        st.dataframe(chf, use_container_width=True)
    if res["violations"]:
        st.error("План содержит жёсткие нарушения — см. таблицу выше (kind=hard).")
    elif res["stress_findings"]:
        st.warning("В стрессе есть отклонения от ориентиров (kind=target) — дефицит показан без корректировок задним числом.")
    else:
        st.success("Все проверки пройдены.")

with tab_risks:
    st.subheader("Реестр рисков")
    if do_risks:
        reg = build_risk_register(ds, plan_used, results)
        st.dataframe(reg, use_container_width=True)
    st.subheader("Чувствительность (один фактор за раз)")
    if do_sens:
        base_sid = list(results)[0]
        sens = sensitivity_analysis(ds, plan_used, scens[base_sid], base_sid)
        st.dataframe(sens, use_container_width=True)
    else:
        st.caption("Включите галочку «Чувствительность» в панели слева и пересчитайте.")
    st.subheader("Монте-Карло")
    if do_mc:
        with st.spinner("Монте-Карло: 1000 прогонов..."):
            base_sid = list(results)[0]
            mc = monte_carlo(ds, plan_used, scens[base_sid], base_sid, n=1000, seed=42)
        mc_m = st.columns(4)
        mc_m[0].metric("P(дефицит > 0)", f"{mc['p_deficit_positive']:.1%}")
        mc_m[1].metric("P(общ. < 97%)", f"{mc['p_service_total_below_097']:.1%}")
        mc_m[2].metric("P(крит. < 99%)", f"{mc['p_service_critical_below_099']:.1%}")
        mc_m[3].metric("NPV p90, млн", f"{mc['npv_p90']:.0f}")
        st.caption(mc["distributions"] + f" | n={mc['n']}, seed={mc['seed']}")
    else:
        st.caption("Включите галочку «Монте-Карло» в панели слева и пересчитайте.")

with tab_export:
    st.subheader("Выгрузка результатов")
    frames_all = {sid: results_to_frames(r) for sid, r in results.items()}
    for sid, f in frames_all.items():
        for name, df in f.items():
            csv_bytes = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(f"{name}_{sid}.csv", csv_bytes, f"{name}_{sid}.csv", "text/csv",
                               key=f"dl_{name}_{sid}")
    comp = comparison_frame(results)
    st.download_button("scenario_comparison.csv",
                       comp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                       "scenario_comparison.csv", "text/csv", key="dl_comp")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        for sid, f in frames_all.items():
            for name, df in f.items():
                df.to_excel(xl, sheet_name=f"{name[:18]}_{sid[:10]}", index=False)
        comp.to_excel(xl, sheet_name="comparison", index=False)
    st.download_button("Полный отчёт XLSX", buf.getvalue(), "fuelloop_results.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key="dl_xlsx")
    plan_json = json.dumps({**plan_used, "years": {str(k): v for k, v in plan_used["years"].items()}},
                           ensure_ascii=False, indent=2)
    st.download_button("План (JSON)", plan_json.encode("utf-8"), "plan_saved.json",
                       "application/json", key="dl_plan")
    st.caption("Снимки плана и все CSV также доступны в папке results/ после запуска CLI.")
