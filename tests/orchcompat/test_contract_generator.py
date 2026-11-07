"""Characterization of the instruction-contract generator and its drift check.

scripts/sync-agent-instructions.py renders config/agent-instructions.md plus a
host adapter into a managed block, stamps it with a receipt line (package
version, policy selection, policy SHA256, contract SHA256), and either prints,
diffs, writes or checks it. scripts/check-instruction-contract.sh wraps the
check and classifies drift.

The generator and the helper are this checkout's real scripts. The template,
adapters, version and policy are frozen copies under fixtures/contract, so the
golden (golden/contract_render.json) changes only when the generator changes.
Regenerate with `python3 tests/orchcompat/gen_golden.py --contract` and read
the diff: a changed hash or line is a changed contract.

tests/structural already checks the live template against the live repo; these
tests pin the generator's own behavior and failure modes.
"""
import hashlib
import json
import re

import pytest

import orchlib as o

GOLDEN = json.loads((o.GOLDEN / "contract_render.json").read_text())
BLOCK_START = "<!-- BEGIN CLAVAIN CODEX TOOL MAP -->"
BLOCK_END = "<!-- END CLAVAIN CODEX TOOL MAP -->"
FIXTURE_POLICY_SHA = hashlib.sha256((o.CONTRACT_FIXTURES / "routing.yaml").read_bytes()).hexdigest()
RECEIPT = re.compile(
    r"Host: (?P<host>\w+); package: (?P<version>[^;]+); policy selection: (?P<selection>[^;]+); "
    r"policy SHA256: (?P<policy>[0-9a-f]{64}); contract SHA256: (?P<contract>[0-9a-f]{64})\.")


@pytest.fixture
def src(tmp_path):
    return o.make_source(tmp_path / "src")


def gen(src, home, *args, **kw):
    return o.run_generator(src, home, *args, **kw)


# --- golden: the rendered contract per host and policy mode ----------------

def test_golden_covers_every_host_and_mode():
    assert sorted(GOLDEN) == sorted(f"{h}|{m}" for h in o.CONTRACT_HOSTS
                                    for m in ("explicit", "portable", "default"))


def test_render_matches_golden(tmp_path):
    assert o.contract_cases(tmp_path) == GOLDEN


@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_rendered_block_shape(key):
    case = GOLDEN[key]
    host, mode = key.split("|")
    body = case["body"]
    assert case["rc"] == 0
    assert body.startswith(BLOCK_START) and body.rstrip().endswith(BLOCK_END)
    assert "{{" not in body, "every placeholder is replaced"
    m = RECEIPT.search(body)
    assert m and m["host"] == host and m["version"] == "1.2.3"
    assert m["policy"] == FIXTURE_POLICY_SHA
    assert m["selection"] == ("portable-managed-installation" if mode == "portable" else "explicit-installation")
    # The profile line: the generator carries the pilot-profile sentence verbatim.
    assert "`CLAVAIN_POLICY_PROFILE=ci-campaign-pilot` requires `scope: mk-ag2s`" in body
    meta = case["metadata"]
    assert meta["policy_hash"] == m["policy"] and meta["contract_hash"] == m["contract"]
    assert meta["routing"] == "instructional" and meta["behaviorally_verified"] is False
    assert meta["parent_model_changed"] is False


def test_policy_argument_by_mode():
    claude = GOLDEN["claude|portable"]["body"]
    assert '--policy="${CLAVAIN_ROUTING_POLICY:-${CLAVAIN_SELECTED_ROOT:?set from native Clavain skill location}/config/routing.yaml}"' in claude
    codex = GOLDEN["codex|portable"]["body"]
    assert '--policy="${CLAVAIN_ROUTING_POLICY:-$HOME/.agents/skills/clavain/../config/routing.yaml}"' in codex
    assert "--policy=<POLICY> " in GOLDEN["claude|explicit"]["body"]
    # Default (no --policy) names the source's own routing.yaml, which is the
    # fixture policy here, so it renders the same as the explicit form.
    assert GOLDEN["claude|default"]["body"] == GOLDEN["claude|explicit"]["body"]


def test_host_text_comes_from_adapter_or_inline_instruction():
    # codex reads its text from a file; claude carries it inline.
    assert "Native model switching" not in GOLDEN["codex|explicit"]["body"]
    assert "first invoke native Skill `clavain:using-clavain`" in GOLDEN["claude|explicit"]["body"]
    assert "Native model switching and delegation enforcement are unsupported" in GOLDEN["gemini|explicit"]["body"]


def test_contract_hash_is_per_host_and_per_selection():
    hashes = {k: v["metadata"]["contract_hash"] for k, v in GOLDEN.items()}
    # Explicit and default selection hash the same bytes (path is not hashed).
    for host in o.CONTRACT_HOSTS:
        assert hashes[f"{host}|explicit"] == hashes[f"{host}|default"]
        assert hashes[f"{host}|portable"] != hashes[f"{host}|explicit"]
    assert len({hashes[f"{h}|explicit"] for h in o.CONTRACT_HOSTS}) == len(o.CONTRACT_HOSTS)


def test_policy_hash_follows_policy_bytes_not_contract_hash(src, home):
    a = json.loads(gen(src, home, "--host", "claude", "--file", home / "x.md", "--check").stdout)
    (src / "config/routing.yaml").write_text("changed: true\n")
    b = json.loads(gen(src, home, "--host", "claude", "--file", home / "x.md", "--check").stdout)
    assert a["policy_hash"] != b["policy_hash"]
    assert b["policy_hash"] == hashlib.sha256(b"changed: true\n").hexdigest()
    assert a["contract_hash"] == b["contract_hash"]


def test_malformed_policy_still_renders_because_it_is_only_hashed(src, home):
    # Pinned: the generator never parses the policy. Garbage bytes render and
    # are hashed; rejecting a malformed policy is the router's job (`ic`).
    garbage = b"\x00: [unclosed\n  - {\n"
    (src / "config/routing.yaml").write_bytes(garbage)
    r = gen(src, home, "--host", "claude", "--render")
    assert r.returncode == 0
    assert hashlib.sha256(garbage).hexdigest() in r.stdout


# --- failure modes ----------------------------------------------------------

def test_unknown_host_is_a_key_error(src, home):
    r = gen(src, home, "--host", "bogus", "--render")
    assert r.returncode == 1 and r.stdout == ""
    assert r.stderr.strip() == "'bogus'"


def test_missing_policy_fails_with_os_error(src, home):
    r = gen(src, home, "--host", "claude", "--render", "--policy", home / "nope.yaml")
    assert r.returncode == 1 and "No such file or directory" in r.stderr


def test_missing_plugin_json_fails(src, home):
    (src / ".claude-plugin/plugin.json").unlink()
    r = gen(src, home, "--host", "claude", "--render")
    assert r.returncode == 1 and "plugin.json" in r.stderr


def test_plugin_json_without_version_is_unversioned(src, home):
    (src / ".claude-plugin/plugin.json").write_text('{"name": "x"}')
    assert "package: unversioned;" in gen(src, home, "--host", "claude", "--render").stdout


@pytest.mark.parametrize("name,text,needle", [
    ("config/host-adapters.json", "{not json", "Expecting property name"),
    (".claude-plugin/plugin.json", "{not json", "Expecting property name"),
])
def test_malformed_json_inputs_fail(src, home, name, text, needle):
    (src / name).write_text(text)
    r = gen(src, home, "--host", "claude", "--render")
    assert r.returncode == 1 and needle in r.stderr


def test_missing_template_fails(src, home):
    (src / "config/agent-instructions.md").unlink()
    r = gen(src, home, "--host", "claude", "--render")
    assert r.returncode == 1 and "agent-instructions.md" in r.stderr


def test_missing_source_directory_fails(home, tmp_path):
    r = gen(tmp_path / "absent", home, "--host", "claude", "--render")
    assert r.returncode == 1 and "No such file or directory" in r.stderr


def test_expected_policy_hash_match_and_mismatch(src, home):
    ok = gen(src, home, "--host", "claude", "--render", "--expected-policy-hash", FIXTURE_POLICY_SHA)
    assert ok.returncode == 0 and FIXTURE_POLICY_SHA in ok.stdout
    bad = gen(src, home, "--host", "claude", "--render", "--expected-policy-hash", "0" * 64)
    assert bad.returncode == 1 and bad.stdout == ""
    assert bad.stderr.strip() == "Reasoning policy changed after resolution; reclassify before dispatch"


def test_empty_expected_hash_is_not_enforced(src, home):
    assert gen(src, home, "--host", "claude", "--render", "--expected-policy-hash", "").returncode == 0


def test_policy_and_portable_policy_are_mutually_exclusive(src, home):
    r = gen(src, home, "--host", "claude", "--render", "--portable-policy", "--policy", src / "config/routing.yaml")
    assert r.returncode == 2 and "mutually exclusive" in r.stderr


def test_file_is_required_unless_render(src, home):
    r = gen(src, home, "--host", "claude")
    assert r.returncode == 2 and "--file is required unless --render" in r.stderr


def test_host_and_source_are_required(home):
    r = o.run([o.py(), "-I", o.ROOT / "scripts/sync-agent-instructions.py", "--render"], o.hermetic_env(home))
    assert r.returncode == 2 and "--source" in r.stderr


# --- --check, --dry-run and write -------------------------------------------

def check(src, home, target, host="claude", *flags):
    r = gen(src, home, "--host", host, "--file", target, "--check", *flags)
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None), r


def test_check_reports_missing_file_as_not_current(src, home):
    rc, meta, _ = check(src, home, home / "CLAUDE.md")
    assert rc == 1 and meta["current"] is False


def test_write_then_check_is_current_and_preserves_surrounding_text(src, home):
    target = home / "CLAUDE.md"
    target.write_text("# mine\nkeep this\n")
    w = gen(src, home, "--host", "claude", "--file", target)
    assert w.returncode == 0 and w.stdout.startswith("Updated managed instructions:")
    text = target.read_text()
    assert text.startswith("# mine\nkeep this\n") and BLOCK_START in text and text.endswith(BLOCK_END + "\n")
    rc, meta, _ = check(src, home, target)
    assert rc == 0 and meta["current"] is True
    again = gen(src, home, "--host", "claude", "--file", target)
    assert again.stdout.startswith("Managed instructions already up to date:")


def test_dry_run_prints_a_diff_and_writes_nothing(src, home):
    target = home / "AGENTS.md"
    target.write_text("existing\n")
    r = gen(src, home, "--host", "codex", "--file", target, "--dry-run")
    assert r.returncode == 0 and target.read_text() == "existing\n"
    assert r.stdout.startswith(f"--- {target}\n+++ {target}\n")
    assert f"+{BLOCK_START}" in r.stdout


def test_dry_run_on_current_file_prints_nothing(src, home):
    target = home / "AGENTS.md"
    gen(src, home, "--host", "codex", "--file", target)
    r = gen(src, home, "--host", "codex", "--file", target, "--dry-run")
    assert r.returncode == 0 and r.stdout == ""


def test_policy_change_makes_an_installed_block_stale(src, home):
    target = home / "CLAUDE.md"
    gen(src, home, "--host", "claude", "--file", target)
    (src / "config/routing.yaml").write_text("dispatch: {}\n")
    rc, meta, _ = check(src, home, target)
    assert rc == 1 and meta["current"] is False


def test_check_flags_local_routing_override_outside_the_block(src, home):
    target = home / "CLAUDE.md"
    gen(src, home, "--host", "claude", "--file", target)
    clean = check(src, home, target)[1]
    assert clean["local_routing_override_review_required"] is False
    target.write_text("model: opus\n" + target.read_text())
    rc, meta, _ = check(src, home, target)
    assert rc == 0 and meta["local_routing_override_review_required"] is True


def test_duplicate_markers_refuse_to_write_and_leave_file_unchanged(src, home):
    target = home / "AGENTS.md"
    target.write_text(f"{BLOCK_START}\nold\n{BLOCK_END}\n{BLOCK_START}\n")
    before = target.read_text()
    r = gen(src, home, "--host", "codex", "--file", target)
    assert r.returncode == 1 and "Malformed or duplicated managed markers; file unchanged" in r.stderr
    assert target.read_text() == before


def test_write_replaces_only_the_old_block(src, home):
    target = home / "AGENTS.md"
    target.write_text(f"top\n{BLOCK_START}\nstale\n{BLOCK_END}\nbottom\n")
    gen(src, home, "--host", "codex", "--file", target)
    text = target.read_text()
    assert text.startswith("top\n") and text.endswith("\nbottom\n") and "stale" not in text


def test_write_follows_a_symlink_and_keeps_it(src, home):
    real = home / "real.md"
    real.write_text("x\n")
    link = home / "AGENTS.md"
    link.symlink_to(real)
    gen(src, home, "--host", "codex", "--file", link)
    assert link.is_symlink() and BLOCK_START in real.read_text()


def test_write_into_a_missing_directory_fails(src, home):
    r = gen(src, home, "--host", "codex", "--file", home / "nodir" / "AGENTS.md")
    assert r.returncode == 1 and "target directory must already exist" in r.stderr


def test_kimi_legacy_markers_are_migrated(src, home):
    target = home / "AGENTS.md"
    target.write_text("<!-- BEGIN CLAVAIN KIMI TOOL MAP -->\nold\n<!-- END CLAVAIN KIMI TOOL MAP -->\n")
    gen(src, home, "--host", "kimi", "--file", target)
    text = target.read_text()
    assert "KIMI TOOL MAP" not in text and BLOCK_START in text and "old" not in text


def test_kimi_legacy_and_shared_markers_together_are_refused(src, home):
    target = home / "AGENTS.md"
    target.write_text(f"<!-- BEGIN CLAVAIN KIMI TOOL MAP -->\n{BLOCK_START}\n")
    r = gen(src, home, "--host", "kimi", "--file", target)
    assert r.returncode == 1 and "Both legacy and shared managed blocks exist" in r.stderr


# --- the live repository ----------------------------------------------------

@pytest.mark.parametrize("host", o.CONTRACT_HOSTS)
def test_live_template_renders_for_every_host(host, home):
    """Content-independent: the live template and adapters still render cleanly."""
    r = o.run([o.py(), "-I", o.ROOT / "scripts/sync-agent-instructions.py", "--source", o.ROOT,
               "--host", host, "--render", "--portable-policy"], o.hermetic_env(home))
    assert r.returncode == 0, r.stderr
    assert "{{" not in r.stdout and r.stdout.startswith(BLOCK_START)
    m = RECEIPT.search(r.stdout)
    assert m and m["host"] == host
    assert m["policy"] == o.policy_sha256(o.ROOT / "config/routing.yaml")


# --- check-instruction-contract.sh ------------------------------------------

def drift(src, home, *args, root=None, env_extra=None):
    env = o.hermetic_env(home, CLAVAIN_SELECTED_ROOT=root if root is not None else src, **(env_extra or {}))
    r = o.run(["bash", src / "scripts/check-instruction-contract.sh", *args], env)
    out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else None
    return r.returncode, out, r


def install(src, home, host="claude", name="CLAUDE.md", *flags):
    target = home / name
    r = gen(src, home, "--host", host, "--file", target, *flags)
    assert r.returncode == 0, r.stderr
    return target


def test_checker_current_portable(src, home):
    target = install(src, home, "claude", "CLAUDE.md", "--portable-policy")
    rc, out, _ = drift(src, home, "--host", "claude", "--file", target)
    assert rc == 0 and out["current"] is True and out["drift"] == []
    assert out["file_version"] == out["installed_version"] == "1.2.3"
    assert out["file_policy_hash"] == out["policy_hash"] == FIXTURE_POLICY_SHA


def test_checker_explicit_mode_uses_the_explicit_block(src, home):
    portable = install(src, home, "claude", "P.md", "--portable-policy")
    explicit = install(src, home, "claude", "E.md")
    assert drift(src, home, "--host", "claude", "--file", explicit, "--explicit")[0] == 0
    rc, out, _ = drift(src, home, "--host", "claude", "--file", portable, "--explicit")
    assert rc == 1 and out["drift"] == ["block-content"]
    rc, out, _ = drift(src, home, "--host", "claude", "--file", explicit)
    assert rc == 1 and out["drift"] == ["block-content"]


def test_checker_file_missing(src, home):
    rc, out, _ = drift(src, home, "--host", "claude", "--file", home / "absent.md")
    assert rc == 1 and out["drift"] == ["file-missing"] and out["current"] is False


def test_checker_no_receipt(src, home):
    target = home / "CLAUDE.md"
    target.write_text("# nothing managed here\n")
    rc, out, _ = drift(src, home, "--host", "claude", "--file", target)
    assert rc == 1 and out["drift"] == ["no-receipt"]


def test_checker_version_drift(src, home):
    target = install(src, home, "claude", "CLAUDE.md", "--portable-policy")
    (src / ".claude-plugin/plugin.json").write_text('{"version": "2.0.0"}')
    rc, out, _ = drift(src, home, "--host", "claude", "--file", target)
    assert rc == 1 and "version" in out["drift"]
    assert (out["file_version"], out["installed_version"]) == ("1.2.3", "2.0.0")


def test_checker_policy_hash_drift_on_unchanged_version(src, home):
    target = install(src, home, "claude", "CLAUDE.md", "--portable-policy")
    (src / "config/routing.yaml").write_text("dispatch: {}\n")
    rc, out, _ = drift(src, home, "--host", "claude", "--file", target)
    assert rc == 1 and out["drift"] == ["policy-hash"]
    assert out["file_policy_hash"] == FIXTURE_POLICY_SHA != out["policy_hash"]


def test_checker_block_content_drift_with_matching_receipt(src, home):
    target = install(src, home, "claude", "CLAUDE.md", "--portable-policy")
    target.write_text(target.read_text().replace("Never silently", "Sometimes silently"))
    rc, out, _ = drift(src, home, "--host", "claude", "--file", target)
    assert rc == 1 and out["drift"] == ["block-content"]


def test_checker_ignores_receipts_quoted_outside_the_block(src, home):
    target = install(src, home, "claude", "CLAUDE.md", "--portable-policy")
    target.write_text("package: 0.0.1; policy selection: x; policy SHA256: " + "a" * 64 + "\n" + target.read_text())
    rc, out, _ = drift(src, home, "--host", "claude", "--file", target)
    assert rc == 0 and out["drift"] == []


@pytest.mark.parametrize("args,needle", [
    ([], "usage:"),
    (["--host", "claude"], "usage:"),
    (["--host"], "--host needs a value"),
    (["--bogus"], "unknown argument: --bogus"),
])
def test_checker_usage_errors_exit_2(src, home, args, needle):
    rc, out, r = drift(src, home, *args)
    assert rc == 2 and needle in r.stderr and out is None


@pytest.mark.parametrize("root", ["", "/nonexistent-root"])
def test_checker_needs_a_clavain_root(src, home, root):
    rc, out, r = drift(src, home, "--host", "claude", "--file", home / "x.md", root=root)
    assert rc == 2 and "CLAVAIN_SELECTED_ROOT must name an installed Clavain root" in r.stderr


def test_checker_renderer_error_exits_2_with_renderer_error_drift(src, home):
    rc, out, _ = drift(src, home, "--host", "bogus", "--file", home / "x.md")
    assert rc == 2 and out["drift"] == ["renderer-error"] and out["current"] is False
    assert "bogus" in out["error"]


def test_checker_help_prints_the_header_comment(src, home):
    rc, _, r = drift(src, home, "--help")
    assert rc == 0 and r.stdout.startswith("# Check that a host instruction file")
