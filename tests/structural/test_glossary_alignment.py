"""Keep glossary discovery and naming guidance aligned across entry points."""

import re

import pytest


WRITERS = (
    "commands/grill-me.md",
    "skills/engineering-docs/references/vocabulary-capture.md",
    "skills/engineering-docs/SKILL.md",
    "skills/engineering-docs/SKILL-compact.md",
)
READERS = (
    "commands/tdd.md",
    "skills/writing-plans/SKILL.md",
    "commands/describe-pr.md",
)


@pytest.mark.parametrize("relative", WRITERS + READERS)
def test_glossary_lookup_order(project_root, relative):
    text = (project_root / relative).read_text()
    paths = re.findall(r"`(docs/glossary\.md|GLOSSARY\.md|CONCEPTS\.md)`", text)
    assert paths[:3] == ["docs/glossary.md", "GLOSSARY.md", "CONCEPTS.md"]
    assert "workspace root" in text


@pytest.mark.parametrize("relative", WRITERS)
def test_glossary_creation_uses_docs_when_none_exists(project_root, relative):
    text = (project_root / relative).read_text()
    assert re.search(r"create `docs/glossary\.md`", text)
    assert not re.search(r"create `CONCEPTS\.md`", text)
    assert "Never start a second glossary" in text


@pytest.mark.parametrize("relative", READERS)
def test_naming_workflows_read_glossary_first(project_root, relative):
    text = (project_root / relative).read_text()
    assert "Read the glossary" in text
    boundary = {
        "commands/tdd.md": "Invoke the test-driven-development skill",
        "skills/writing-plans/SKILL.md": "Write `docs/plans/",
        "commands/describe-pr.md": "## Step 2: Analyze",
    }[relative]
    assert text.index("Read the glossary") < text.index(boundary)
