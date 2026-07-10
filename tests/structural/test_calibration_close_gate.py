"""Structural contract for the A:L3 proof close gate."""


def test_calibration_close_gate_verifies_before_token_consumption(project_root):
    script = (project_root / "scripts" / "gates" / "bead-close.sh").read_text()
    label = script.index("close-gate:calibration-streak")
    verify = script.index("calibration-streak verify --target=10")
    consume = script.index("gate_token_consume bead-close")

    assert label < verify < consume


def test_calibration_close_gate_does_not_guard_every_bead(project_root):
    script = (project_root / "scripts" / "gates" / "bead-close.sh").read_text()
    assert 'if bead_has_label "$BEAD_ID" "close-gate:calibration-streak"' in script
