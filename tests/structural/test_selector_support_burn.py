"""Burn accounting normalization and explicit finite cost bounds."""
import pytest
from clavain_selector import burn
from support_helpers import isolation, require_netns  # noqa: F401

pytestmark = pytest.mark.usefixtures("isolation", "require_netns")

@pytest.fixture
def ledger(monkeypatch):
    monkeypatch.setattr(burn, "load_parsers", lambda *args: (lambda p: ([], [], []), lambda p: ([], [], []), "fixture"))
    class TranscriptWeights(dict):
        def __getitem__(self, key): pytest.fail("transcript weights reached Jev bound")
        def get(self, *args): pytest.fail("transcript weights reached Jev bound")
    monkeypatch.setattr(burn, "load_weights", lambda: TranscriptWeights(input_tokens=1., output_tokens=5.))
    return lambda **kwargs: burn.ledger([], "claude", **kwargs)["selector_overhead"]

def test_missing_weights(ledger):
    assert hasattr(burn, "accounting_from_record")
    result = ledger(selector_accounting=[])
    assert result["bound_reason"] == "no_weights"
    assert result["weighted_total"] is None

def test_empty_bounded(ledger):
    assert hasattr(burn, "accounting_from_record")
    result = ledger(selector_accounting=[], selector_weights={"input_tokens": 1, "output_tokens": 5, "source": "fixture"})
    assert result["bound"] == "bounded"
    assert result["weighted_total"] == 0.0

@pytest.mark.parametrize("value", [True, -1, 0, float("nan"), float("inf"), "1.0"])
def test_invalid_weights(ledger, value):
    assert hasattr(burn, "accounting_from_record")
    with pytest.raises(ValueError):
        ledger(selector_accounting=[], selector_weights={"input_tokens": value, "output_tokens": 1, "source": "fixture"})

def test_legacy_keyword(ledger):
    result = ledger(selector_usage=[{"input_tokens": 1, "output_tokens": 1}])
    assert result.get("complete") == "unknown"
    assert result["bound"] == "unbounded"

@pytest.mark.parametrize("counter", [True, -1, 1.0, "1", 2**40+1])
def test_invalid_legacy_counter(counter):
    assert hasattr(burn, "accounting_from_record")
    result = burn.accounting_from_record({"attempts": 1, "jev_usage": {"input_tokens": counter, "output_tokens": 1}})
    assert result["complete"] == "invalid"

@pytest.mark.parametrize("attempts,usage,complete", [(0,None,"unknown"),(1,None,False),(1,{"input_tokens":1,"output_tokens":2},True),(2,{"input_tokens":1,"output_tokens":2},False),(1,{"input_tokens":1},False)])
def test_legacy_rows(attempts,usage,complete):
    assert burn.accounting_from_record({"attempts":attempts,"jev_usage":usage})["complete"] == complete

def test_overflow_and_bound(ledger):
    complete = {"attempts":1,"jev_usage":{"input_tokens":2,"output_tokens":0}}
    weights = {"input_tokens":1e308,"output_tokens":1,"source":"fixture"}
    result = ledger(selector_accounting=[complete],selector_weights=weights)
    assert result["bound_reason"] == "non_finite"
    assert result["weighted_total"] is None
    assert not burn.cost_bound_passes(result)
    complete["jev_usage"] = {"input_tokens":1,"output_tokens":1}
    result = ledger(selector_accounting=[complete],selector_weights={**weights,"output_tokens":1e308})
    assert result["bound_reason"] == "non_finite"

def test_incomplete_precedes_weights(ledger):
    result = ledger(selector_accounting=[{"attempts":0}])
    assert result["bound_reason"] == "incomplete"
    assert not burn.cost_bound_passes(result)

def test_keywords_exclusive(ledger):
    with pytest.raises(ValueError): ledger(selector_accounting=[],selector_usage=[])

@pytest.mark.parametrize("version", ["1",True,1.0,2])
def test_record_versions(version):
    assert burn.accounting_from_record({"schema":"clavain.selector.decision","schema_version":version,"selector":{"attempts":0}})["complete"] == "invalid"
