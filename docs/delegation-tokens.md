# Scoped delegation with tokens (v2)

Auto-proceed authz v1.5 answers "is this op allowed right now?" by reading policy. v2 adds a second layer — opaque, signed, time-boxed **tokens** — that let a vetted agent grant scoped permission to another agent, or to a one-shot command, without loosening policy for anyone else. Tokens short-circuit the policy check when they match; policy still governs every token-less op.

**When to use a token**

- **Delegation.** Claude has vetted a change and wants Codex to ship it. Issue a token scoped to the exact op + target, pass it to Codex.
- **Scoped one-shot grant.** `ic publish --patch` for a single plugin after a bead landed — token lives for one command, no ambient permission.
- **Cross-session hand-off.** Sprint closed in session A; session B needs to push without re-running the vetting flow.

**Issue**

```bash
clavain-cli policy token issue --op=<op> --target=<t> --for=<agent> --ttl=60m
```

**Present — one-shot, preferred (no shell history leakage):**

```bash
CLAVAIN_AUTHZ_TOKEN=$(clavain-cli policy token issue --op=ic-publish-patch --target=my-plugin --for=claude --ttl=60m) \
  ic publish --patch
```

The env var lives only for this one command. Do NOT `export` it.

**Present — interactive, with eval-clear:** if the token genuinely needs to persist across several commands, use:

```bash
CLAVAIN_AUTHZ_TOKEN=<string>
# ... do the work ...
eval "$(clavain-cli policy token consume --token="$CLAVAIN_AUTHZ_TOKEN" --expect-op=... --expect-target=...)"
```

Output starts with a shell-comment JSON receipt containing `schema`, `status`, `op`, `target`, `audit_id`, and `signed`, followed by `# authz-unset-begin\nunset CLAVAIN_AUTHZ_TOKEN\n# authz-unset-end`. Validate the receipt and sentinels before eval-ing output from an untrusted binary. Gate wrappers require `jq` and reject any malformed exit-zero response.

**Delegate**

```bash
clavain-cli policy token delegate --from=<parent> --to=<child-agent> --ttl=<d>
```

Proof-of-possession required — `CLAVAIN_AGENT_ID` must equal the parent token's `agent_id`. Scope can never widen: `--op` and `--target` override flags are deliberately absent.

**Revoke**

```bash
clavain-cli policy token revoke --token=<id>             # revoke one
clavain-cli policy token revoke --cascade --token=<root> # revoke a root + all descendants
```

`--cascade` is refused on non-root tokens (see `canon/authz-token-model.md` for rationale).

**Audit**

```bash
clavain-cli policy token list   # delegation tree per root
```

Every consume writes a v1.5-shaped authorizations row with `vetting.via="token"`. The existing `policy audit --verify` continues to walk the signature chain; v2 doesn't change the signing model.

Full semantics: `canon/authz-token-model.md`.
