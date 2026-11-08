"""Tests for skill directories and SKILL.md files."""

import re
from pathlib import Path

import pytest

from helpers import parse_frontmatter as _parse_frontmatter


def _get_skill_dirs():
    """Get all skill directories containing SKILL.md at collection time."""
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    return sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


SKILL_DIRS = _get_skill_dirs()


def test_skill_count(skills_dir, plugin_json):
    """Skill count on filesystem matches plugin.json manifest."""
    dirs = sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )
    expected = len(plugin_json.get("skills", []))
    assert len(dirs) == expected, (
        f"plugin.json lists {expected} skills, filesystem has {len(dirs)}: {[d.name for d in dirs]}"
    )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_has_skillmd(skill_dir):
    """Every skill directory contains SKILL.md."""
    assert (skill_dir / "SKILL.md").exists(), (
        f"{skill_dir.name}/ is missing SKILL.md"
    )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_has_frontmatter(skill_dir):
    """Each SKILL.md has YAML frontmatter."""
    fm, _ = _parse_frontmatter(skill_dir / "SKILL.md")
    assert fm is not None, f"{skill_dir.name}/SKILL.md is missing frontmatter"


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_frontmatter_required_fields(skill_dir):
    """Frontmatter has 'name' and 'description'."""
    fm, _ = _parse_frontmatter(skill_dir / "SKILL.md")
    assert fm is not None, f"{skill_dir.name}/SKILL.md has no frontmatter"
    for field in ("name", "description"):
        assert field in fm, (
            f"{skill_dir.name}/SKILL.md frontmatter missing: {field}"
        )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_name_matches_dirname(skill_dir):
    """Frontmatter 'name' matches directory name."""
    fm, _ = _parse_frontmatter(skill_dir / "SKILL.md")
    assert fm is not None, f"{skill_dir.name}/SKILL.md has no frontmatter"
    expected = skill_dir.name
    actual = fm.get("name", "")
    assert actual == expected, (
        f"Name mismatch in {skill_dir.name}/SKILL.md: "
        f"frontmatter says {actual!r}, dirname says {expected!r}"
    )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_dirname_kebab_case(skill_dir):
    """Skill directory names follow kebab-case convention."""
    name = skill_dir.name
    assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name), (
        f"Skill directory {name!r} is not kebab-case"
    )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_body_nonempty(skill_dir):
    """Body after frontmatter is at least 50 characters."""
    _, body = _parse_frontmatter(skill_dir / "SKILL.md")
    body_stripped = body.strip()
    assert len(body_stripped) >= 50, (
        f"{skill_dir.name}/SKILL.md body is too short ({len(body_stripped)} chars)"
    )


def test_no_orphan_skill_dirs(skills_dir):
    """No empty directories in skills/."""
    for d in skills_dir.iterdir():
        if d.is_dir():
            contents = list(d.iterdir())
            assert len(contents) > 0, f"Orphan (empty) skill directory: {d.name}/"


# --- Description budget, references links and coverage (bead mk-yvmw9.7) ---

DESCRIPTION_CAP = 1024
_LINK_RE = re.compile(r"\]\(\s*(?:\./)?(references/[^)\s#]+)(?:#[^)]*)?\s*\)")


def _unfolded_description(skill_md):
    """Description after YAML unfolding, or None when absent."""
    fm, _ = _parse_frontmatter(skill_md)
    if not fm:
        return None
    desc = fm.get("description")
    return None if desc is None else str(desc).strip()


def _dead_reference_links(skill_md):
    """Relative SKILL.md links into references/ whose target is missing."""
    text = skill_md.read_text(encoding="utf-8")
    return [
        rel for rel in _LINK_RE.findall(text)
        if not (skill_md.parent / rel).exists()
    ]


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_description_within_cap(skill_dir):
    """Unfolded description fits the cap; truncation drops the routing tail."""
    desc = _unfolded_description(skill_dir / "SKILL.md")
    assert desc, f"{skill_dir.name}/SKILL.md has no description"
    assert len(desc) <= DESCRIPTION_CAP, (
        f"{skill_dir.name} description is {len(desc)} chars, cap {DESCRIPTION_CAP}"
    )


def test_description_parser_is_not_vacuous():
    """Positive control: some real description is long enough that a broken
    parser returning short or empty strings would be caught."""
    lengths = [len(_unfolded_description(d / "SKILL.md") or "") for d in SKILL_DIRS]
    assert max(lengths) > 200, f"longest description is only {max(lengths)} chars"


def test_description_cap_catches_planted_overlong(tmp_path):
    """Planted fixture: a folded description over the cap is measured as over."""
    d = tmp_path / "planted"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: planted\ndescription: >\n  " + "word " * 300 + "\n---\n" + "body " * 20
    )
    assert len(_unfolded_description(d / "SKILL.md")) > DESCRIPTION_CAP


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_references_links_resolve(skill_dir):
    """Every relative link from SKILL.md into references/ exists."""
    dead = _dead_reference_links(skill_dir / "SKILL.md")
    assert not dead, f"{skill_dir.name}/SKILL.md has dead references links: {dead}"


def test_reference_link_check_catches_planted_dead_link(tmp_path):
    """Planted fixture: a dead link is reported, a live one is not."""
    d = tmp_path / "planted"
    (d / "references").mkdir(parents=True)
    (d / "references" / "ok.md").write_text("x")
    (d / "SKILL.md").write_text(
        "---\nname: planted\ndescription: x\n---\n"
        "[ok](references/ok.md) [ok2](./references/ok.md) [bad](references/missing.md#a)\n"
        "[bad2](./references/missing2.md)\n"
    )
    assert _dead_reference_links(d / "SKILL.md") == [
        "references/missing.md", "references/missing2.md",
    ]


def test_every_skill_dir_is_covered(skills_dir):
    """Every directory under skills/ is in the parametrized set, so a new
    skill cannot escape the per-skill checks above."""
    on_disk = sorted(d.name for d in skills_dir.iterdir() if d.is_dir())
    covered = sorted(d.name for d in SKILL_DIRS)
    assert on_disk == covered, (
        f"skill dirs without SKILL.md or not collected: {sorted(set(on_disk) ^ set(covered))}"
    )


# --- Hygiene checks: cross-references, compact/full parity, canon (bead mk-2i46.1) ---

import yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CLAVAIN_REF_RE = re.compile(r"(?<![\w/.-])clavain:([a-z][a-z0-9-]*)")
_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_ROLE_RE = re.compile(r"--role[ =]\{?([A-Za-z][A-Za-z0-9|-]*)\}?")
_DISPATCH_RE = re.compile(r"\bdispatch(?:\.sh)?\b")
_SHINGLE = 8
# codex-delegate carried ~36 shared 8-word runs with interserve-engine before
# the enrolled block was reduced to a pointer; 8 remain. Fail well below the old
# level but with headroom for incidental shared phrasing.
_MAX_SHARED_SHINGLES = 15


def _known_clavain_names(root):
    """Names a `clavain:<name>` reference may resolve to: skills, commands, agents."""
    names = {d.name for d in (root / "skills").iterdir() if d.is_dir()}
    names |= {p.stem for p in (root / "commands").glob("*.md")}
    names |= {p.stem for p in (root / "agents").rglob("*.md")}
    return names


def _unresolved_clavain_refs(text, known):
    return sorted(set(_CLAVAIN_REF_RE.findall(text)) - known)


def _fenced(text):
    return "\n".join(_FENCE_RE.findall(text))


def _fenced_roles(text):
    """Role names used with --role on dispatch command lines (dispatch.sh, `route dispatch`, task-delivery.py dispatch)
    inside fenced code blocks (alternations split). Other tools take their own
    --role flag (for example pattern-f-verdict.sh), so they are not counted."""
    roles = set()
    logical = _fenced(text).replace("\\\n", " ")
    for line in logical.splitlines():
        if not _DISPATCH_RE.search(line):
            continue
        for raw in _ROLE_RE.findall(line):
            roles.update(part for part in raw.split("|") if part)
    return roles


def _routing_roles(root):
    cfg = yaml.safe_load((root / "config" / "routing.yaml").read_text(encoding="utf-8"))
    return set(cfg["dispatch"]["roles"])


def _skill_text(skill_dir):
    """SKILL.md plus everything under references/, the full protocol."""
    parts = [(skill_dir / "SKILL.md").read_text(encoding="utf-8")]
    refs = skill_dir / "references"
    if refs.is_dir():
        parts += [p.read_text(encoding="utf-8") for p in sorted(refs.rglob("*.md"))]
    return "\n".join(parts)


def _shingles(text, n=_SHINGLE):
    words = text.split()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _prose_files():
    return sorted(
        p for base in ("skills", "commands", "agents")
        for p in (REPO_ROOT / base).rglob("*.md")
    )


@pytest.mark.parametrize(
    "path", _prose_files(), ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_clavain_cross_references_resolve(path):
    """Every clavain:<name> reference names a skill, command or agent that exists."""
    bad = _unresolved_clavain_refs(
        path.read_text(encoding="utf-8"), _known_clavain_names(REPO_ROOT)
    )
    assert not bad, f"{path.relative_to(REPO_ROOT)} references missing: {bad}"


def test_cross_reference_check_catches_planted_stale_name():
    """Positive control: the stale name that once sat in subagent-driven-development
    (the real skill is intertest:test-driven-development) is flagged, real ones are not."""
    known = _known_clavain_names(REPO_ROOT)
    assert "interserve-engine" in known
    text = "use clavain:test-driven-development and clavain:interserve-engine"
    assert _unresolved_clavain_refs(text, known) == ["test-driven-development"]


COMPACT_DIRS = sorted(
    d for d in SKILL_DIRS if (d / "SKILL-compact.md").exists()
)


@pytest.mark.parametrize("skill_dir", COMPACT_DIRS, ids=lambda p: p.name)
def test_compact_skill_does_not_exceed_full(skill_dir):
    """The compact variant cites no skill, role or tier flag the full protocol lacks,
    and keeps the 'Enrolled measured work' section only if the full one has it."""
    compact = (skill_dir / "SKILL-compact.md").read_text(encoding="utf-8")
    full = _skill_text(skill_dir)
    extra_refs = set(_CLAVAIN_REF_RE.findall(compact)) - set(_CLAVAIN_REF_RE.findall(full))
    assert not extra_refs, f"{skill_dir.name} compact cites refs absent from full: {sorted(extra_refs)}"
    extra_roles = _fenced_roles(compact) - _fenced_roles(full)
    assert not extra_roles, f"{skill_dir.name} compact uses roles absent from full: {sorted(extra_roles)}"
    assert ("Enrolled measured work" in compact) == (
        "Enrolled measured work" in (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    ), f"{skill_dir.name}: 'Enrolled measured work' section differs between compact and full"


def test_compact_parity_check_is_not_vacuous():
    """Positive control: the parity set includes the skill with the richest
    compact/full pair, and the role parser finds roles in it."""
    names = {d.name for d in COMPACT_DIRS}
    assert "interserve-engine" in names
    assert "deep-execution" in _fenced_roles(
        (REPO_ROOT / "skills" / "interserve-engine" / "SKILL-compact.md").read_text(encoding="utf-8")
    )


def test_fenced_role_parser_handles_alternation():
    text = (
        "```bash\ndispatch.sh --role {scout|deep-execution} -s x\n"
        "bash dispatch.sh \\\n  --role validation\n"
        "pattern-f-verdict.sh --role executor\n```\n--role prose"
    )
    assert _fenced_roles(text) == {"scout", "deep-execution", "validation"}


@pytest.mark.parametrize(
    "path", _prose_files(), ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_fenced_dispatch_roles_exist_in_routing_policy(path):
    """Roles used with --role in code blocks are defined in config/routing.yaml."""
    unknown = _fenced_roles(path.read_text(encoding="utf-8")) - _routing_roles(REPO_ROOT)
    assert not unknown, (
        f"{path.relative_to(REPO_ROOT)} dispatches with undefined roles: {sorted(unknown)}"
    )


CODEX_DELEGATE_FILES = [
    REPO_ROOT / "skills" / "codex-delegate" / "SKILL.md",
    REPO_ROOT / "agents" / "workflow" / "codex-delegate.md",
]


@pytest.mark.parametrize(
    "path", CODEX_DELEGATE_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_codex_delegate_default_path_uses_role_not_tier(path):
    """Canon: --tier cannot satisfy role resolution, so codex-delegate's dispatch
    example must use --role (docs/canon/reasoning-routing.md)."""
    fenced = _fenced(path.read_text(encoding="utf-8"))
    assert "--tier" not in fenced, f"{path.name} dispatch example still uses --tier"
    assert "--role" in fenced, f"{path.name} dispatch example has no --role"


def test_codex_delegate_does_not_duplicate_interserve_enrolled_block():
    """The enrolled-dispatch protocol lives in interserve-engine only."""
    delegate = (REPO_ROOT / "skills" / "codex-delegate" / "SKILL.md").read_text(encoding="utf-8")
    engine = (REPO_ROOT / "skills" / "interserve-engine" / "SKILL.md").read_text(encoding="utf-8")
    shared = len(_shingles(delegate) & _shingles(engine))
    assert shared <= _MAX_SHARED_SHINGLES, (
        f"codex-delegate shares {shared} {_SHINGLE}-word runs with interserve-engine "
        f"(max {_MAX_SHARED_SHINGLES}); point to the engine instead of copying"
    )
    assert "task-delivery.py" not in delegate


def test_interop_with_gsd_uses_current_repo_names():
    """GSD moved to open-gsd/gsd-core; the plugin repo is buildomator/buildomator.
    The old locations may be named only as former names, never linked."""
    text = (REPO_ROOT / "skills" / "interop-with-gsd" / "SKILL.md").read_text(encoding="utf-8")
    assert "](https://github.com/gsd-build/get-shit-done" not in text
    assert "](https://github.com/jnuyens/gsd-plugin" not in text
    assert "https://github.com/open-gsd/gsd-core" in text
    assert "https://github.com/buildomator/buildomator" in text
