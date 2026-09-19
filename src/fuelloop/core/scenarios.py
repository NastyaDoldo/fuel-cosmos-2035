"""Сценарный слой: применение изменений на копии набора данных."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .loaders import Dataset


def load_scenarios(path: str | Path) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def apply_scenario(dataset: Dataset, scenario: dict, scenario_id: str = "") -> Dataset:
    ds = copy.deepcopy(dataset)
    variant = scenario.get("base_demand_variant", "base")
    for y in ds.years:
        d = ds.demand[y]
        if variant == "low":
            d["total"] = d["low_total"]
        elif variant == "high":
            d["total"] = d["high_total"]
        d["critical"] = d["crit_share"] * d["total"]

    changes = scenario.get("changes", [])
    for chg in changes:
        ctype = chg.get("type")
        if ctype == "demand_multiplier":
            for y in chg["years"]:
                ds.demand[y]["total"] *= chg["value"]
                ds.demand[y]["critical"] *= chg["value"]
        elif ctype == "price_multiplier":
            for cid in chg["channels"]:
                if cid not in ds.channels:
                    raise ValueError(f"price_multiplier: неизвестный канал {cid}")
                for y in chg["years"]:
                    cur = ds.price_mult.get(cid, {}).get(y, 1.0)
                    ds.price_mult.setdefault(cid, {})[y] = cur * chg["value"]
        elif ctype == "isru_actual_share":
            ds.isru_share.update({int(k): float(v) for k, v in chg["shares_by_year"].items()})
        elif ctype == "loss_rate_cap":
            for y in chg["years"]:
                ds.loss_cap[int(y)] = float(chg["value"])
        elif ctype == "channel_disable":
            for y in chg["years"]:
                ds.disabled.setdefault(chg["channel"], {})[int(y)] = True
        elif ctype == "demand_override":
            for y in chg["years"]:
                if "total" in chg:
                    ds.demand[y]["total"] = float(chg["total"])
                if "critical" in chg:
                    ds.demand[y]["critical"] = float(chg["critical"])
        else:
            raise ValueError(f"Неизвестный тип изменения сценария: {ctype}")

    ds.scenario_id = scenario_id
    ds.scenario_kind = scenario.get("kind") or ("standard" if not changes else "custom")
    return ds
