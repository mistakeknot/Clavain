"""Structural contracts for proof-gated terminal completion."""


def test_calibration_close_gate_verifies_before_token_consumption(project_root):
    script = (project_root / "scripts" / "gates" / "bead-close.sh").read_text()
    label = script.index("close-gate:calibration-streak")
    verify = script.index("calibration-streak verify --target=10")
    consume = script.index("gate_token_consume bead-close")

    assert label < verify < consume


def test_calibration_close_gate_does_not_guard_every_bead(project_root):
    script = (project_root / "scripts" / "gates" / "bead-close.sh").read_text()
    assert 'if bead_has_label "$BEAD_ID" "close-gate:calibration-streak"' in script


def test_runtime_close_gate_verifies_and_persists_before_token_consumption(project_root):
    script = (project_root / "scripts" / "gates" / "bead-close.sh").read_text()
    required = script.index('runtime-evidence required "$BEAD_ID"')
    verify = script.index('runtime-evidence verify "$BEAD_ID"')
    completed = script.index('run status "$runtime_run_id"')
    persist = script.index('runtime_evidence_schema=$runtime_schema')
    consume = script.index("gate_token_consume bead-close")

    assert required < verify < completed < persist < consume


def test_reflect_registers_artifact_without_terminal_advance(project_root):
    reflect = (project_root / "commands" / "reflect.md").read_text()

    assert 'set-artifact "<sprint_id>" "reflection"' in reflect
    assert "sprint-advance" not in reflect
    assert "reflect -> done" not in reflect.replace("→", "->")


def test_sprint_terminal_step_orders_land_collect_advance_and_close(project_root):
    sprint = (project_root / "commands" / "sprint.md").read_text()
    step_ten = sprint[sprint.index("## Step 10: Ship") :]

    land = step_ten.index("clavain:landing-a-change")
    required = step_ten.index('runtime-evidence required "$CLAVAIN_BEAD_ID"')
    collect = step_ten.index('runtime-evidence collect "$CLAVAIN_BEAD_ID"')
    advance = step_ten.index('sprint-advance "$CLAVAIN_BEAD_ID" "reflect"')
    close = step_ten.index('scripts/gates/bead-close.sh" "$CLAVAIN_BEAD_ID"')

    assert land < required < collect < advance < close
