#!/usr/bin/env python3
"""Sync agent-rig.json plugin lists into setup.md and doctor.md marker sections.

Follows gen-catalog.py patterns: ROOT-relative paths, --check flag, idempotent writes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RIG_PATH = ROOT / "agent-rig.json"
SETUP_PATH = ROOT / "commands" / "setup.md"
DOCTOR_PATH = ROOT / "commands" / "doctor.md"
MARKETPLACE_PATH = ROOT.parent.parent / "infra" / "marketplace" / ".claude-plugin" / "marketplace.json"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_rig() -> dict:
    return json.loads(read_text(RIG_PATH))


def load_marketplace() -> dict:
    if MARKETPLACE_PATH.exists():
        return json.loads(read_text(MARKETPLACE_PATH))
    return {}


def parse_source(source_str: str) -> tuple[str, str]:
    """Parse 'name@marketplace' into (name, marketplace)."""
    name, _, marketplace = source_str.partition("@")
    return name, marketplace


def get_tier_entries(rig: dict, tier: str) -> list[dict]:
    """Get plugin entries from a tier (handles core being a single object)."""
    val = rig.get("plugins", {}).get(tier, [])
    if isinstance(val, dict):
        return [val]
    return val


def group_by_marketplace(entries: list[dict]) -> dict[str, list[dict]]:
    """Group entries by marketplace name."""
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        _name, marketplace = parse_source(entry["source"])
        groups.setdefault(marketplace, []).append(entry)
    return groups


# ---------------------------------------------------------------------------
# Generator functions
# ---------------------------------------------------------------------------

def gen_install_interagency(entries: list[dict]) -> str:
    """Generate install commands for interagency-marketplace plugins."""
    lines = ["```bash"]
    for entry in entries:
        lines.append(f"claude plugin install {entry['source']}")
    lines.append("```")
    return "\n".join(lines)


def gen_install_official(entries: list[dict]) -> str:
    """Generate install commands for claude-plugins-official plugins."""
    lines = ["```bash"]
    for entry in entries:
        lines.append(f"claude plugin install {entry['source']}")
    lines.append("```")
    return "\n".join(lines)


def gen_install_infrastructure(entries: list[dict]) -> str:
    """Generate infrastructure install list items."""
    lang_map = {
        "gopls-lsp": "Go",
        "pyright-lsp": "Python",
        "typescript-lsp": "TypeScript",
        "rust-analyzer-lsp": "Rust",
    }
    lines = []
    for entry in entries:
        name, _ = parse_source(entry["source"])
        lang = lang_map.get(name, name)
        lines.append(f"- {lang} → `claude plugin install {entry['source']}`")
    return "\n".join(lines)


def gen_install_optional(entries: list[dict]) -> str:
    """Generate optional plugin list items."""
    lines = []
    for entry in entries:
        lines.append(f"- `{entry['source']}` — {entry['description']}")
    return "\n".join(lines)


def gen_disable_conflicts(entries: list[dict]) -> str:
    """Generate disable commands for conflicting plugins."""
    lines = ["```bash"]
    for entry in entries:
        lines.append(f"claude plugin disable {entry['source']}")
    lines.append("```")
    return "\n".join(lines)


def gen_verify_script(rig: dict) -> str:
    """Generate a shell call to verify-config.sh for setup.md.

    Uses jq/shell instead of python3 to avoid silent stdout swallowing
    on some environments (see GitHub #2).
    """
    return '''```bash
# Resolve script path relative to plugin cache (works from any cwd)
VERIFY_SCRIPT="$(dirname "$(ls "$HOME/.claude/plugins/cache"/*/clavain/*/scripts/verify-config.sh 2>/dev/null | head -1)")/verify-config.sh"
if [[ -x "$VERIFY_SCRIPT" ]]; then
    bash "$VERIFY_SCRIPT"
else
    echo "ERROR: verify-config.sh not found in plugin cache. Try reinstalling clavain."
fi
```'''


def gen_companion_checks(entries: list[dict]) -> str:
    """Generate doctor.md companion check blocks from doctorCheck metadata."""
    sections = []
    # Use a letter counter starting at 'b' for subsection numbering
    letter = ord("b")

    for entry in entries:
        check = entry.get("doctorCheck")
        if not check:
            continue

        name, _ = parse_source(entry["source"])
        label = check["label"]
        probe = check["probe"]
        not_installed_msg = check["notInstalledMsg"]

        section_label = chr(letter)
        letter += 1

        sections.append(f"""### 3{section_label}. {label}

```bash
if ls "$HOME/.claude/plugins/cache"/*/{name}/*/{probe} 2>/dev/null | head -1 >/dev/null; then
  echo "{name}: installed"
else
  echo "{name}: not installed ({not_installed_msg})"
  echo "  Install: claude plugin install {entry['source']}"
fi
```""")

    return "\n\n".join(sections)


def gen_doctor_conflicts(entries: list[dict]) -> str:
    """Generate doctor.md conflicts check script."""
    conflict_lines = ",\n    ".join(f"'{entry['source']}'" for entry in entries)

    return f'''```bash
python3 -c "
import json, os
settings = os.path.expanduser('~/.claude/settings.json')
try:
    plugins = json.load(open(settings)).get('enabledPlugins', {{}})
except FileNotFoundError:
    print('  settings.json not found'); exit()
conflicts = [
    {conflict_lines},
]
active = [p for p in conflicts if plugins.get(p, True)]
if active:
    for p in active:
        print(f'  WARN: {{p}} is still enabled')
else:
    print('  All conflicts disabled')
"
```'''


def gen_doctor_output(rig: dict) -> str:
    """Generate doctor.md output table template."""
    # Build companion lines from entries with doctorCheck
    companion_lines = []
    for entry in get_tier_entries(rig, "recommended"):
        check = entry.get("doctorCheck")
        if check:
            name, _ = parse_source(entry["source"])
            companion_lines.append(f"{name:<14}[installed|not installed]")

    # Always include interlock (hand-written check, no doctorCheck)
    companion_lines.append(f"{'interlock':<14}[installed|not installed]")

    companions = "\n".join(companion_lines)

    return f"""```
Clavain Doctor
──────────────────────────────────
{"context7":<14}[PASS|FAIL]
{"qmd":<14}[PASS|WARN: not installed]
{"oracle":<14}[installed|not found]
{"codex":<14}[installed|not found]
{"beads":<14}[OK (N open, M closed)|not initialized]
{companions}
{".clavain":<14}[initialized|not set up]
{"conflicts":<14}[clear|WARN: N active]
{"skill budget":<14}[PASS|WARN: N over 16K|ERROR: N over 32K]
{"version":<14}v0.X.Y
──────────────────────────────────
```"""


# ---------------------------------------------------------------------------
# Marker replacement
# ---------------------------------------------------------------------------

def replace_between_markers(text: str, section: str, replacement: str) -> str:
    """Replace content between <!-- agent-rig:begin:SECTION --> and <!-- agent-rig:end:SECTION --> markers."""
    pattern = re.compile(
        rf"(<!-- agent-rig:begin:{re.escape(section)} -->\n).*?(<!-- agent-rig:end:{re.escape(section)} -->)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        print(f"WARNING: marker section '{section}' not found", file=sys.stderr)
        return text
    return pattern.sub(rf"\g<1>{replacement}\n\g<2>", text, count=1)


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

def detect_drift(rig: dict, marketplace: dict) -> list[str]:
    """Compare marketplace plugins vs agent-rig.json tiers; warn about uncurated or stale entries."""
    warnings = []

    # Collect all plugin names from agent-rig.json (interagency only)
    rig_names: set[str] = set()
    for tier in ("core", "required", "recommended", "optional"):
        for entry in get_tier_entries(rig, tier):
            name, mp = parse_source(entry["source"])
            if mp == "interagency-marketplace":
                rig_names.add(name)

    # Collect marketplace plugin names
    mp_names: set[str] = set()
    for plugin in marketplace.get("plugins", []):
        mp_names.add(plugin["name"])

    # Plugins in marketplace but not in any agent-rig tier
    uncurated = mp_names - rig_names
    if uncurated:
        for name in sorted(uncurated):
            warnings.append(f"uncurated: {name} is in marketplace but not in agent-rig.json")

    # Plugins in agent-rig but not in marketplace (stale references)
    stale = rig_names - mp_names
    if stale:
        for name in sorted(stale):
            warnings.append(f"stale: {name} is in agent-rig.json but not in marketplace")

    return warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_expected(rig: dict) -> dict[Path, str]:
    """Build expected file contents by applying generator output to marker sections."""
    expected: dict[Path, str] = {}

    # --- setup.md ---
    setup_text = read_text(SETUP_PATH)

    # Collect entries by tier + marketplace
    recommended = get_tier_entries(rig, "recommended")
    required = get_tier_entries(rig, "required")
    optional = get_tier_entries(rig, "optional")
    infrastructure = get_tier_entries(rig, "infrastructure")
    conflicts = get_tier_entries(rig, "conflicts")

    rec_groups = group_by_marketplace(recommended)
    req_groups = group_by_marketplace(required)

    # Interagency = recommended interagency plugins
    interagency_entries = rec_groups.get("interagency-marketplace", [])
    setup_text = replace_between_markers(setup_text, "install-interagency", gen_install_interagency(interagency_entries))

    # Official = required + recommended official plugins
    official_entries = req_groups.get("claude-plugins-official", []) + rec_groups.get("claude-plugins-official", [])
    setup_text = replace_between_markers(setup_text, "install-official", gen_install_official(official_entries))

    # Infrastructure
    setup_text = replace_between_markers(setup_text, "install-infrastructure", gen_install_infrastructure(infrastructure))

    # Optional
    setup_text = replace_between_markers(setup_text, "install-optional", gen_install_optional(optional))

    # Conflicts
    setup_text = replace_between_markers(setup_text, "disable-conflicts", gen_disable_conflicts(conflicts))

    # Verify script
    setup_text = replace_between_markers(setup_text, "verify-script", gen_verify_script(rig))

    expected[SETUP_PATH] = setup_text

    # --- doctor.md ---
    doctor_text = read_text(DOCTOR_PATH)

    # Companion checks (from recommended entries with doctorCheck)
    doctor_text = replace_between_markers(doctor_text, "companion-checks", gen_companion_checks(recommended))

    # Conflicts
    doctor_text = replace_between_markers(doctor_text, "doctor-conflicts", gen_doctor_conflicts(conflicts))

    # Output table
    doctor_text = replace_between_markers(doctor_text, "doctor-output", gen_doctor_output(rig))

    expected[DOCTOR_PATH] = doctor_text

    return expected


def compute_drift(expected: dict[Path, str]) -> list[Path]:
    drifted: list[Path] = []
    for path, desired in expected.items():
        current = read_text(path) if path.exists() else None
        if current != desired:
            drifted.append(path)
    return drifted


def write_updates(expected: dict[Path, str], drifted: list[Path]) -> None:
    for path in drifted:
        path.write_text(expected[path], encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync agent-rig.json plugin lists into setup.md and doctor.md.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for drift without writing files (exit 1 if changes are needed).",
    )
    args = parser.parse_args()

    rig = load_rig()
    expected = build_expected(rig)
    drifted = compute_drift(expected)

    # Drift detection against marketplace
    marketplace = load_marketplace()
    if marketplace:
        warnings = detect_drift(rig, marketplace)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)

    if args.check:
        if drifted:
            print("Drift detected:")
            for path in drifted:
                print(f"- {path.relative_to(ROOT).as_posix()}")
            return 1
        print("Agent-rig sync is fresh.")
        return 0

    if not drifted:
        print("Agent-rig sync is already fresh.")
        return 0

    write_updates(expected, drifted)
    print("Updated files:")
    for path in drifted:
        print(f"- {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)
