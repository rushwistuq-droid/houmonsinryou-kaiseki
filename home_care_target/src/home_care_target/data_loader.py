"""公的統計・JMAP由来データの読み込み."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"


@lru_cache(maxsize=1)
def load_constants() -> Dict[str, Any]:
    return json.loads((DATA_DIR / "mhlw_constants.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_prefecture_clinics() -> Dict[str, Any]:
    return json.loads(
        (DATA_DIR / "prefecture_home_support_clinics.json").read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def load_city_clinics() -> Dict[str, Any]:
    return json.loads(
        (DATA_DIR / "city_home_support_clinics.json").read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def load_secondary_clinics() -> Dict[str, Any]:
    return json.loads(
        (DATA_DIR / "secondary_home_support_clinics.json").read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def load_municipal_facilities() -> Dict[str, Any]:
    return json.loads(
        (DATA_DIR / "municipal_home_support_facilities.json").read_text(encoding="utf-8")
    )


def get_prefecture_clinic_stats(pref_name: str) -> Optional[Dict[str, Any]]:
    return load_prefecture_clinics().get(pref_name)


def get_secondary_clinic_stats(code_or_name: str) -> Optional[Dict[str, Any]]:
    data = load_secondary_clinics()
    if code_or_name in data:
        return data[code_or_name]
    for rec in data.values():
        if rec.get("name") == code_or_name:
            return rec
    return None


def get_municipal_facilities(name: str) -> Optional[Dict[str, Any]]:
    return load_municipal_facilities().get(name)


def avg_patients_per_clinic(rec: Dict[str, Any]) -> Optional[float]:
    clinics = rec.get("home_support_clinics") or 0
    patients = rec.get("patients_managed") or 0
    if clinics <= 0 or patients <= 0:
        return None
    return patients / clinics
