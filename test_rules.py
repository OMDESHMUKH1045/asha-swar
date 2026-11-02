"""Fast, offline, dataset-driven tests for the deterministic risk rules."""

import json
import sys
from pathlib import Path

from rules import assess_risk


def main() -> int:
    path = Path(__file__).with_name("synthetic_asha_notes_fixed.json")
    notes = json.loads(path.read_text(encoding="utf-8"))
    total = passed = 0
    for note in notes:
        for index, patient in enumerate(note.get("patients", []), start=1):
            expected = patient.get("expected_risk") or note.get("expected_risk")
            actual = assess_risk(patient)["risk"]
            label = patient.get("name") or f"Patient {index}"
            total += 1
            if actual == expected:
                passed += 1
                print(f"PASS {note.get('id')} / {label}")
            else:
                print(f"FAIL {note.get('id')} / {label}\n  Expected: {expected}\n  Got: {actual}")
    failed = total - passed
    print(f"Total: {total}\nPassed: {passed}\nFailed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
