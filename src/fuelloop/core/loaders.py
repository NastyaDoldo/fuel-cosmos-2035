"""Загрузка и валидация входных данных (data layer)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Channel:
    id: str
    name: str
    capacity: float
    var_cost: float
    reserve_rate: float
    top_share: float
    lead_time_months: float
    reliability: dict
    start_year: int
    requires_investment: str | None
    max_consecutive_base_years: int | None
    note: str = ""


@dataclass
class Dataset:
    years: list[int]
    demand: dict
    channels: dict
    storage: dict
    investments: dict
    constraints: dict
    price_mult: dict = field(default_factory=dict)
    isru_share: dict = field(default_factory=dict)
    loss_cap: dict = field(default_factory=dict)
    disabled: dict = field(default_factory=dict)
    scenario_id: str = ""
    scenario_kind: str = "standard"

    def price(self, channel_id: str, year: int) -> float:
        ch = self.channels[channel_id]
        mult = self.price_mult.get(channel_id, {}).get(year, 1.0)
        return ch.var_cost * mult

    def is_disabled(self, channel_id: str, year: int) -> bool:
        return bool(self.disabled.get(channel_id, {}).get(year, False))


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _validate(ds: Dataset) -> None:
    for y in ds.years:
        d = ds.demand[y]
        if d["critical"] > d["total"] + 1e-9:
            raise ValueError(f"{y}: критический спрос {d['critical']} больше общего {d['total']}")
        for key in ("low_total", "high_total"):
            if d[key] < 0:
                raise ValueError(f"{y}: отрицательный спрос {key}")
    for cid, ch in ds.channels.items():
        if ch.capacity <= 0:
            raise ValueError(f"{cid}: мощность должна быть положительной")
        if ch.var_cost < 0 or ch.reserve_rate < 0:
            raise ValueError(f"{cid}: отрицательная стоимость/тариф резерва")
        if not 0.0 <= ch.top_share <= 1.0:
            raise ValueError(f"{cid}: take-or-pay доля вне [0,1]")
        if ch.start_year not in ds.years:
            raise ValueError(f"{cid}: start_year {ch.start_year} вне горизонта {ds.years}")
    loss = ds.storage["base_storage"]["loss_rate"]
    if not 0.0 <= loss < 1.0:
        raise ValueError(f"loss_rate хранилища вне [0,1): {loss}")
    for key in ("min_service_critical", "min_service_total"):
        v = ds.constraints.get(key, 0)
        if not 0.0 < v <= 1.0:
            raise ValueError(f"{key} вне (0,1]: {v}")
    if ds.constraints.get("steps_per_year", 1) < 1:
        raise ValueError("steps_per_year должен быть >= 1")


def load_dataset(data_dir: str | Path) -> Dataset:
    p = Path(data_dir)
    demand: dict[int, dict] = {}
    with open(p / "demand.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            y = int(row["year"])
            total = float(row["base_total"])
            crit = float(row["base_critical"])
            demand[y] = {
                "total": total,
                "critical": crit,
                "low_total": float(row["low_total"]),
                "high_total": float(row["high_total"]),
                "crit_share": crit / total if total > 0 else 0.0,
            }
    if not demand:
        raise ValueError("demand.csv пуст")

    channels: dict[str, Channel] = {}
    for cid, c in _read_json(p / "channels.json").items():
        channels[cid] = Channel(
            id=cid,
            name=c["name"],
            capacity=float(c["capacity_t_per_year"]),
            var_cost=float(c["var_cost_mln_per_t"]),
            reserve_rate=float(c["reserve_rate_mln_per_t"]),
            top_share=float(c["take_or_pay_share"]),
            lead_time_months=float(c["lead_time_months"]),
            reliability=dict(c.get("reliability_by_year", {})),
            start_year=int(c["start_year"]),
            requires_investment=c.get("requires_investment"),
            max_consecutive_base_years=c.get("max_consecutive_base_years"),
            note=c.get("note", ""),
        )

    ds = Dataset(
        years=sorted(demand),
        demand=demand,
        channels=channels,
        storage=_read_json(p / "storage.json"),
        investments=_read_json(p / "investments.json"),
        constraints=_read_json(p / "constraints.json"),
    )
    _validate(ds)
    return ds
