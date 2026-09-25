#!/usr/bin/env bash
# mk-zz4m: scripts/lib-dispatch-audit.sh's _classify_dispatch_failure text
# fallback must only map real capacity signals to rate_limited — since
# db2b24e, dispatch.sh walks the fallback chain on rate_limited (and records
# a same-lab reviewer as a capacity substitute on review roles), so a false
# positive silently switches the model and mislabels an auth failure as a
# capacity one. This drives the classifier function directly, in isolation
# from any actual dispatch/codex/claude invocation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$ROOT/scripts/lib-dispatch-audit.sh"

classify_text() {
  local text="$1" file="$TMP_ROOT/stderr.txt"
  printf '%s\n' "$text" > "$file"
  _classify_dispatch_failure "$file" 1
}

assert_class() {
  local label="$1" text="$2" want="$3" got
  got="$(classify_text "$text")"
  [[ "$got" == "$want" ]] || fail "$label: expected '$want', got '$got' for: $text"
}

# --- False positives from mk-zz4m: must NOT classify as rate_limited -------

assert_class "401 with x-ratelimit header (false positive)" \
  'HTTP 401 Unauthorized (x-ratelimit-remaining: 0)' terminal_configuration

assert_class "traceback line number 429 (false positive)" \
  'File "runner.py", line 429, in main' terminal_configuration

# invalid_api_key is itself a real auth signal (see the 401/403 block below),
# so this now correctly lands on terminal_configuration instead of
# rate_limited — the fix is that the "rate-limit docs" prose no longer wins.
assert_class "prose doc reference to rate-limit (false positive)" \
  'invalid_api_key; see rate-limit docs' terminal_configuration

echo "PASS: 401/traceback-429/doc-prose no longer misclassify as rate_limited"

# --- 401/403 map to a class that dispatch.sh's walk list never retries on --
# (scripts/dispatch.sh:675,680,808: only quota_exhausted, rate_limited,
# model_unavailable, account_access_absent, insufficient_codex_version and
# unsupported_adapter walk; terminal_policy and terminal_configuration do
# not, so both 401 and 403 must land there.)

assert_class "bare 401 Unauthorized" \
  '401 Unauthorized' terminal_configuration

assert_class "bare 403 Forbidden" \
  '403 Forbidden' terminal_policy

assert_class "403 with misalignment policy wording" \
  'HTTP 403 Forbidden: misalignment policy blocked request' terminal_policy

assert_class "invalid_api_key auth failure" \
  'Error: invalid_api_key — check your credentials' terminal_configuration

echo "PASS: 401 and 403 classify into non-walking classes"

# --- True positives: real capacity signals must still classify rate_limited

assert_class "codex exhausted-retries 429 (mk-nh6v real text)" \
  'exceeded retry limit, last status: 429 Too Many Requests' rate_limited

assert_class "codex stream error 429 (role-dispatch-test.sh fixture text)" \
  'stream error: unexpected status 429 Too Many Requests: rate limited' rate_limited

assert_class "claude structured rate_limit_error" \
  '{"type":"error","error":{"type":"rate_limit_error","message":"Number of request tokens has exceeded..."}}' rate_limited

assert_class "rate limit exceeded phrasing" \
  'Error: rate limit exceeded, please retry later' rate_limited

assert_class "hyphenated rate-limited adjective" \
  'Request was rate-limited by the upstream provider' rate_limited

# --- P2 follow-up (review findings 3, 4): widened real 429/rate-limit forms,
# the 401-before-429 ordering, and the traceback false positive surviving a
# status/http/code-named source file.

assert_class "HTTP/2 429 status line" \
  'HTTP/2 429' rate_limited

assert_class "HTTP/1.1 429 status line (digits in the version must not break the gap)" \
  '< HTTP/1.1 429' rate_limited

assert_class "Error 429: colon form" \
  'Error 429: too many requests from this key' rate_limited

assert_class "upstream responded 429" \
  'upstream responded 429' rate_limited

assert_class "OpenAI structured code field" \
  '{"error":{"code":"rate_limit_exceeded","message":"..."}}' rate_limited

assert_class "bare rate_limit_exceeded" \
  'rate_limit_exceeded' rate_limited

assert_class "Rate limit reached for phrasing" \
  'Rate limit reached for gpt-9 in organization org-abc' rate_limited

assert_class "Moonshot rate_limit_reached_error" \
  'moonshot: rate_limit_reached_error' rate_limited

assert_class "ratelimited with no space or hyphen" \
  'Request was ratelimited' rate_limited

echo "PASS: widened 429/rate-limit forms all classify rate_limited"

assert_class "401 message that also contains rate-limit-shaped prose (401 must win)" \
  '401 Unauthorized: invalid x-api-key (see rate limit exceeded FAQ)' terminal_configuration

assert_class "401 message with 'rate limited' adjective inline (401 must win)" \
  'Error code: 401 - unauthenticated clients are rate limited' terminal_configuration

echo "PASS: 401 check runs before the 429/rate-limit check"

assert_class "traceback line 429 with filename literally named status.py" \
  'File "/app/status.py", line 429, in main' terminal_configuration

assert_class "traceback line 429 with filename literally named http.py" \
  'File "/app/http.py", line 429, in main' terminal_configuration

assert_class "traceback line 429 with filename literally named code.py" \
  'File "/app/code.py", line 429, in main' terminal_configuration

echo "PASS: a traceback's 'line 429' never classifies rate_limited, even when the filename contains status/http/code"

echo "PASS: real 429/rate-limit signals still classify as rate_limited"

# --- Existing classes stay intact ------------------------------------------

assert_class "account access absent" \
  'The gpt-6-astra model is not supported when using Codex with a ChatGPT account.' account_access_absent

assert_class "model unavailable" \
  'Error: model_not_found: gpt-9-nonexistent' model_unavailable

got="$(_classify_dispatch_failure /dev/null 0)"
[[ "$got" == "success" ]] || fail "exit 0 did not classify as success: $got"

echo "PASS: unrelated classes (account_access_absent, model_unavailable, success) are unaffected"
