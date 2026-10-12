"""Check the figures stated in docs/wiki against the code."""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "docs" / "wiki" / "src"


def page(name):
    return (WIKI / name).read_text()


def bold_numbers(text):
    return [int(n) for n in re.findall(r"\*\*(\d+)\*\*", text)]


def test_summary_links_resolve():
    summary = page("SUMMARY.md")
    links = re.findall(r"\]\(([^)]+\.md)\)", summary)
    assert links
    for link in links:
        assert (WIKI / link).is_file(), link


def test_version_matches_manifest():
    version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    assert f"**{version}**" in page("introduction.md")


def test_skill_count_and_skill_md():
    dirs = [d for d in (ROOT / "skills").iterdir() if d.is_dir()]
    assert bold_numbers(page("skills.md")) == [len(dirs)]
    for d in dirs:
        assert (d / "SKILL.md").is_file(), d.name


def test_named_skills_exist():
    names = set(re.findall(r"`([a-z][a-z0-9-]+)`", page("skills.md")))
    existing = {d.name for d in (ROOT / "skills").iterdir() if d.is_dir()}
    assert len(names) >= 10
    assert names <= existing, names - existing


def test_command_file_count():
    files = [f for f in (ROOT / "commands").iterdir() if f.is_file()]
    assert bold_numbers(page("commands.md")) == [len(files)]


def test_named_commands_exist():
    cmds = re.findall(r"`/([a-z0-9-]+)`", page("commands.md"))
    assert len(cmds) >= 10
    for cmd in cmds:
        assert (ROOT / "commands" / f"{cmd}.md").is_file(), cmd


def test_hook_events_and_script_count():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    text = page("hooks.md")
    scripts = list((ROOT / "hooks").glob("*.sh"))
    assert bold_numbers(text) == [len(hooks), len(scripts)]
    for event in hooks:
        assert f"`{event}`" in text
    stated = dict(re.findall(r"`([A-Za-z]+)` (\d+)\b", text))
    assert stated == {e: str(len(v)) for e, v in hooks.items()}


def test_routing_sections_and_strikes():
    cfg = yaml.safe_load((ROOT / "config" / "routing.yaml").read_text())
    text = page("routing.md")
    assert bold_numbers(text) == [len(cfg), cfg["reasoning"]["strikes"]]
    for section in cfg:
        assert f"`{section}`" in text
    stated_models = set(re.findall(r"`((?:gpt|claude)-[a-z0-9.-]+)`", text))
    assert stated_models == set(cfg["reasoning"]["frontier_models"])
    assert "five frontier reasons" in text
    assert len(cfg["reasoning"]["frontier_reasons"]) == 5
