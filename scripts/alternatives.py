import copy
import sys

sys.stdout.reconfigure(encoding="utf-8")

from fuelloop.core import apply_scenario, load_dataset, load_plan, load_scenarios, run


def main():
    ds = load_dataset("data")
    scens = load_scenarios("configs/scenarios.json")
    plan = load_plan("configs/plan_standard.json")

    variants = {"baseline (A+B-буфер+ISRU+ZBO)": plan}

    no_isru = copy.deepcopy(plan)
    for y in no_isru["years"].values():
        y["channels"].pop("D_lunar_isru", None)
        y["investments"]["isru_pay_mln"] = 0
    variants["alt1 без ISRU (только A+B)"] = no_isru

    no_zbo = copy.deepcopy(plan)
    no_zbo["years"][2036]["investments"]["zbo_pay_mln"] = 0
    variants["alt2 без ZBO"] = no_zbo

    with_c = copy.deepcopy(plan)
    for y, yv in with_c["years"].items():
        if "D_lunar_isru" in yv["channels"]:
            d = yv["channels"].pop("D_lunar_isru")
            yv["channels"]["C_earth_new"] = {"reserved_t": d["reserved_t"], "ordered_t": d["ordered_t"]}
        yv["investments"]["isru_pay_mln"] = 0
    with_c["years"][2035]["investments"]["earth_new_option_mln"] = 90
    with_c["years"][2036]["investments"]["earth_new_exercise_mln"] = 270
    variants["alt3 Earth-New (C) вместо ISRU"] = with_c

    for sid in ("standard", "stress"):
        print(f"--- {sid} ---")
        for name, p in variants.items():
            r = run(apply_scenario(ds, scens[sid], sid), p)
            t = r["totals"]
            print(
                f"{name:38s} NPV={t['expenses_npv']:8.1f} capex={t['capex_total']:6.0f} "
                f"minSVC={t['min_service_total']:.3f} crit={t['min_service_critical']:.3f} "
                f"deficit={t['deficit_total']:6.1f} viol={len(r['violations'])}"
            )


if __name__ == "__main__":
    main()
