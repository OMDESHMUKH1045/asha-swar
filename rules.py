"""Deterministic prototype risk rules. These are not clinical guidance."""

import re
from typing import Any

# VERIFY ALL CLINICAL THRESHOLDS WITH CURRENT MoHFW/NHM GUIDELINES.
# These prototype thresholds are for hackathon/demo use and are not
# a substitute for clinical judgment or official protocols.
RISK_CONFIG = {
    "hb": {"urgent_below": 7.0, "refer_below": 11.0},
    "bp": {"urgent_systolic_at_least": 160, "urgent_diastolic_at_least": 110,
           "refer_systolic_at_least": 140, "refer_diastolic_at_least": 90},
    "newborn": {"age_days_at_most": 28, "urgent_weight_below_kg": 2.0,
                "refer_weight_below_kg": 2.5},
}

DANGER_SIGNS = (
    "bleeding", "no fetal movement", "severe headache", "breathlessness", "fits", "seizure",
    "खून बहना", "खून आना", "बच्चा नहीं हिल रहा", "तेज सिरदर्द", "सांस लेने में तकलीफ", "दौरे",
    "रक्तस्राव", "रक्त येणे", "बाळाची हालचाल नाही", "तीव्र डोकेदुखी", "श्वास घेण्यास त्रास", "फिट येणे",
)


def parse_bp(value: Any) -> tuple[int, int] | None:
    """Parse a conventional systolic/diastolic value, or return None."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d{2,3})\s*/\s*(\d{2,3})\s*", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def assess_risk(patient: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    urgent = False
    refer = False
    hb = patient.get("hb")
    try:
        hb = float(hb) if hb is not None else None
    except (TypeError, ValueError):
        hb = None
    if hb is not None:
        if hb < RISK_CONFIG["hb"]["urgent_below"]:
            reasons.append("Rule triggered: Hb below configured urgent threshold")
            urgent = True
        elif hb < RISK_CONFIG["hb"]["refer_below"]:
            reasons.append("Rule triggered: Hb below configured refer threshold")
            refer = True

    bp = parse_bp(patient.get("bp"))
    if bp:
        systolic, diastolic = bp
        cfg = RISK_CONFIG["bp"]
        if systolic >= cfg["urgent_systolic_at_least"] or diastolic >= cfg["urgent_diastolic_at_least"]:
            reasons.append("Rule triggered: BP at or above configured urgent threshold")
            urgent = True
        elif systolic >= cfg["refer_systolic_at_least"] or diastolic >= cfg["refer_diastolic_at_least"]:
            reasons.append("Rule triggered: BP at or above configured refer threshold")
            refer = True

    age, unit, weight = patient.get("age"), patient.get("age_unit"), patient.get("weight_kg")
    try:
        newborn_age_days = float(age) * (30 if unit == "months" else 365 if unit == "years" else 1)
    except (TypeError, ValueError):
        newborn_age_days = None
    try:
        weight = float(weight) if weight is not None else None
    except (TypeError, ValueError):
        weight = None
    newborn_cfg = RISK_CONFIG["newborn"]
    if newborn_age_days is not None and newborn_age_days <= newborn_cfg["age_days_at_most"] and weight is not None:
        if weight < newborn_cfg["urgent_weight_below_kg"]:
            reasons.append("Rule triggered: newborn weight below configured urgent threshold")
            urgent = True
        elif weight < newborn_cfg["refer_weight_below_kg"]:
            reasons.append("Rule triggered: newborn weight below configured refer threshold")
            refer = True

    symptoms = patient.get("symptoms") or []
    if isinstance(symptoms, str):
        symptoms = [symptoms]
    normalized = " ".join(" ".join(str(s).lower().split()) for s in symptoms)
    for sign in DANGER_SIGNS:
        if " ".join(sign.lower().split()) in normalized:
            reasons.append(f"Rule triggered: danger-sign keyword detected ({sign})")
            urgent = True

    return {"risk": "urgent" if urgent else "refer_soon" if refer else "none", "reasons": reasons}
