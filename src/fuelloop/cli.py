"""CLI: прогон сценариев, выгрузка результатов, риски, чувствительность, Монте-Карло."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fuelloop.core import (  # noqa: E402
    apply_scenario,
    load_dataset,
    load_plan,
    load_scenarios,
    run,
)
from fuelloop.core.risks import build_risk_register, monte_carlo, sensitivity_analysis  # noqa: E402
from fuelloop.io_layer.exporters import export_all  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fuelloop", description="Топливный космоконтур 2035")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="Прогнать сценарии и выгрузить результаты")
    r.add_argument("--data", default="data")
    r.add_argument("--configs", default="configs")
    r.add_argument("--out", default="results")
    r.add_argument("--plan", default=None, help="Путь к JSON плана (по умолчанию configs/plan_standard.json)")
    r.add_argument("--scenarios", default="standard,stress", help="Список id сценариев через запятую")
    r.add_argument("--risks", action="store_true", help="Реестр рисков")
    r.add_argument("--sensitivity", action="store_true", help="Анализ чувствительности")
    r.add_argument("--monte-carlo", action="store_true", help="Монте-Карло (n=1000, seed=42)")
    args = p.parse_args(argv)

    ds = load_dataset(args.data)
    scens = load_scenarios(Path(args.configs) / "scenarios.json")
    plan_path = Path(args.plan) if args.plan else Path(args.configs) / "plan_standard.json"
    plan = load_plan(plan_path)

    results = {}
    plans = {}
    for sid in [s.strip() for s in args.scenarios.split(",") if s.strip()]:
        if sid not in scens:
            raise SystemExit(f"Сценарий '{sid}' не найден в {args.configs}/scenarios.json")
        results[sid] = run(apply_scenario(ds, scens[sid], sid), plan)
        plans[sid] = plan

    comp = export_all(results, args.out, plans=plans)
    print("=== Сравнение сценариев ===")
    print(comp.to_string(index=False))

    out = Path(args.out)
    if args.risks:
        reg = build_risk_register(ds, plan, results)
        reg.to_csv(out / "risk_register.csv", index=False, encoding="utf-8-sig")
        print(f"Реестр рисков: {out / 'risk_register.csv'} ({len(reg)} рисков)")
    if args.sensitivity:
        base_sid = args.scenarios.split(",")[0].strip()
        sens = sensitivity_analysis(ds, plan, scens[base_sid], base_sid)
        sens.to_csv(out / f"sensitivity_{base_sid}.csv", index=False, encoding="utf-8-sig")
        print(f"Чувствительность: {out / f'sensitivity_{base_sid}.csv'} ({len(sens)} строк)")
    if args.monte_carlo:
        base_sid = args.scenarios.split(",")[0].strip()
        mc = monte_carlo(ds, plan, scens[base_sid], base_sid, n=1000, seed=42)
        import json

        with open(out / f"monte_carlo_{base_sid}.json", "w", encoding="utf-8") as f:
            json.dump(mc, f, ensure_ascii=False, indent=2)
        print(f"Монте-Карло: {out / f'monte_carlo_{base_sid}.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
