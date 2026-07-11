"""Structural invariants for the installed-runtime close gate."""

from pathlib import Path


CANONICAL_CLOSE = "scripts/gates/bead-close.sh"


def _read(project_root: Path, relative: str) -> str:
    return (project_root / relative).read_text(encoding="utf-8")


def test_managed_close_surfaces_route_through_canonical_wrapper(project_root):
    routed = [
        "scripts/bead-close-shipped.sh",
        "scripts/bead-land.sh",
        "hooks/lib-sprint.sh",
        "commands/bead-sweep.md",
        "commands/campaign.md",
        "commands/clavain-doctor.md",
        "skills/landing-a-change/SKILL.md",
        "skills/landing-a-change/SKILL-compact.md",
        "skills/ship/SKILL.md",
    ]

    for relative in routed:
        assert CANONICAL_CLOSE in _read(project_root, relative), relative


def test_landing_and_ship_push_before_gated_close(project_root):
    for relative in [
        "skills/landing-a-change/SKILL.md",
        "skills/landing-a-change/SKILL-compact.md",
        "skills/ship/SKILL.md",
    ]:
        text = _read(project_root, relative)
        assert text.index("git push") < text.index(CANONICAL_CLOSE), relative


def test_no_unmanaged_raw_close_in_active_surfaces(project_root):
    allowed = {
        "cmd/clavain-cli/children.go",  # guarded automated parent/child path
        "hooks/lib-signals.sh",  # transcript signal detector
        "scripts/gates/README.md",  # wrapper documentation
        "scripts/gates/bead-close.sh",  # sole raw close implementation
        "scripts/gates/gates-smoke_test.sh",
        "skills/project-onboard/templates/AGENTS.md.tmpl",  # downstream template
    }
    active_roots = ["commands", "skills", "scripts", "hooks", "cmd/clavain-cli"]
    violations = []

    for root in active_roots:
        for path in (project_root / root).rglob("*"):
            if not path.is_file() or ".worktrees" in path.parts:
                continue
            relative = path.relative_to(project_root).as_posix()
            if relative.startswith("cmd/clavain-cli/docs/") or relative in allowed:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "bd close" in text or 'runBD("close"' in text:
                violations.append(relative)

    assert violations == []


def test_children_raw_close_is_preceded_by_runtime_requirement_guard(project_root):
    source = _read(project_root, "cmd/clavain-cli/children.go")
    child = source[source.index("func cmdCloseChildren"):source.index("func cmdCloseParentIfDone")]
    parent = source[source.index("func cmdCloseParentIfDone"):]

    for section in [child, parent]:
        assert section.count('runBD("close"') == 1
        assert "runtimeEvidenceAutoCloseAllowed" in section
        assert section.index("runtimeEvidenceAutoCloseAllowed") < section.index('runBD("close"')


def test_reflected_sprint_resumes_at_terminal_ship_step(project_root):
    route = _read(project_root, "commands/route.md")
    reflect_spec = _read(project_root, "config/agency/reflect.yaml")

    assert 'get-artifact "$sprint_id" "reflection"' in route
    assert '[[ -n "$reflection" && -f "$reflection" ]]' in route
    assert "/clavain:sprint --from-step ship" in route
    assert "resolve→`/clavain:resolve`" in route
    assert "advance to done" not in reflect_spec


def test_doctor_runs_full_runtime_evidence_audit(project_root):
    doctor = _read(project_root, "commands/clavain-doctor.md")

    assert "scripts/runtime-evidence-audit.sh" in doctor
    assert '"$_runtime_audit" --json' in doctor
    assert "runtime evidence audit: PASS" in doctor
    assert "runtime evidence audit: FAIL" in doctor
    rc_failure = doctor.index('elif [ "$_audit_rc" -gt 1 ]')
    unsupported = doctor.index('elif [ "$(echo "$_audit_json" | jq -r \'.supported\')" != "true" ]')
    assert rc_failure < unsupported
