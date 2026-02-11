from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import httpx

from .config import Config


@dataclass(frozen=True)
class Record:
    timestamp: str
    submitter_user_id: str
    submitter_username: str
    segment: str
    jenis_order: str
    bobot: float
    service_number: str
    wo_number: str
    ticket_id: str
    tanggal_open: str
    tanggal_close: str
    teknisi_1: str
    teknisi_2: str
    workzone: str
    keterangan: str


def _post(config: Config, payload: dict) -> dict:
    with httpx.Client(timeout=20) as client:
        resp = client.post(config.gs_webapp_url, json=payload)
        resp.raise_for_status()
        return resp.json()


def append_record(config: Config, record: Record) -> None:
    payload = {
        "action": "append_record",
        "data": {
            "timestamp": record.timestamp,
            "submitter_user_id": record.submitter_user_id,
            "submitter_username": record.submitter_username,
            "segment": record.segment,
            "jenis_order": record.jenis_order,
            "bobot": record.bobot,
            "service_number": record.service_number,
            "wo_number": record.wo_number,
            "ticket_id": record.ticket_id,
            "tanggal_open": record.tanggal_open,
            "tanggal_close": record.tanggal_close,
            "teknisi_1": record.teknisi_1,
            "teknisi_2": record.teknisi_2,
            "workzone": record.workzone,
            "keterangan": record.keterangan,
        },
    }
    _post(config, payload)


def set_user_mapping(config: Config, user_id: str, username: str, teknisi_name: str) -> None:
    payload = {
        "action": "set_user_mapping",
        "data": {
            "user_id": user_id,
            "username": username,
            "teknisi_name": teknisi_name,
            "updated_at": datetime.utcnow().isoformat(),
        },
    }
    _post(config, payload)


def get_user_mapping(config: Config, user_id: str) -> Optional[str]:
    payload = {"action": "get_user_mapping", "data": {"user_id": user_id}}
    result = _post(config, payload)
    if result.get("ok") and result.get("data"):
        return result["data"].get("teknisi_name") or None
    return None


def get_all_records(config: Config) -> List[dict]:
    payload = {"action": "get_all_records"}
    result = _post(config, payload)
    return result.get("data", [])
