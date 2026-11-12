"""Three-label response, request and provenance contract."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import pytest
from clavain_selector import egress, flags, jev_client as j
from support_helpers import isolation, require_netns, request_packet  # noqa: F401

pytestmark = pytest.mark.usefixtures("isolation", "require_netns")

def test_registry_inert_default():
    registry = flags.load_registry(Path(__file__).resolve().parents[2] / "config/selector-integrations.json")
    entry = registry["integrations"].get("support_check")
    assert entry is not None
    assert entry["enabled"] is False
    assert entry["session_budget"] == entry["daily_budget"] == 0
    assert flags.resolve_mode("support_check", {"CLAVAIN_SELECTOR_SUPPORT_CHECK": "shadow"}, registry).mode == "off"
    assert not flags.registry_errors(registry)
    entry["enabled"] = True
    assert flags.registry_errors(registry)

def answer(choice="supported", confidence=.9):
    return {"model": j.PINNED_MODEL, "answers": {"support": {"type": "choice", "choice": choice, "confidence": confidence, "probabilities": {k: (.8 if k == choice else .1) for k in ("supported", "not_supported", "unclear")}}}, "usage": {"input_tokens": 2, "output_tokens": 1}}

@pytest.mark.parametrize("choice", ["supported", "not_supported", "unclear"])
def test_label_response(choice):
    from clavain_selector import support
    result = support._validate_support_response(json.dumps(answer(choice)).encode())
    assert result.choice == choice

@pytest.mark.parametrize("counter", [True, -1, 1.0, 2**40+1, None])
def test_usage_response(counter):
    from clavain_selector import support
    raw = answer()
    raw["usage"]["input_tokens"] = counter
    with pytest.raises(support.SupportInvalid, match="usage"):
        support._validate_support_response(json.dumps(raw).encode())

@pytest.mark.parametrize("change", ["model", "extra_answer", "missing_answer", "probability_keys", "probability_sum", "choice", "unknown_choice", "type"])
def test_invalid_response(change):
    from clavain_selector import support
    raw = answer()
    a = raw["answers"]["support"]
    if change == "model": raw["model"] = "dummy-other-model"
    elif change == "extra_answer": raw["answers"]["select"] = {}
    elif change == "missing_answer": raw["answers"] = {}
    elif change == "probability_keys": a["probabilities"]["other"] = .1
    elif change == "probability_sum": a["probabilities"]["supported"] = .1
    elif change == "choice": a["choice"] = "not_supported"
    elif change == "unknown_choice": a["choice"] = "other"
    elif change == "type": a["type"] = "noul"
    with pytest.raises(support.SupportInvalid):
        support._validate_support_response(json.dumps(raw).encode())

def test_clean_admission(request_packet):
    assert hasattr(egress, "admit_support")
    admitted = egress.admit_support(request_packet)
    assert egress.verify(admitted)

def test_frozen_label_contract(request_packet):
    import jsonschema
    root = Path(__file__).resolve().parents[2]
    request_packet.update(json.loads((root / "tests/fixtures/selector/support-labels.json").read_text()))
    jsonschema.Draft202012Validator(json.loads((root / "schemas/selector-support-request.v1.schema.json").read_text())).validate(request_packet)
    assert egress.verify(egress.admit_support(request_packet))

@pytest.mark.parametrize("path", ["../outside", "/outside", "~/.config/jev/key", "bad\x00path"])
def test_path_grammar(request_packet, path):
    assert hasattr(egress, "admit_support")
    request_packet["sections"][0]["path"] = path
    refused = egress.admit_support(request_packet)
    assert refused.rule_ids == ("src.path_invalid",)

@pytest.mark.parametrize("kind", ["dirty", "untracked", "ignored", "symlink", "directory_symlink", "span", "hash", "revision"])
def test_revision_provenance(request_packet, kind):
    from clavain_selector import support
    root = Path(request_packet["project_root"])
    section = request_packet["sections"][0]
    expected = "src.not_at_revision"
    if kind == "dirty": (root / "source.md").write_text("Changed.\n")
    if kind in ("untracked", "ignored"):
        section["path"] = "other.md"
        (root / "other.md").write_text(section["text"])
        if kind == "ignored": (root / ".gitignore").write_text("other.md\n")
    if kind == "symlink":
        (root / "link.md").symlink_to("source.md")
        section["path"] = "link.md"
        expected = "src.symlink"
    if kind == "directory_symlink":
        (root / "link").symlink_to(root, target_is_directory=True)
        section["path"] = "link/source.md"
        expected = "src.symlink"
    if kind == "span": section["text"] = "Different"; expected = "span_text"
    if kind == "hash": section["sha256"] = "0" * 64; expected = "span_hash"
    if kind == "revision": request_packet["revision"] = "0" * 40; expected = "revision_mismatch"
    result = egress.admit_support(request_packet)
    assert result.rule_ids == (expected,)

@pytest.mark.parametrize("field", ["claim","section","description"])
def test_scan_and_size(request_packet,field):
    from clavain_selector import support
    # Scanning is checked after valid provenance. Descriptions and claims need
    # no source edit; section scanning is covered by the loaded-key fixture.
    if field == "section":
        request_packet["sections"][0]["text"] = "x" * 12001
    elif field == "claim":
        text="x" * 4001
        request_packet["claim"]={"text":text,"sha256":hashlib.sha256(text.encode()).hexdigest()}
    else:
        request_packet["label_descriptions"]["supported"] = "password=synthetic-dummy-value"
    result=egress.admit_support(request_packet)
    assert isinstance(result,egress.Refusal)
    assert result.rule_ids[0] == "size.over_limit" if field != "description" else result.rule_ids[0].startswith("cred.")

def git_fixture(packet,*args):
    import os
    return subprocess.check_output(["git","-C",packet["project_root"],*args],env={"PATH":"/usr/bin:/bin","HOME":str(Path(packet["project_root"]).parent),"GIT_CONFIG_GLOBAL":"/dev/null","GIT_CONFIG_NOSYSTEM":"1"}).decode().strip()

@pytest.mark.parametrize("kind",["tracked_symlink","gitlink","crlf"])
def test_git_modes_and_filters(request_packet,kind):
    root=Path(request_packet["project_root"])
    expected="src.not_at_revision"
    if kind == "tracked_symlink":
        (root/"link.md").symlink_to("source.md")
        git_fixture(request_packet,"add","link.md")
        request_packet["sections"][0]["path"]="link.md"
        expected="src.symlink"
    elif kind == "gitlink":
        # Keep readable worktree bytes so the tree-mode check is reached.
        (root/"module").write_text(request_packet["sections"][0]["text"])
        git_fixture(request_packet,"update-index","--add","--cacheinfo",f"160000,{request_packet['revision']},module")
        request_packet["sections"][0]["path"]="module"
    else:
        (root/".gitattributes").write_text("source.md text eol=crlf\n")
        (root/"source.md").write_bytes(b"First line.\r\nSecond line.\r\n")
        git_fixture(request_packet,"add","source.md",".gitattributes")
    git_fixture(request_packet,"commit","-qm","Fixture mode")
    request_packet["revision"]=git_fixture(request_packet,"rev-parse","HEAD")
    result=egress.admit_support(request_packet)
    assert result.rule_ids == (expected,)

def test_symlink_swap(monkeypatch,request_packet):
    from clavain_selector import support
    root=Path(request_packet["project_root"])
    target=root/"source.md"
    (root/"other.md").write_bytes(target.read_bytes())
    real_open=support.os.open
    def swap(path,*args,**kwargs):
        if path == target:
            target.unlink()
            target.symlink_to("other.md")
        return real_open(path,*args,**kwargs)
    monkeypatch.setattr(support.os,"open",swap)
    result=egress.admit_support(request_packet)
    assert result.rule_ids == ("src.target_changed",)

def test_unowned_and_missing_root(request_packet):
    git_fixture(request_packet,"remote","set-url","origin","https://github.com/unowned/support-fixture.git")
    assert egress.admit_support(request_packet).rule_ids == ("proj.unowned",)
    del request_packet["project_root"]
    assert egress.admit_support(request_packet).rule_ids == ("src.provenance_unavailable",)

def test_env_source_refused(request_packet):
    root=Path(request_packet["project_root"])
    (root/".env").write_text("dummy fixture\n")
    request_packet["sections"][0]["path"]=".env"
    assert egress.admit_support(request_packet).rule_ids == ("src.denylisted_path",)

def test_non_repository_source_refused(request_packet,tmp_path):
    root=tmp_path/"nongit"
    root.mkdir()
    request_packet["project_root"]=str(root)
    result=egress.admit_support(request_packet)
    assert isinstance(result,egress.Refusal)
    assert result.outcome == "refused"
    assert result.rule_ids == ("src.provenance_unavailable",)

@pytest.mark.parametrize("object_kind", ["blob", "commit"])
def test_replace_refs_cannot_substitute_revision_bytes(request_packet,object_kind):
    root=Path(request_packet["project_root"])
    original=git_fixture(request_packet,"rev-parse",request_packet["revision"]+":source.md")
    text="Replacement bytes.\n"
    (root/"source.md").write_text(text)
    if object_kind == "commit":
        original=request_packet["revision"]
        git_fixture(request_packet,"add","source.md")
        tree=git_fixture(request_packet,"write-tree")
        replacement=git_fixture(request_packet,"commit-tree",tree,"-p",original,"-m","Fixture replacement")
    else:
        replacement=git_fixture(request_packet,"hash-object","-w","source.md")
    git_fixture(request_packet,"replace",original,replacement)
    request_packet["sections"][0].update(text=text,sha256=hashlib.sha256(text.encode()).hexdigest())
    result=egress.admit_support(request_packet)
    assert isinstance(result,egress.Refusal)
    assert result.rule_ids == ("src.not_at_revision",)
