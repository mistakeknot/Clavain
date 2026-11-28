"""Authenticated pool evidence must survive dispatch without accepting guesses."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location("pool_receipt", ROOT / "scripts/pool_receipt.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipt():
    return dict(version=1, id="a" * 32, host_id="host-test", attempt_id="attempt-test",
                provider="claude", sealed=True, valid=True, complete=True,
                requests=[dict(id=1, kind="inference", state="finished", hops=[dict(
                    index=1, account_id="account-test", provider="claude", status=200,
                    state="complete", model="claude-opus-5-5", usage=dict(input_tokens=10,
                    output_tokens=9, cache_read_input_tokens=30, cache_creation_input_tokens=20))])])


def mixed_receipt():
    data = receipt()
    data['requests'].append(dict(id=2, kind='metadata', state='finished', hops=[dict(
        index=1, account_id='account-test', provider='claude', status=200,
        state='unknown', model=None, usage=None)]))
    return data


def test_metadata_contributes_nothing_to_the_four_inference_totals():
    assert load().validate(mixed_receipt(), 'attempt-test') == dict(
        input_tokens=10, output_tokens=9, cache_read_input_tokens=30,
        cache_creation_input_tokens=20)


@pytest.mark.parametrize('target, field, value', [
    ('request', 'kind', 'other'),
    ('request', 'kind', None),
    ('request', 'state', 'active'),
    ('request', 'state', 'error'),
    ('request', 'state', 'cancelled'),
    ('hop', 'state', 'complete'),
    ('hop', 'state', 'truncated'),
    ('hop', 'state', 'rejected'),
    ('hop', 'state', 'cancelled'),
    ('hop', 'state', 'transport_error'),
    ('hop', 'status', None),
    ('hop', 'status', 401),
    ('hop', 'status', 302),
    ('hop', 'account_id', ''),
    ('hop', 'provider', 'codex'),
    ('hop', 'usage', {}),
    ('hop', 'model', 'claude-opus-5-5'),
])
def test_rejects_invalid_metadata_in_an_otherwise_complete_receipt(target, field, value):
    data = mixed_receipt()
    request = data['requests'][1]
    record = request if target == 'request' else request['hops'][0]
    record[field] = value
    with pytest.raises(ValueError):
        load().validate(data, 'attempt-test')


@pytest.mark.parametrize('field', ['usage', 'model'])
def test_metadata_requires_explicit_nulls(field):
    data = mixed_receipt()
    del data['requests'][1]['hops'][0][field]
    with pytest.raises(ValueError):
        load().validate(data, 'attempt-test')


def test_metadata_only_is_not_accounting():
    data = mixed_receipt()
    data['requests'].pop(0)
    data['requests'][0]['id'] = 1
    with pytest.raises(ValueError):
        load().validate(data, 'attempt-test')


@pytest.mark.parametrize('kind', ['inference', 'metadata'])
def test_successful_retry_does_not_erase_a_prior_failed_hop(kind):
    data = mixed_receipt()
    request = next(r for r in data['requests'] if r['kind'] == kind)
    request['hops'][0]['index'] = 2
    request['hops'].insert(0, dict(index=1, account_id='prior-account', provider='claude',
                                   status=429, state='rejected', model=None, usage=None))
    with pytest.raises(ValueError):
        load().validate(data, 'attempt-test')


def test_accepts_real_request_account_and_usage():
    m = load()
    assert m.validate(receipt(), "attempt-test") == dict(input_tokens=10, output_tokens=9,
        cache_read_input_tokens=30, cache_creation_input_tokens=20)


@pytest.mark.parametrize("fault", ["account", "usage", "model", "retry", "attempt", "empty", "metadata", "active", "invalid"])
def test_rejects_incomplete_or_uncorrelated_evidence(fault):
    data = receipt()
    hop = data["requests"][0]["hops"][0]
    if fault in ("account", "usage", "model"):
        hop[{"account": "account_id"}.get(fault, fault)] = None
    elif fault == "retry":
        bad = copy.deepcopy(hop)
        bad.update(state="unknown", usage=None, status=429)
        data["requests"][0]["hops"].insert(0, bad)
    elif fault == "attempt": data["attempt_id"] = "another"
    elif fault == "empty": data["requests"] = []
    elif fault == "metadata": data["requests"][0]["kind"] = "metadata"
    elif fault == "active": data["requests"][0]["state"] = "active"
    elif fault == "invalid": data["valid"] = False
    with pytest.raises(ValueError): load().validate(data, "attempt-test")


def test_preflight_refusal_never_launches_or_persists_token(tmp_path, monkeypatch):
    m = load()
    calls = []
    def refused(*args):
        calls.append(args[1])
        raise ValueError("receipt service unavailable")
    monkeypatch.setattr(m.PoolAttempt, "request", refused)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1/api/v1/plugins/account-pool/http")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "synthetic-host-token")
    with pytest.raises(ValueError): m.PoolAttempt("attempt-test", tmp_path / "receipt.json")
    assert calls == ["begin"]
    assert not list(tmp_path.iterdir())


def test_scoped_child_token_and_sealed_evidence(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1/api/v1/plugins/account-pool/http")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "synthetic-host-token")
    def request(self, action, payload):
        if action == "begin":
            return dict(version=1, id="a"*32, host_id="host-test", attempt_id="attempt-test",
                        provider="claude", token="synthetic-scoped-token", expires_at=9999999999999)
        return receipt()
    monkeypatch.setattr(m.PoolAttempt, "request", request)
    path = tmp_path / "receipt.json"
    attempt = m.PoolAttempt("attempt-test", path)
    assert attempt.child_env()["ANTHROPIC_AUTH_TOKEN"] == "synthetic-scoped-token"
    assert "synthetic-host-token" not in attempt.child_env().values()
    attempt.finish(dict(input_tokens=10, output_tokens=9, cache_read_input_tokens=30, cache_creation_input_tokens=20))
    assert path.stat().st_mode & 0o777 == 0o600
    assert "synthetic-host-token" not in path.read_text()
    assert "synthetic-scoped-token" not in path.read_text()


def test_totals_must_reconcile(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1/api/v1/plugins/account-pool/http")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "synthetic-host-token")
    monkeypatch.setattr(m.PoolAttempt, "request", lambda self, action, payload:
        dict(version=1, id="a"*32, host_id="host-test", attempt_id="attempt-test", provider="claude",
             token="synthetic-scoped-token", expires_at=9999999999999) if action == "begin" else receipt())
    attempt = m.PoolAttempt("attempt-test", tmp_path / "receipt.json")
    with pytest.raises(ValueError): attempt.finish(dict(input_tokens=0))


def test_retained_evidence_cannot_be_replaced_or_rebound(tmp_path):
    import hashlib
    import json
    m = load()
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt()))
    ledger = tmp_path / 'usage.jsonl'
    record = dict(type='pool.accounting', attempt_id='attempt-test', terminal=True, complete=True, status='success', **m.validate(receipt(), 'attempt-test'),
                  pool_receipt=dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                    id='a'*32, attempt_id='attempt-test'))
    ledger.write_text(json.dumps(record)+'\n')
    assert m.check_ledger(ledger, 'attempt-test')['id'] == 'a'*32
    with pytest.raises(ValueError): m.check_ledger(ledger, 'another-attempt')
    path.write_text('{}')
    with pytest.raises(ValueError): m.check_ledger(ledger, 'attempt-test')


@pytest.mark.parametrize("noise", ['WARNING raw output', '{', '[]', 'null', '42', '"text"'])
def test_ledger_ignores_non_object_lines(tmp_path, noise):
    import hashlib, json
    m = load()
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt()))
    ref = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               id='a'*32, attempt_id='attempt-test')
    record = dict(type='pool.accounting', attempt_id='attempt-test', terminal=True,
                  complete=True, status='success', pool_receipt=ref,
                  **m.validate(receipt(), 'attempt-test'))
    ledger = tmp_path / 'ledger'
    ledger.write_text(noise+'\n'+json.dumps(record)+'\n')
    assert m.check_ledger(ledger, 'attempt-test') == ref


@pytest.mark.parametrize("provider", ["claude", "codex"])
@pytest.mark.parametrize("last", [
    dict(type='pool.accounting', attempt_id='attempt-test', terminal=True,
         complete=False, status='accounting_error'),
    dict(type='pool.accounting', attempt_id='attempt-test', terminal=True,
         complete=True, status='success'),
])
def test_last_terminal_cannot_fall_back_to_forged_reference(tmp_path, last, provider):
    import hashlib, json
    m = load()
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt()))
    data = receipt()
    data['provider'] = provider
    data['requests'][0]['hops'][0]['provider'] = provider
    path.write_text(json.dumps(data))
    forged = dict(type='pool.accounting', terminal=True, complete=True, status='success',
                  pool_receipt=dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                    id='a'*32, attempt_id='attempt-test'),
                  **m.validate(receipt(), 'attempt-test'))
    ledger = tmp_path / 'ledger'
    ledger.write_text(json.dumps(forged)+'\n'+json.dumps(last)+'\n')
    with pytest.raises(ValueError): m.check_ledger(ledger, 'attempt-test', provider)


def test_finalize_array_is_controlled_refusal(tmp_path, monkeypatch):
    m = load()
    attempt = object.__new__(m.PoolAttempt)
    monkeypatch.setattr(attempt, 'request', lambda *_: [])
    attempt.id, attempt.attempt = 'a'*32, 'attempt-test'
    with pytest.raises(ValueError, match='object'): attempt.finish({})


@pytest.mark.parametrize('fault', ['none', 'unverified-kind', 'receipt-id', 'attempt', 'totals'])
def test_ledger_revalidates_mixed_receipt_after_checking_its_hash(tmp_path, fault):
    data = mixed_receipt()
    if fault == 'unverified-kind':
        del data['requests'][1]['kind']
    elif fault == 'receipt-id':
        data['id'] = 'b' * 32
    elif fault == 'attempt':
        data['attempt_id'] = 'another-attempt'
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(data))
    ref = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               id='a' * 32, attempt_id='attempt-test')
    ledger = tmp_path / 'ledger.jsonl'
    ledger.write_text(json.dumps(dict(
        terminal=True, complete=True, status='success', pool_receipt=ref,
        input_tokens=10, output_tokens=9, cache_read_input_tokens=30,
        cache_creation_input_tokens=21 if fault == 'totals' else 20)) + '\n')
    if fault == 'none':
        assert load().check_ledger(ledger, 'attempt-test') == ref
    else:
        with pytest.raises(ValueError):
            load().check_ledger(ledger, 'attempt-test')
