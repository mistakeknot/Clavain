from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_reflect_does_not_run_receipted_calibration_loops() -> None:
    reflect = (ROOT / "commands" / "reflect.md").read_text(encoding="utf-8")
    normalized = " ".join(reflect.split())

    assert "calibrate-phase-costs" not in reflect
    assert "_interspect_write_routing_calibration" not in reflect
    assert "calibration-streak record-manual" not in reflect
    assert "SessionEnd owns routing, gate-threshold, and phase-cost calibration" in normalized
