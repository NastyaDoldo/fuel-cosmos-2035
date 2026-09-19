import sys

sys.stdout.reconfigure(encoding="utf-8")

from fuelloop.core import apply_scenario, load_dataset, load_plan, load_scenarios, run


def main():
    ds = load_dataset("data")
    scens = load_scenarios("configs/scenarios.json")
    plan = load_plan("configs/plan_standard.json")
    std = run(apply_scenario(ds, scens["standard"], "standard"), plan)
    strs = run(apply_scenario(ds, scens["stress"], "stress"), plan)
    for name, r in (("STANDARD", std), ("STRESS", strs)):
        t = r["totals"]
        print(
            f"{name}: NPV={t['expenses_npv']:.1f} total={t['expenses_total']:.1f} "
            f"capex={t['capex_total']:.0f} minSVC={t['min_service_total']:.3f} "
            f"minSVCcrit={t['min_service_critical']:.3f} deficit={t['deficit_total']:.1f} "
            f"viol={len(r['violations'])} findings={len(r['stress_findings'])}"
        )
        for y, v in r["years"].items():
            print(
                f"  {y}: demand={v['demand_total']:.1f} served={v['served']:.1f} "
                f"losses={v['losses']:.2f} stockEnd={v['stock_end']:.2f} "
                f"exp={v['expenses_total']:.0f} svc={v['service_total']:.3f}"
            )


if __name__ == "__main__":
    main()
