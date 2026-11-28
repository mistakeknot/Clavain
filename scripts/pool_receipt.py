"""Provider attempt accounting through the authenticated account-pool contract.

Host and scoped bearers remain in memory. Never include HTTP bodies or errors
in diagnostics: a server error is not trusted to be free of credentials.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def validate(data, attempt, provider="claude"):
    def require(condition):
        if not condition:
            raise ValueError("pool receipt lacks complete request-bound accounting")
    require(isinstance(data, dict))
    require(data.get("version") == 1 and data.get("attempt_id") == attempt and
            provider in ("claude", "codex") and data.get("provider") == provider and bool(data.get("host_id")) and
            isinstance(data.get("id"), str) and re.fullmatch(r"[a-f0-9]{32}", data["id"]))
    require(all(data.get(k) is True for k in ("sealed", "valid", "complete")))
    requests = data.get("requests")
    require(isinstance(requests, list) and 0 < len(requests) <= 128)
    totals = dict.fromkeys(FIELDS, 0)
    inference = False
    for i, request in enumerate(requests, 1):
        require(isinstance(request, dict) and request.get("id") == i and
                request.get("kind") in ("inference", "metadata") and request.get("state") == "finished")
        hops = request.get("hops")
        require(isinstance(hops, list) and 0 < len(hops) <= 32)
        # Account selection and authorization are enforced by the authenticated
        # pool server. Admission supplies no expected account ID; the client
        # validates attribution exists, not that an account was preselected.
        for j, hop in enumerate(hops, 1):
            require(isinstance(hop, dict) and hop.get("index") == j and
                    isinstance(hop.get("account_id"), str) and bool(hop["account_id"]) and
                    hop.get("provider") == provider and
                    type(hop.get("status")) is int and 200 <= hop["status"] < 300)
            usage = hop.get("usage")
            if request["kind"] == "metadata":
                # Aleph v1 attests metadata separately. It has no inference terminal.
                require(hop.get("state") == "unknown" and
                        "usage" in hop and usage is None and
                        "model" in hop and hop["model"] is None)
            else:
                require(hop.get("state") == "complete")
                inference = True
                require(isinstance(hop.get("model"), str) and bool(hop["model"]) and isinstance(usage, dict))
                require(set(usage) <= set(FIELDS) | {"cache_creation_5m_input_tokens", "cache_creation_1h_input_tokens"})
                for key in FIELDS:
                    value = usage.get(key)
                    require(type(value) is int and 0 <= value <= 2**53)
                    totals[key] += value
    require(inference)
    return totals


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args):
        return None


class PoolAttempt:
    def __init__(self, attempt, destination, provider="claude"):
        if provider not in ("claude", "codex"):
            raise ValueError("unsupported receipt provider")
        self.provider = provider
        self.token_env = "ANTHROPIC_AUTH_TOKEN" if provider == "claude" else "CODEX_POOL_AUTH_TOKEN"
        self.attempt = attempt
        self.destination = Path(destination)
        self.base = os.environ.get("ANTHROPIC_BASE_URL" if provider == "claude" else "CODEX_OPENAI_BASE_URL", "")
        if provider == "codex":
            if not self.base.endswith("/http/v1"):
                raise ValueError("invalid pool receipt origin")
            self.base = self.base[:-3]
        url = urlsplit(self.base)
        if (url.scheme not in ("http", "https") or not url.hostname or url.username or
                url.password or url.query or url.fragment or
                url.path != "/api/v1/plugins/account-pool/http" or
                (url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"))):
            raise ValueError("invalid pool receipt origin")
        self.host_token = os.environ.get(self.token_env, "")
        if not self.host_token or self.destination.exists() or self.destination.is_symlink():
            raise ValueError("pool receipt preflight unavailable")
        begin = self.request("begin", dict(version=1, provider=provider, attempt_id=attempt))
        if (not isinstance(begin, dict) or begin.get("version") != 1 or
                begin.get("attempt_id") != attempt or begin.get("provider") != provider or
                not isinstance(begin.get("id"), str) or not re.fullmatch(r"[a-f0-9]{32}", begin["id"]) or
                not begin.get("host_id") or not isinstance(begin.get("token"), str) or not begin["token"] or
                type(begin.get("expires_at")) is not int or begin["expires_at"] <= time.time()*1000):
            raise ValueError("invalid pool receipt admission")
        self.id, self.host, self.scoped = begin["id"], begin["host_id"], begin["token"]

    def request(self, action, payload):
        try:
            req = Request(self.base + "/receipts/" + action, data=json.dumps(payload).encode(),
                          headers={"x-bb-account-pool-token": self.host_token, "Content-Type": "application/json"})
            # Do not forward authentication through redirects or environment proxies.
            with build_opener(ProxyHandler({}), NoRedirect).open(req, timeout=5) as response:
                raw = response.read((2 << 20) + 1)
                if len(raw) > 2 << 20:
                    raise ValueError()
                return json.loads(raw)
        except Exception:
            raise ValueError("pool receipt service unavailable") from None

    def child_env(self):
        env = {k: v for k, v in os.environ.items() if v != self.host_token}
        env[self.token_env] = self.scoped
        return env

    def finish(self, totals):
        for _ in range(20):
            data = self.request("finalize", dict(version=1, id=self.id, attempt_id=self.attempt))
            if not isinstance(data, dict):
                raise ValueError("pool finalize response must be an object")
            if data.get("complete") is True:
                break
            time.sleep(.1)
        if data.get("id") != self.id or data.get("host_id") != self.host:
            raise ValueError("pool receipt identity changed")
        # Retain terminal evidence, including unknown spending, before validation.
        # Reject unexpected fields rather than risk persisting a secret-bearing body.
        if set(data) != {"version", "id", "host_id", "attempt_id", "provider", "sealed", "valid", "complete", "requests"}:
            raise ValueError("unexpected pool receipt fields")
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
        if self.host_token in encoded or self.scoped in encoded:
            raise ValueError("pool receipt contains authentication material")
        fd = os.open(self.destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write(encoded + "\n")
            out.flush()
            os.fsync(out.fileno())
        observed = validate(data, self.attempt, self.provider)
        if observed != totals:
            raise ValueError("pool request usage differs from provider totals")
        return {"path": str(self.destination), "sha256": hashlib.sha256((encoded + "\n").encode()).hexdigest(),
                "id": self.id, "attempt_id": self.attempt}


def check_ledger(path, attempt, provider="claude"):
    record = None
    with open(path) as ledger:
        for line in ledger:
            try:
                candidate = json.loads(line)
            except ValueError:
                continue
            if not isinstance(candidate, dict):
                continue
            ref = candidate.get("pool_receipt")
            # Claude usage records predate the distinct Codex terminal type.
            correlated = candidate.get("attempt_id") == attempt
            if provider == "claude" and isinstance(ref, dict):
                correlated = correlated or ref.get("attempt_id") == attempt
            if (correlated and ((provider == "claude" and candidate.get("terminal") is True) or
                                (provider == "codex" and candidate.get("type") == "pool.accounting"))):
                record = candidate
    if (not record or record.get("terminal") is not True or
            record.get("complete") is not True or record.get("status") != "success"):
        raise ValueError("missing successful correlated pool accounting")
    ref = record.get("pool_receipt")
    if not isinstance(ref, dict) or ref.get("attempt_id") != attempt:
        raise ValueError("missing correlated pool receipt reference")
    raw = Path(ref["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("pool evidence hash mismatch")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("id") != ref["id"] or validate(data, attempt, provider) != {k: record[k] for k in FIELDS}:
        raise ValueError("pool evidence does not reconcile")
    return ref


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-ledger", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--provider", choices=("claude", "codex"), default="claude")
    args = parser.parse_args()
    try:
        print(json.dumps(check_ledger(args.check_ledger, args.attempt, args.provider)))
    except (ValueError, OSError, KeyError, TypeError):
        print("pool request accounting unavailable or invalid", file=sys.stderr)
        sys.exit(1)
