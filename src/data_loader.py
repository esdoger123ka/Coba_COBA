from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class OrderItem:
    id: str
    name: str
    weight: float
    segment: str


@dataclass(frozen=True)
class Technician:
    name: str
    unit: str
    labor: str | None


def _read_csv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def _normalize_weight(value: str) -> float:
    if value is None:
        return 0.0
    s = str(value).strip()
    if not s:
        return 0.0
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_orders(data_dir: str) -> Dict[str, List[OrderItem]]:
    orders: Dict[str, List[OrderItem]] = {}
    for name in os.listdir(data_dir):
        if not name.lower().endswith(".csv"):
            continue
        if "teknisi" in name.lower():
            continue
        path = os.path.join(data_dir, name)
        rows = _read_csv(path)
        segment = os.path.splitext(name)[0]
        items: List[OrderItem] = []
        for idx, row in enumerate(rows):
            order_name = (row.get("jenis order") or row.get("JENIS_ORDER") or "").strip()
            if not order_name:
                continue
            weight = _normalize_weight(row.get("bobot", ""))
            item_id = f"{segment}:{idx}"
            items.append(OrderItem(id=item_id, name=order_name, weight=weight, segment=segment))
        if items:
            orders[segment] = items
    return orders


def load_technicians(data_dir: str) -> Tuple[List[Technician], List[str]]:
    tech_file = None
    for name in os.listdir(data_dir):
        if name.lower().endswith(".csv") and "teknisi" in name.lower():
            tech_file = os.path.join(data_dir, name)
            break
    if not tech_file:
        raise FileNotFoundError("Technician CSV not found in data directory")

    rows = _read_csv(tech_file)
    technicians: List[Technician] = []
    units = set()
    for row in rows:
        name = (row.get("NAMA") or row.get("nama") or "").strip()
        if not name:
            continue
        unit = (row.get("UNIT") or row.get("unit") or "").strip()
        labor = (row.get("LABOR") or row.get("labor") or "").strip() or None
        technicians.append(Technician(name=name, unit=unit, labor=labor))
        if unit:
            units.add(unit)
    return technicians, sorted(units)
