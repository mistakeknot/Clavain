#!/usr/bin/env bash
# lib-context-reset.sh — observe-mode context-reset hygiene telemetry (mk-42j9.40).
#
# NOT A SECURITY BOUNDARY. This library detects when a context epoch has read
# untrusted content (web, remote commands, MCP, browser) and when an
# approval-gated action (push, PR, release, publication, destructive override)
# runs, and records what a context-reset rule *would* have done. Every verdict
# is "allow". Nothing blocks, nothing is enforced, no reset is performed or
# requested, and the store under $CLAVAIN_CONTEXT_RESET_DIR is plain,
# unauthenticated JSON that any local process can edit. Enforcement modes need
# origin tagging and attestation, deferred to mk-42j9.42.
#
# Environment:
#   CLAVAIN_CONTEXT_RESET_CONFIG  config path (default config/context-reset.yaml)
#   CLAVAIN_CONTEXT_RESET_MODE    overrides config `mode` (observe|off)
#   CLAVAIN_CONTEXT_RESET_DIR     store (default ~/.clavain/context-reset)
#   CLAVAIN_CONTEXT_RESET_NOW     clock override in epoch seconds (tests)
#   CLAVAIN_DISPATCH_ROLE         role label for rows (default interactive)
#   BB_THREAD_ID                  thread label for rows

[[ -n "${_LIB_CONTEXT_RESET_LOADED:-}" ]] && return 0
_LIB_CONTEXT_RESET_LOADED=1

_CR_LIBDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || _CR_LIBDIR="."
CR_ROOT="${CLAUDE_PLUGIN_ROOT:-$_CR_LIBDIR/..}"

IC_LOG_COMPONENT="${IC_LOG_COMPONENT:-context-reset}"
if [[ -f "$_CR_LIBDIR/lib-log.sh" ]]; then
    # shellcheck source=hooks/lib-log.sh
    source "$_CR_LIBDIR/lib-log.sh" 2>/dev/null || true
fi
if ! declare -F log_error >/dev/null 2>&1; then
    log_error() { printf 'context-reset error: %s\n' "$1" >&2; }
fi
if ! declare -F log_warn >/dev/null 2>&1; then
    log_warn() { printf 'context-reset warning: %s\n' "$1" >&2; }
fi

_CR_KW='(push|publish|release|deploy|merge)'
_CR_ASSIGN='^[A-Za-z_][A-Za-z0-9_]*='
_CR_HOST_RE='^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.?$'

# ─── Config ──────────────────────────────────────────────────────────────

cr_config_file() {
    printf '%s' "${CLAVAIN_CONTEXT_RESET_CONFIG:-$CR_ROOT/config/context-reset.yaml}"
}

# cr_config_get KEY DEFAULT — flat `key: value` lookup; strips comments and quotes.
cr_config_get() {
    local key="$1" def="${2:-}" file line val
    file=$(cr_config_file)
    if [[ ! -r "$file" ]]; then printf '%s' "$def"; return 0; fi
    line=$(grep -E "^${key}:" "$file" 2>/dev/null | head -n 1) || line=""
    if [[ -z "$line" ]]; then printf '%s' "$def"; return 0; fi
    val="${line#*:}"
    val=$(printf '%s' "$val" | sed -e 's/[[:space:]]#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
        -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/") || val=""
    [[ -n "$val" ]] || val="$def"
    printf '%s' "$val"
    return 0
}

cr_config_int() {
    local v
    v=$(cr_config_get "$1" "$2")
    [[ "$v" =~ ^[0-9]+$ ]] || v="$2"
    printf '%s' "$v"
}

cr_config_float() {
    local v
    v=$(cr_config_get "$1" "$2")
    [[ "$v" =~ ^[0-9]+(\.[0-9]+)?$ ]] || v="$2"
    printf '%s' "$v"
}

cr_mode() {
    local m="${CLAVAIN_CONTEXT_RESET_MODE:-}"
    [[ -n "$m" ]] || m=$(cr_config_get mode observe)
    m=$(printf '%s' "$m" | tr '[:upper:]' '[:lower:]')
    printf '%s' "${m:-observe}"
}

# cr_should_record_for PAYLOAD — 0 when this phase records (observe), 1 otherwise.
# approval/full are not built: they log an error at SessionStart and record
# nothing. Never blocks anything.
cr_should_record_for() {
    local payload="${1:-}" mode event
    mode=$(cr_mode)
    case "$mode" in
        observe) return 0 ;;
        off) return 1 ;;
    esac
    event=$(printf '%s' "$payload" | jq -r 'if type == "object" then
            (if (.hook_event_name // "") != "" then .hook_event_name
             elif ((.tool_name // "") == "" and (.source // "") != "") then "SessionStart"
             else "" end)
        else "" end' 2>/dev/null) || event=""
    if [[ "$event" == "SessionStart" ]]; then
        log_error "context-reset: mode '$mode' is not implemented in this phase (observe-mode hygiene telemetry only, NOT a security boundary; enforcement requires mk-42j9.42); recording disabled, nothing blocked"
    fi
    return 1
}

# ─── Small utilities ─────────────────────────────────────────────────────

cr_now() {
    local n="${CLAVAIN_CONTEXT_RESET_NOW:-}"
    if [[ "$n" =~ ^[0-9]+$ ]]; then printf '%s' "$n"; else date +%s; fi
}

cr_role() { printf '%s' "${CLAVAIN_DISPATCH_ROLE:-interactive}"; }

cr_store_dir() { printf '%s' "${CLAVAIN_CONTEXT_RESET_DIR:-${HOME:-.}/.clavain/context-reset}"; }

# cr_hash TEXT — 16 hex chars; lets rows reference a tool call without storing it.
cr_hash() {
    local h=""
    if command -v sha256sum >/dev/null 2>&1; then
        h=$(printf '%s' "${1:-}" | sha256sum 2>/dev/null) || h=""
    elif command -v shasum >/dev/null 2>&1; then
        h=$(printf '%s' "${1:-}" | shasum -a 256 2>/dev/null) || h=""
    fi
    h="${h%% *}"
    printf '%s' "${h:0:16}"
}

cr_safe_id() {
    local s
    s=$(printf '%s' "${1:-}" | tr -c 'A-Za-z0-9._-' '_')
    s="${s:0:128}"
    if [[ -z "$s" || "$s" == "." || "$s" == ".." ]]; then s="unknown-session"; fi
    printf '%s' "$s"
}

# cr_url_host URL — host only (no scheme, userinfo, port, path, query). Input
# that could carry credentials into the host (an `@` in the path, a non-numeric
# port, characters outside a hostname) yields the sentinel `ambiguous-host`, so
# the unstripped part of a URL is never logged.
cr_url_host() {
    local u="${1:-}" auth path host port
    if [[ "$u" == *://* ]]; then u="${u#*://}"; fi
    auth="${u%%[/?#]*}"
    path="${u:${#auth}}"
    path="${path%%[?#]*}"
    if [[ "$auth" == *@* ]]; then
        auth="${auth##*@}"
    elif [[ "$path" == *@* ]]; then
        printf 'ambiguous-host'
        return 0
    fi
    [[ -n "$auth" ]] || return 0
    auth=$(printf '%s' "$auth" | tr '[:upper:]' '[:lower:]')
    if [[ "$auth" == \[* ]]; then
        host="${auth%%]*}"
        host="${host#\[}"
        port="${auth#*]}"
        if [[ ! "$host" =~ ^[0-9a-f:.]+$ || ! "$port" =~ ^(:[0-9]*)?$ ]]; then
            printf 'ambiguous-host'
            return 0
        fi
    else
        host="${auth%%:*}"
        port=""
        if [[ "$auth" == *:* ]]; then port="${auth#*:}"; fi
        if [[ ! "$port" =~ ^[0-9]*$ || ! "$host" =~ $_CR_HOST_RE ]]; then
            printf 'ambiguous-host'
            return 0
        fi
    fi
    printf '%s' "$host"
}

_cr_is_local_host() {
    case "${1:-}" in
        ""|localhost|0.0.0.0|::1|127.*|10.*|192.168.*|*.localhost|*.local|*.internal|*.ts.net) return 0 ;;
    esac
    return 1
}

# ─── Payload ─────────────────────────────────────────────────────────────

_CR_PARSE_JQ='
def s: if . == null then "" elif type == "string" then . else tojson end | gsub("[\n\r\u001f]"; " ");
if type != "object" then error("payload is not an object") else . end
| (.tool_input | if type == "object" then . else {} end) as $ti
| [ (.session_id | s), (.hook_event_name | s), (.tool_name | s),
    (($ti.skill // $ti.name) | s), (.transcript_path | s), (.agent_id | s),
    (.source | s), ($ti.url | s), ($ti.query | s), ($ti | tojson | s) ]
| join("\u001f")'

# cr_parse_payload PAYLOAD — sets CR_* globals; 1 when the payload is unusable.
cr_parse_payload() {
    local payload="${1:-}" line
    CR_SID="" CR_EVENT="" CR_TOOL="" CR_SKILL="" CR_TRANSCRIPT="" CR_AGENT=""
    CR_SOURCE="" CR_URL="" CR_QUERY="" CR_INPUT="" CR_CMD="" CR_REF="" CR_HOST=""
    line=$(printf '%s' "$payload" | jq -r "$_CR_PARSE_JQ" 2>/dev/null) || return 1
    [[ -n "$line" ]] || return 1
    IFS=$'\x1f' read -r CR_SID CR_EVENT CR_TOOL CR_SKILL CR_TRANSCRIPT CR_AGENT \
        CR_SOURCE CR_URL CR_QUERY CR_INPUT <<<"$line"
    if [[ "$CR_TOOL" == "Bash" ]]; then
        CR_CMD=$(printf '%s' "$payload" | jq -r '(.tool_input | if type == "object" then .command else null end) // ""
            | if type == "string" then . else tojson end' 2>/dev/null) || CR_CMD=""
    fi
    CR_REF=$(cr_hash "$CR_TOOL|$CR_INPUT")
    if [[ -n "$CR_URL" ]]; then CR_HOST=$(cr_url_host "$CR_URL"); fi
    return 0
}

# ─── Command classification (Bash) ───────────────────────────────────────
# Heuristic, quote-aware tokenizing only. It is not a full shell parser and it
# is NOT a security boundary: unresolved forms are counted as coverage gaps,
# never as clean.

# The tokenizer prints one line per simple command, words joined by \037. It
# honours quotes and escapes, splits on ; | & ( ) ` $( and newlines outside
# quotes, keeps redirections such as 2>&1 whole, drops comments and skips
# here-document bodies. A final \036 line marks input with an unterminated quote.
_CR_TOK_AWK='
function flushw() {
    if (hw) {
        gsub(/[\n\r]/, " ", w)
        gsub(US, " ", w)
        ln = (nw > 0) ? ln US w : w
        nw++
    }
    w = ""; hw = 0
}
function flushs() {
    flushw()
    if (nw > 0) print ln
    ln = ""; nw = 0
}
function push(k, r) { sp++; sk[sp] = k; sr[sp] = r }
function skiphd(p,    k, rest, e, l) {
    for (k = 1; k <= hn; k++) {
        while (p <= n) {
            rest = substr(s, p)
            e = index(rest, "\n")
            if (e == 0) { l = rest; p = n + 1 } else { l = substr(rest, 1, e - 1); p += e }
            if (hs[k]) sub(/^\t+/, "", l)
            if (l == hd[k]) break
        }
    }
    hn = 0
    return p
}
BEGIN { RS = "\001"; US = "\037"; SQ = "\047"; DQ = "\"" }
{
    s = $0; n = length(s); q = ""; sp = 0; hn = 0; amb = 0; w = ""; hw = 0; ln = ""; nw = 0
    i = 1
    while (i <= n) {
        c = substr(s, i, 1)
        if (q == SQ) {
            if (c == SQ) q = ""; else w = w c
            i++; continue
        }
        if (c == "\\") {
            d = substr(s, i + 1, 1)
            if (d == "\n") { i += 2; continue }
            if (q == DQ && index("$`\"\\", d) == 0) w = w c
            w = w d; hw = 1; i += 2; continue
        }
        if (q == DQ) {
            if (c == DQ) { q = ""; i++; continue }
            if (c == "$" && substr(s, i + 1, 1) == "(") { push("p", DQ); q = ""; flushs(); i += 2; continue }
            if (c == "`") { push("b", DQ); q = ""; flushs(); i++; continue }
            w = w c; i++; continue
        }
        if (c == SQ || c == DQ) { q = c; hw = 1; i++; continue }
        if (c == "#" && !hw) {
            e = index(substr(s, i), "\n")
            if (e == 0) i = n + 1; else i += e - 1
            continue
        }
        if (c == " " || c == "\t" || c == "\r") { flushw(); i++; continue }
        if (c == "\n") { flushs(); i++; if (hn > 0) i = skiphd(i); continue }
        if (c == "<" && substr(s, i + 1, 2) == "<<") { w = w "<<<"; hw = 1; i += 3; continue }
        if (c == "<" && substr(s, i + 1, 1) == "<") {
            flushw()
            i += 2; strip = 0
            if (substr(s, i, 1) == "-") { strip = 1; i++ }
            while (substr(s, i, 1) == " " || substr(s, i, 1) == "\t") i++
            dl = ""
            while (i <= n) {
                d = substr(s, i, 1)
                if (d == SQ || d == DQ) {
                    e = index(substr(s, i + 1), d)
                    if (e == 0) { amb = 1; i = n + 1; break }
                    dl = dl substr(s, i + 1, e - 1); i += e + 1; continue
                }
                if (d == "\\") { dl = dl substr(s, i + 1, 1); i += 2; continue }
                if (index(" \t\n;|&()<>`", d) > 0) break
                dl = dl d; i++
            }
            if (dl != "") { hn++; hd[hn] = dl; hs[hn] = strip } else amb = 1
            continue
        }
        if (c == "$" && substr(s, i + 1, 1) == "(") { push("p", ""); flushs(); i += 2; continue }
        if (c == "(") { push("p", ""); flushs(); i++; continue }
        if (c == ")") { if (sp > 0 && sk[sp] == "p") { q = sr[sp]; sp-- } flushs(); i++; continue }
        if (c == "`") {
            if (sp > 0 && sk[sp] == "b") { q = sr[sp]; sp-- } else push("b", "")
            flushs(); i++; continue
        }
        if (c == ";" || c == "|") { flushs(); i++; continue }
        if (c == "&") {
            if (substr(s, i + 1, 1) == ">" || (i > 1 && (substr(s, i - 1, 1) == ">" || substr(s, i - 1, 1) == "<"))) { w = w c; hw = 1; i++; continue }
            flushs(); i++; continue
        }
        w = w c; hw = 1; i++
    }
    if (q != "") amb = 1
    flushs()
    if (amb) print "\036"
}'

_cr_tokenize() {
    printf '%s' "${1:-}" | LC_ALL=C awk "$_CR_TOK_AWK" 2>/dev/null
}

# _cr_legacy_tokenize CMD — the quote-blind split, used only as an extra pass
# over ambiguous input (unterminated quotes, or no awk) so nothing is missed.
_cr_legacy_tokenize() {
    local seg old_ifs
    local -a ws
    while IFS= read -r seg; do
        seg="${seg//\"/}"
        seg="${seg//\'/}"
        ws=()
        IFS=$' \t' read -ra ws <<<"$seg" || true
        [[ ${#ws[@]} -gt 0 ]] || continue
        old_ifs="$IFS"
        IFS=$'\x1f'
        printf '%s\n' "${ws[*]}"
        IFS="$old_ifs"
    done < <(printf '%s\n' "${1:-}" | tr ';|&()`' '\n\n\n\n\n\n')
    return 0
}

_cr_any() {
    local a t
    for a in ${_CR_A[@]+"${_CR_A[@]}"}; do
        for t in "$@"; do
            if [[ "$a" == "$t" ]]; then return 0; fi
        done
    done
    return 1
}

_cr_any_re() {
    local a
    for a in ${_CR_A[@]+"${_CR_A[@]}"}; do
        if [[ "$a" =~ $1 ]]; then return 0; fi
    done
    return 1
}

# _cr_positional [OPTS-WITH-VALUE...] — fill _CR_P with non-option args of _CR_A.
_cr_positional() {
    _CR_P=()
    local j=0 na=${#_CR_A[@]} a t skip
    while (( j < na )); do
        a="${_CR_A[j]}"
        if [[ "$a" == -* ]]; then
            skip=0
            for t in "$@"; do
                if [[ "$a" == "$t" ]]; then skip=1; fi
            done
            j=$((j + 1 + skip))
        else
            _CR_P+=("$a")
            j=$((j + 1))
        fi
    done
    return 0
}

_cr_git() {
    local j=0 na=${#_CR_A[@]} sub="" k
    while (( j < na )); do
        case "${_CR_A[j]}" in
            -C|-c|--git-dir|--work-tree|--namespace|--exec-path|--config-env) j=$((j + 2)) ;;
            -*) j=$((j + 1)) ;;
            *) sub="${_CR_A[j]}"; break ;;
        esac
    done
    case "$sub" in
        push)
            if ! _cr_any --dry-run -n; then _cr_s_fam=remote-source-change; fi ;;
        send-email) _cr_s_fam=external-publication ;;
        reset)
            if _cr_any --hard; then _cr_s_fam=destructive-override; fi ;;
        clean)
            if { _cr_any --force || _cr_any_re '^-[a-zA-Z]*f[a-zA-Z]*$'; } \
                && ! _cr_any --dry-run && ! _cr_any_re '^-[a-zA-Z]*n[a-zA-Z]*$'; then
                _cr_s_fam=destructive-override
            fi ;;
        ""|add|am|apply|archive|bisect|blame|branch|cat-file|check-ignore|checkout|cherry-pick|clone\
        |commit|config|describe|diff|fetch|for-each-ref|format-patch|gc|grep|help|init|log|ls-files\
        |ls-remote|ls-tree|merge|merge-base|mv|name-rev|notes|pull|rebase|reflog|remote|restore\
        |rev-list|rev-parse|revert|rm|shortlog|show|show-ref|stash|status|submodule|switch\
        |symbolic-ref|tag|update-index|var|version|worktree) ;;
        *)
            # Unknown subcommand (alias, or options this parser misread) followed
            # by a bare `push`: count a gap rather than a silent pass.
            for ((k = j + 1; k < na; k++)); do
                if [[ "${_CR_A[k]}" == push ]]; then _cr_s_gap=unrecognized-git-subcommand; break; fi
            done ;;
    esac
    return 0
}

_cr_gh_api() {
    local j na=${#_CR_A[@]} a method="" data=0 graphql=0 mut=0
    for ((j = 0; j < na; j++)); do
        a="${_CR_A[j]}"
        case "$a" in
            -X|--method) method="${_CR_A[j+1]:-}" ;;
            -X*) method="${a#-X}" ;;
            --method=*) method="${a#--method=}" ;;
            -f|-F|--field|--raw-field|--input|-f*|-F*|--field=*|--raw-field=*|--input=*) data=1 ;;
            graphql) graphql=1 ;;
        esac
        if [[ "$a" == *mutation* ]]; then mut=1; fi
    done
    if (( graphql )); then
        if (( mut )); then _cr_s_fam=external-publication; else _cr_s_exp=remote-command; fi
    elif [[ -n "$method" ]]; then
        case "$method" in
            GET|get|Get|HEAD|head|Head) _cr_s_exp=remote-command ;;
            *) _cr_s_fam=external-publication ;;
        esac
    elif (( data )); then
        _cr_s_fam=external-publication
    else
        _cr_s_exp=remote-command
    fi
    if [[ "$_cr_s_exp" == remote-command ]]; then _cr_s_host=api.github.com; fi
    return 0
}

_cr_gh() {
    _cr_positional -R --repo
    local g1="${_CR_P[0]:-}" g2="${_CR_P[1]:-}"
    if [[ "$g1" == api ]]; then _cr_gh_api; return 0; fi
    case "$g1 $g2" in
        "pr create"|"pr merge") _cr_s_fam=pr-publication ;;
        "release create"|"release upload"|"release edit"|"release delete") _cr_s_fam=release ;;
        "issue create"|"issue comment"|"issue edit"|"issue close"|"issue reopen"|"issue delete"|"issue transfer"\
        |"pr comment"|"pr edit"|"pr close"|"pr reopen"|"pr review"|"pr ready"\
        |"repo create"|"repo delete"|"repo edit"|"repo rename"|"repo archive"|"repo fork"\
        |"gist create"|"gist edit"|"gist delete"|"secret set"|"secret delete"\
        |"variable set"|"variable delete"|"workflow run"|"label create"|"label edit"|"label delete")
            _cr_s_fam=external-publication ;;
        "issue view"|"issue list"|"pr view"|"pr list"|"pr diff"|"pr checks"|"repo view"\
        |"release view"|"release list"|"gist view"|"search "*)
            _cr_s_exp=remote-command; _cr_s_host=github.com ;;
    esac
    return 0
}

_cr_http() {
    local exe="$1" a v j na=${#_CR_A[@]} host="" pub=0 method="" urlopt=0 dyn=0
    for ((j = 0; j < na; j++)); do
        a="${_CR_A[j]}"
        if [[ "$a" == *'$'* ]]; then dyn=1; fi
        case "$a" in
            --url|--url=*)
                urlopt=1
                if [[ "$a" == --url ]]; then v="${_CR_A[j+1]:-}"; else v="${a#--url=}"; fi
                if [[ -z "$host" && -n "$v" && "$v" != *'$'* ]]; then host=$(cr_url_host "$v"); fi ;;
            *://*) if [[ -z "$host" ]]; then host=$(cr_url_host "$a"); fi ;;
            -X|--request|--method) method="${_CR_A[j+1]:-}" ;;
            -X*) method="${a#-X}" ;;
            --request=*|--method=*) method="${a#*=}" ;;
            -d|-d*|--data|--data-*|--data=*|-F|--form|--form-*|-T|--upload-file|--json|--post-data|--post-data=*|--post-file|--post-file=*)
                pub=1 ;;
        esac
    done
    if [[ "$exe" == http || "$exe" == https || "$exe" == xh ]]; then
        _cr_positional
        case "${_CR_P[0]:-}" in
            POST|PUT|PATCH|DELETE|post|put|patch|delete) pub=1 ;;
        esac
    fi
    if [[ -z "$host" ]]; then
        _cr_positional -o -O --output -H --header -u --user -A --user-agent -e --referer -b --cookie \
            -c --cookie-jar -w --write-out -x --proxy -K --config -d --data -F --form -T --upload-file -X --request \
            --url
        for a in ${_CR_P[@]+"${_CR_P[@]}"}; do
            case "$a" in
                POST|PUT|PATCH|DELETE|GET|HEAD|post|put|patch|delete|get|head) continue ;;
                *'$'*) continue ;;
            esac
            if [[ "$a" == *.* && "$a" != *=* ]]; then host=$(cr_url_host "$a"); break; fi
        done
    fi
    if [[ -n "$host" ]] && ! _cr_is_local_host "$host"; then
        _cr_s_exp=remote-command
        _cr_s_host="$host"
        if [[ -n "$method" ]]; then
            case "$(printf '%s' "$method" | tr '[:lower:]' '[:upper:]')" in
                GET|HEAD) ;;
                *) pub=1 ;;
            esac
        fi
        if (( pub )); then _cr_s_fam=external-publication; fi
    elif [[ -z "$host" ]] && (( urlopt || dyn )); then
        # The target is a variable or an unparsed --url: not provably local.
        _cr_s_expgap=unresolved-url
    fi
    return 0
}

_cr_kw_in_args() {
    local a
    for a in ${_CR_A[@]+"${_CR_A[@]}"}; do
        if [[ "$a" =~ $_CR_KW ]]; then return 0; fi
    done
    return 1
}

_cr_url_gap() {
    local a h
    for a in "$1" ${_CR_A[@]+"${_CR_A[@]}"}; do
        [[ "$a" == *://* ]] || continue
        h=$(cr_url_host "$a")
        if [[ -n "$h" ]] && ! _cr_is_local_host "$h"; then
            _cr_s_expgap=unclassified-url
            return 0
        fi
    done
    return 0
}

# _cr_segment WORD... — classify one simple command. Sets _cr_s_fam (approval
# family), _cr_s_exp/_cr_s_host (exposure), _cr_s_gap/_cr_s_expgap (gaps), and
# _cr_s_nested (a command string from `bash -c` / `eval` to classify next).
_cr_segment() {
    _cr_s_fam="" _cr_s_exp="" _cr_s_host="" _cr_s_gap="" _cr_s_expgap="" _cr_s_nested=""
    [[ $# -gt 0 ]] || return 0
    local -a w=("$@")
    local n=${#w[@]} i=0 guard=0 t b raw exe matched=1 wrapper=0 dest sh_host
    while (( i < n && guard < 64 )); do
        guard=$((guard + 1))
        t="${w[i]}"
        if [[ "$t" =~ $_CR_ASSIGN ]]; then i=$((i + 1)); continue; fi
        b="${t##*/}"
        case "$b" in
            env)
                i=$((i + 1))
                while (( i < n )); do
                    case "${w[i]}" in
                        -u|-C|--unset|--chdir) i=$((i + 2)) ;;
                        -*) i=$((i + 1)) ;;
                        *) if [[ "${w[i]}" =~ $_CR_ASSIGN ]]; then i=$((i + 1)); else break; fi ;;
                    esac
                done ;;
            sudo|doas)
                i=$((i + 1))
                while (( i < n )); do
                    case "${w[i]}" in
                        -u|-g|-C|-h|-p|-U|-r|-t) i=$((i + 2)) ;;
                        --) i=$((i + 1)); break ;;
                        -*) i=$((i + 1)) ;;
                        *) break ;;
                    esac
                done ;;
            command|builtin|exec|nohup|time|stdbuf|nice|ionice|then|do|else|if|while|until|'!'|'{')
                i=$((i + 1))
                while (( i < n )); do
                    case "${w[i]}" in
                        -n|-c|-p) i=$((i + 2)) ;;
                        -*) i=$((i + 1)) ;;
                        *) break ;;
                    esac
                done ;;
            timeout)
                i=$((i + 1))
                while (( i < n )); do
                    case "${w[i]}" in
                        -s|-k|--signal|--kill-after) i=$((i + 2)) ;;
                        -*) i=$((i + 1)) ;;
                        *) break ;;
                    esac
                done
                i=$((i + 1)) ;;
            bash|sh|zsh|dash)
                i=$((i + 1))
                while (( i < n )); do
                    case "${w[i]}" in
                        -o|+o|-O|+O) i=$((i + 2)) ;;
                        --*|+*) i=$((i + 1)) ;;
                        -*)
                            if [[ "${w[i]}" =~ ^-[a-zA-Z]*c[a-zA-Z]*$ ]]; then
                                _cr_s_nested="${w[i+1]:-}"
                                return 0
                            fi
                            i=$((i + 1)) ;;
                        *) break ;;
                    esac
                done ;;
            eval)
                if (( i + 1 < n )); then printf -v _cr_s_nested '%s ' "${w[@]:i+1}"; fi
                return 0 ;;
            npx|bunx) i=$((i + 1)) ;;
            *) break ;;
        esac
    done
    (( i < n )) || return 0
    raw="${w[i]}"
    exe="${raw##*/}"
    _CR_A=("${w[@]:i+1}")

    case "$exe" in
        git) _cr_git ;;
        gh) _cr_gh ;;
        ic)
            _cr_positional
            if [[ "${_CR_P[0]:-}" == publish ]]; then _cr_s_fam=release; fi ;;
        npm|pnpm|yarn|bun)
            _cr_positional
            case "${_CR_P[0]:-}" in
                run|exec|x|dlx|run-script) wrapper=1 ;;
                *) if _cr_any publish; then _cr_s_fam=release; fi ;;
            esac ;;
        cargo|uv|poetry|hatch|flit)
            _cr_positional
            if [[ "${_CR_P[0]:-}" == publish ]]; then _cr_s_fam=release; fi ;;
        twine)
            _cr_positional
            if [[ "${_CR_P[0]:-}" == upload ]]; then _cr_s_fam=release; fi ;;
        gem)
            _cr_positional
            if [[ "${_CR_P[0]:-}" == push ]]; then _cr_s_fam=release; fi ;;
        docker|podman)
            _cr_positional
            if [[ "${_CR_P[0]:-}" == push || ( "${_CR_P[0]:-}" == image && "${_CR_P[1]:-}" == push ) ]]; then
                _cr_s_fam=release
            fi ;;
        wrangler)
            _cr_positional
            case "${_CR_P[0]:-}" in deploy|publish) _cr_s_fam=release ;; esac ;;
        fly|flyctl|firebase|netlify)
            _cr_positional
            if [[ "${_CR_P[0]:-}" == deploy ]]; then _cr_s_fam=release; fi ;;
        vercel)
            _cr_positional
            if [[ "${_CR_P[0]:-}" == deploy ]] || _cr_any --prod; then _cr_s_fam=release; fi ;;
        terraform|tofu)
            _cr_positional
            case "${_CR_P[0]:-}" in apply|destroy) _cr_s_fam=release ;; esac ;;
        kubectl)
            _cr_positional -n --namespace --context --kubeconfig
            case "${_CR_P[0]:-}" in apply|delete) _cr_s_fam=release ;; esac ;;
        pulumi)
            _cr_positional
            case "${_CR_P[0]:-}" in up|destroy) _cr_s_fam=release ;; esac ;;
        helm)
            _cr_positional
            case "${_CR_P[0]:-}" in push|upgrade|install) _cr_s_fam=release ;; esac ;;
        bump-version.sh) _cr_s_fam=release ;;
        curl|wget|http|https|xh|aria2c|lynx|w3m|links) _cr_http "$exe" ;;
        dispatch.sh|gemini) _cr_s_exp=child-uncovered ;;
        codex)
            _cr_positional
            case "${_CR_P[0]:-}" in exec|e) _cr_s_exp=child-uncovered ;; esac ;;
        claude)
            if _cr_any -p --print; then _cr_s_exp=child-uncovered; fi ;;
        ssh)
            # Output of a remote command is untrusted content; the remote side's
            # actions are not observed, so keywords there are an approval gap.
            _cr_positional -p -i -l -o -F -J -L -R -D -b -c -e -m -O -Q -S -W -w -E -B -I
            dest="${_CR_P[0]:-}"
            sh_host=""
            if [[ "$dest" == *://* ]]; then
                sh_host=$(cr_url_host "$dest")
            elif [[ -n "$dest" ]]; then
                sh_host=$(cr_url_host "ssh://$dest")
            fi
            if [[ -z "$sh_host" ]]; then
                _cr_s_expgap=unclassified-remote
            elif ! _cr_is_local_host "$sh_host"; then
                _cr_s_exp=remote-command
                _cr_s_host="$sh_host"
            fi
            if _cr_kw_in_args; then _cr_s_gap=uncovered-wrapper; fi ;;
        xargs|make|just|parallel|watch|task|find|fd|entr|tmux|screen|nix|mise|direnv) wrapper=1 ;;
        *) matched=0 ;;
    esac

    if [[ -z "$_cr_s_fam" && -z "$_cr_s_exp" ]]; then
        if [[ "$raw" == \$* ]]; then
            if [[ "$raw" =~ $_CR_KW ]] || _cr_kw_in_args; then _cr_s_gap=unresolved-executable; fi
        elif (( wrapper )); then
            if _cr_kw_in_args; then _cr_s_gap=uncovered-wrapper; fi
        elif (( ! matched )) && [[ "$exe" =~ $_CR_KW ]] \
            && [[ "$raw" == */* || "$raw" == *.* || "$exe" == *-* || "$exe" == *_* ]]; then
            _cr_s_gap=unrecognized-command
        fi
        case "$exe" in
            git|echo|printf|bd|jq|grep|rg|sed|awk|cat|head|tail|sort|uniq|wc|tr|cut|ls|cd|cp|mv|rm|mkdir|touch|test|'['|true|false|export|local|read|tee) ;;
            *) _cr_url_gap "$raw" ;;
        esac
    fi
    return 0
}

# cr_classify_command COMMAND — classify a Bash command string (all segments,
# including `bash -c` / `eval` bodies).
cr_classify_command() {
    local cmd="${1:-}" truncated=0 nseg=0 nested=0 amb=0 out line
    local -a pending=() words=()
    [[ -n "$cmd" ]] || return 0
    if (( ${#cmd} > 65536 )); then cmd="${cmd:0:65536}"; truncated=1; fi
    pending=("$cmd")
    while (( ${#pending[@]} > 0 && nseg <= 2000 )); do
        cmd="${pending[0]}"
        pending=("${pending[@]:1}")
        out=$(_cr_tokenize "$cmd") || out=$'\036'
        if [[ "$out" == *$'\036' ]]; then
            amb=1
            out="${out%$'\036'}"
            out+=$'\n'"$(_cr_legacy_tokenize "$cmd")"
        fi
        while IFS= read -r line; do
            [[ -n "$line" ]] || continue
            nseg=$((nseg + 1))
            if (( nseg > 2000 )); then truncated=1; break; fi
            words=()
            IFS=$'\x1f' read -ra words <<<"$line" || true
            [[ ${#words[@]} -gt 0 ]] || continue
            _cr_segment "${words[@]}"
            if [[ -z "$CR_APPROVAL_FAMILY" && -n "$_cr_s_fam" ]]; then CR_APPROVAL_FAMILY="$_cr_s_fam"; fi
            if [[ "$_cr_s_exp" == remote-command && "$CR_EXPOSURE_CLASS" != remote-command ]]; then
                CR_EXPOSURE_CLASS=remote-command
                CR_EXPOSURE_HOST="$_cr_s_host"
            elif [[ "$_cr_s_exp" == child-uncovered && -z "$CR_EXPOSURE_CLASS" ]]; then
                CR_EXPOSURE_CLASS=child-uncovered
            fi
            if [[ -z "$CR_GAP_KIND" && -n "$_cr_s_gap" ]]; then CR_GAP_KIND="$_cr_s_gap"; fi
            if [[ -z "$CR_EXPOSURE_GAP" && -n "$_cr_s_expgap" ]]; then CR_EXPOSURE_GAP="$_cr_s_expgap"; fi
            if [[ -n "$_cr_s_nested" ]]; then
                nested=$((nested + 1))
                if (( nested > 16 )); then truncated=1; else pending+=("$_cr_s_nested"); fi
            fi
        done <<<"$out"
    done
    # Unbalanced quoting: a host read from it may be misparsed, so log none.
    if (( amb )) && [[ -n "$CR_EXPOSURE_HOST" ]]; then CR_EXPOSURE_HOST=ambiguous-host; fi
    if (( truncated )); then
        if [[ -z "$CR_APPROVAL_FAMILY" ]]; then CR_GAP_KIND=truncated-command; fi
        if [[ -z "$CR_EXPOSURE_CLASS" ]]; then CR_EXPOSURE_GAP=truncated-command; fi
    fi
    if [[ -n "$CR_APPROVAL_FAMILY" ]]; then CR_GAP_KIND=""; fi
    if [[ -n "$CR_EXPOSURE_CLASS" ]]; then CR_EXPOSURE_GAP=""; fi
    return 0
}

# ─── Tool classification ─────────────────────────────────────────────────

_cr_is_exempt_server() {
    local server="$1" raw item
    local -a items=()
    raw=$(cr_config_get exempt_mcp_servers "[]")
    raw="${raw#\[}"
    raw="${raw%\]}"
    IFS=',' read -ra items <<<"$raw" || true
    for item in ${items[@]+"${items[@]}"}; do
        item=$(printf '%s' "$item" | tr -d " \t\"'" | tr '[:upper:]' '[:lower:]')
        [[ -n "$item" ]] || continue
        if [[ "$server" == "$item" || "$server" == *"_$item" ]]; then return 0; fi
    done
    return 1
}

_cr_classify_mcp() {
    local rest="${CR_TOOL#mcp__}" server op fam=""
    server="${rest%%__*}"
    if [[ "$rest" == *__* ]]; then op="${rest#*__}"; else op=""; fi
    server=$(printf '%s' "$server" | tr '[:upper:]' '[:lower:]')
    op=$(printf '%s' "$op" | tr '[:upper:]' '[:lower:]')
    op="${op//-/_}"
    case "$op" in
        get_*|list_*|search_*|read_*|fetch_*|view_*|describe_*|query_*) ;;
        *)
            case "$op" in
                *pull_request*)
                    case "$op" in *create*|*merge*) fam=pr-publication ;; esac ;;
            esac
            if [[ -z "$fam" ]]; then
                case "$op" in
                    push_files|create_or_update_file|delete_file|create_branch|update_ref|create_ref) fam=remote-source-change ;;
                    *release*|*publish*|*deploy*) fam=release ;;
                    send_*|post_message|create_issue|update_issue|*_comment|add_comment*|create_comment*|reply*) fam=external-publication ;;
                esac
            fi
            if [[ -z "$fam" && "$op" =~ $_CR_KW ]]; then CR_GAP_KIND=unrecognized-mcp-operation; fi ;;
    esac
    CR_APPROVAL_FAMILY="$fam"
    if ! _cr_is_exempt_server "$server"; then
        case "$server" in
            *browser*|*playwright*|*puppeteer*|*chrome*|*chromium*) CR_EXPOSURE_CLASS=browser ;;
            *) CR_EXPOSURE_CLASS=mcp ;;
        esac
        CR_EXPOSURE_HOST="$CR_HOST"
    fi
    return 0
}

_cr_classify_skill() {
    local s
    s=$(printf '%s' "$CR_SKILL" | tr '[:upper:]' '[:lower:]')
    case "$s" in
        interpub:*release*|interpub:*publish*) CR_APPROVAL_FAMILY=release ;;
        *) if [[ "$s" =~ $_CR_KW ]]; then CR_GAP_KIND=unrecognized-skill; fi ;;
    esac
    return 0
}

# cr_classify — classify the parsed tool call into CR_APPROVAL_FAMILY,
# CR_EXPOSURE_CLASS/HOST, CR_GAP_KIND (approval surface), CR_EXPOSURE_GAP.
cr_classify() {
    CR_APPROVAL_FAMILY="" CR_EXPOSURE_CLASS="" CR_EXPOSURE_HOST="" CR_GAP_KIND="" CR_EXPOSURE_GAP=""
    case "$CR_TOOL" in
        Bash) cr_classify_command "$CR_CMD" ;;
        WebFetch|WebSearch|web.run|web__*) CR_EXPOSURE_CLASS=web; CR_EXPOSURE_HOST="$CR_HOST" ;;
        mcp__*) _cr_classify_mcp ;;
        Skill) _cr_classify_skill ;;
        # A child agent's result may carry content it read; which content is not
        # known without origin tagging (mk-42j9.42), so it counts as unknown.
        Task|Agent) CR_EXPOSURE_CLASS=subagent-result ;;
    esac
    return 0
}

# ─── State (plain JSON; not tamper-resistant; NOT a security boundary) ───

cr_state_load() {
    local f="$1" line
    CR_S_EPOCH=0 CR_S_EXPOSURE=unknown CR_S_REASON=no-session-start-record CR_S_FIRST=0
    CR_S_BATCH=0 CR_S_BATCH_START=0 CR_S_BATCH_READS=0 CR_S_READS=0 CR_S_SHADOW=unknown CR_S_EXISTS=0
    CR_S_EPOCH_READS=0
    [[ -r "$f" ]] || return 0
    line=$(jq -r '
        def n: if type == "number" and . >= 0 then floor else 0 end;
        def e: if . == "clean" or . == "exposed" or . == "unknown" then . else "unknown" end;
        [ (.epoch | n), (.exposure | e),
          ((.reason // "none") | tostring | gsub("[^A-Za-z0-9._-]"; "_") | if . == "" then "none" else . end),
          (.first_exposure_ts | n), (.batch | n), (.batch_start_ts | n), (.batch_reads | n),
          (.reads_since_exposure | n), (.shadow | e),
          (if .epoch_reads == null then (if (.batch | n) > 0 then 1 else 0 end) else (.epoch_reads | n) end) ]
        | map(tostring) | join(" ")' "$f" 2>/dev/null) || line=""
    if [[ -z "$line" ]]; then CR_S_REASON=state-unreadable; return 0; fi
    read -r CR_S_EPOCH CR_S_EXPOSURE CR_S_REASON CR_S_FIRST CR_S_BATCH CR_S_BATCH_START \
        CR_S_BATCH_READS CR_S_READS CR_S_SHADOW CR_S_EPOCH_READS <<<"$line"
    CR_S_EXISTS=1
    return 0
}

cr_state_save() {
    local f="$1" tmp now pv
    tmp="$f.tmp.$$"
    now=$(cr_now)
    pv=$(cr_config_int policy_version 1)
    { jq -nc --arg session "$CR_SID" --arg agent "${CR_AGENT:-}" --argjson epoch "$CR_S_EPOCH" \
        --arg exposure "$CR_S_EXPOSURE" \
        --arg reason "$CR_S_REASON" --argjson first "$CR_S_FIRST" --argjson batch "$CR_S_BATCH" \
        --argjson batch_start "$CR_S_BATCH_START" --argjson batch_reads "$CR_S_BATCH_READS" \
        --argjson epoch_reads "$CR_S_EPOCH_READS" \
        --argjson reads "$CR_S_READS" --arg shadow "$CR_S_SHADOW" --argjson now "$now" --argjson pv "$pv" \
        '{session: $session, agent: $agent, epoch: $epoch, exposure: $exposure, reason: $reason,
          first_exposure_ts: $first, batch: $batch, batch_start_ts: $batch_start,
          batch_reads: $batch_reads, epoch_reads: $epoch_reads, reads_since_exposure: $reads, shadow: $shadow,
          updated_ts: $now, policy_version: $pv,
          note: "observe-mode hygiene telemetry; NOT a security boundary; not tamper-resistant"}' \
        > "$tmp"; } 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 1; }
    mv -f "$tmp" "$f" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 1; }
    return 0
}

cr_lock() {
    local dir="$1"
    command -v flock >/dev/null 2>&1 || return 0
    [[ -d "$dir" ]] || return 0
    { exec 8>>"$dir/.lock"; } 2>/dev/null || return 0
    flock -w 2 8 2>/dev/null || true
    return 0
}

# State is keyed per (session, agent). A child agent's first call starts from
# the parent's exposure and shadow, with its own epoch counters, so the child
# and the parent never overwrite each other.
_cr_open_state() {
    local pfile
    _CR_DIR=$(cr_store_dir)
    mkdir -p "$_CR_DIR/state" 2>/dev/null || true
    cr_lock "$_CR_DIR"
    pfile="$_CR_DIR/state/$(cr_safe_id "$CR_SID").json"
    if [[ -z "${CR_AGENT:-}" ]]; then
        _CR_SFILE="$pfile"
        cr_state_load "$_CR_SFILE"
        return 0
    fi
    _CR_SFILE="$_CR_DIR/state/$(cr_safe_id "$CR_SID").agent.$(cr_safe_id "$CR_AGENT").json"
    if [[ -r "$_CR_SFILE" ]]; then
        cr_state_load "$_CR_SFILE"
        return 0
    fi
    cr_state_load "$pfile"
    if (( CR_S_EXISTS )); then CR_S_REASON=inherited-from-parent; fi
    CR_S_BATCH=0 CR_S_BATCH_START=0 CR_S_BATCH_READS=0 CR_S_EPOCH_READS=0
    return 0
}

_cr_close_state() {
    if ! cr_state_save "$_CR_SFILE"; then
        printf 'context-reset: session state NOT saved under %s (observe-mode telemetry only, not a security boundary; nothing was blocked)\n' "$_CR_DIR" >&2
    fi
    return 0
}

# ─── Rows ────────────────────────────────────────────────────────────────

_CR_EMIT_JQ='reduce $ARGS.positional[] as $kv
  ({event: $event, session: $session, epoch: $epoch, role: $role, thread: $thread,
    agent: $agent, mode: $mode, policy_version: $policy_version, ts: $ts,
    security_boundary: false};
   ($kv | index("=")) as $i
   | if $i == null or $i == 0 then .
     elif ($kv[:$i] | endswith(":")) then
       ($kv[$i + 1:]) as $v | .[$kv[:$i - 1]] = ($v | try fromjson catch $v)
     else .[$kv[:$i]] = $kv[$i + 1:]
     end)'

# cr_emit EVENT key=value key:=json ... — build one row and hand it to the
# always-allow recorder. A row that cannot be recorded is reported on stderr.
cr_emit() {
    local event="$1"
    shift
    local row epoch pv store verdict rc=0 why
    epoch="${CR_S_EPOCH:-0}"
    [[ "$epoch" =~ ^[0-9]+$ ]] || epoch=0
    pv=$(cr_config_int policy_version 1)
    row=$(jq -nc --arg event "$event" --arg session "${CR_SID:-}" --argjson epoch "$epoch" \
        --arg role "$(cr_role)" --arg thread "${BB_THREAD_ID:-}" --arg agent "${CR_AGENT:-}" \
        --arg mode "$(cr_mode)" --argjson policy_version "$pv" --argjson ts "$(cr_now)" \
        "$_CR_EMIT_JQ" --args "$@" 2>/dev/null) || row=""
    store=$(cr_store_dir)
    if [[ -z "$row" ]]; then
        printf 'context-reset: %s row NOT recorded (could not encode it; observe-mode telemetry only, not a security boundary; nothing was blocked)\n' "$event" >&2
        return 0
    fi
    verdict="$CR_ROOT/scripts/context-reset-verdict.sh"
    if command -v timeout >/dev/null 2>&1; then
        printf '%s\n' "$row" | timeout 3 bash "$verdict" --store "$store" >/dev/null || rc=$?
    else
        printf '%s\n' "$row" | bash "$verdict" --store "$store" >/dev/null || rc=$?
    fi
    if [[ $rc -ne 0 ]]; then
        why="recorder exit $rc"
        if [[ $rc -eq 124 ]]; then why="recorder timed out"; fi
        printf 'context-reset: %s row NOT recorded in %s (%s; observe-mode telemetry only, not a security boundary; nothing was blocked)\n' "$event" "$store" "$why" >&2
    fi
    return 0
}

# cr_context_tokens — H, the context size at the last assistant turn, or null.
cr_context_tokens() {
    local t="${CR_TRANSCRIPT:-}" v
    if [[ -z "$t" || ! -r "$t" ]]; then printf 'null'; return 0; fi
    v=$(tail -n 400 "$t" 2>/dev/null | jq -Rn '
        [inputs | (try fromjson catch null) | objects | .message? | objects | .usage? | objects]
        | last
        | if . == null then null
          else ((.input_tokens // 0) + (.cache_read_input_tokens // 0) + (.cache_creation_input_tokens // 0)) end' 2>/dev/null) || v=""
    [[ "$v" =~ ^[0-9]+$ ]] || v=null
    printf '%s' "$v"
}

# cr_record_approval FAMILY — log what a reset rule would do; the action proceeds.
cr_record_approval() {
    local fam="$1" now ev would secs=null sim=false shadow_before
    _cr_open_state
    now=$(cr_now)
    if [[ "$CR_S_EXPOSURE" == clean ]]; then
        ev=approval_clean
        would=false
    else
        ev=would_be_reset
        would=true
    fi
    if [[ "$CR_S_EXPOSURE" == exposed && "$CR_S_FIRST" -gt 0 ]]; then
        secs=$((now - CR_S_FIRST))
        if (( secs < 0 )); then secs=0; fi
    fi
    shadow_before="$CR_S_SHADOW"
    if [[ "$CR_S_SHADOW" != clean ]]; then
        sim=true
        CR_S_SHADOW=clean
    fi
    cr_emit "$ev" trigger=approval "family=$fam" "exposure=$CR_S_EXPOSURE" "exposure_reason=$CR_S_REASON" \
        "reads_since_exposure:=$CR_S_READS" "secs_since_exposure:=$secs" "context_tokens:=$(cr_context_tokens)" \
        "tool=$CR_TOOL" "ref=$CR_REF" "would_be_reset:=$would" "simulated_reset:=$sim" \
        "shadow_exposure=$shadow_before" "enforced:=false"
    _cr_close_state
    return 0
}

# cr_record_unknown REASON EVENT FIELDS... — clean becomes unknown (never a
# false clean). exposure_unknown rows are written only on the transition;
# coverage_gap rows are always written.
cr_record_unknown() {
    local reason="$1" ev="$2" was
    shift 2
    _cr_open_state
    was="$CR_S_EXPOSURE"
    if [[ "$CR_S_EXPOSURE" == clean ]]; then
        CR_S_EXPOSURE=unknown
        CR_S_REASON="$reason"
    fi
    if [[ "$CR_S_SHADOW" == clean ]]; then CR_S_SHADOW=unknown; fi
    if [[ "$ev" == coverage_gap || "$was" == clean ]]; then
        cr_emit "$ev" "prior_exposure=$was" "$@"
    fi
    _cr_close_state
    return 0
}

# cr_record_exposure CLASS HOST — one row per epoch's first read and per new
# accounting batch; later reads in a batch only update counters. An epoch that
# carried exposure over a compaction still gets its own first-read row.
cr_record_exposure() {
    local cls="$1" host="${2:-}" now prior prev max_reads max_secs carried
    if [[ "$cls" == child-uncovered || "$cls" == subagent-result ]]; then
        cr_record_unknown "$cls" exposure_unknown trigger=exposure "source_class=$cls" \
            "tool=$CR_TOOL" "ref=$CR_REF"
        return 0
    fi
    max_reads=$(cr_config_int batch_max_reads 20)
    max_secs=$(cr_config_int batch_max_seconds 600)
    _cr_open_state
    now=$(cr_now)
    CR_S_SHADOW=exposed
    if [[ "$CR_S_EXPOSURE" != exposed || "$CR_S_EPOCH_READS" -eq 0 ]]; then
        prior="$CR_S_EXPOSURE"
        if [[ "$CR_S_EXPOSURE" == exposed ]]; then
            carried=true
            CR_S_READS=$((CR_S_READS + 1))
        else
            carried=false
            CR_S_EXPOSURE=exposed
            CR_S_REASON="$cls"
            CR_S_FIRST=$now
            CR_S_READS=1
        fi
        CR_S_BATCH=1
        CR_S_BATCH_START=$now
        CR_S_BATCH_READS=1
        CR_S_EPOCH_READS=1
        cr_emit exposure trigger=exposure "first_in_epoch:=true" "batch:=1" "prior_exposure=$prior" \
            "carried:=$carried" "source_class=$cls" "host=$host" "tool=$CR_TOOL" "ref=$CR_REF" \
            "context_tokens:=$(cr_context_tokens)"
    else
        CR_S_READS=$((CR_S_READS + 1))
        CR_S_EPOCH_READS=$((CR_S_EPOCH_READS + 1))
        if (( CR_S_BATCH_READS >= max_reads || now - CR_S_BATCH_START >= max_secs )); then
            prev=$CR_S_BATCH_READS
            CR_S_BATCH=$((CR_S_BATCH + 1))
            CR_S_BATCH_START=$now
            CR_S_BATCH_READS=1
            cr_emit exposure trigger=exposure "first_in_epoch:=false" "batch:=$CR_S_BATCH" \
                "prev_batch_reads:=$prev" "source_class=$cls" "host=$host" "tool=$CR_TOOL" \
                "ref=$CR_REF" "context_tokens:=$(cr_context_tokens)"
        else
            CR_S_BATCH_READS=$((CR_S_BATCH_READS + 1))
        fi
    fi
    _cr_close_state
    return 0
}

# cr_session_start — startup/clear open a clean epoch; compact opens a new
# epoch that carries exposure (its batch counters restart); resume keeps state.
# No record means unknown.
cr_session_start() {
    local src="$CR_SOURCE" prior_epoch
    _cr_open_state
    prior_epoch=$CR_S_EPOCH
    case "$src" in
        startup|clear)
            CR_S_EPOCH=$((CR_S_EPOCH + 1))
            CR_S_EXPOSURE=clean CR_S_REASON="$src" CR_S_FIRST=0 CR_S_BATCH=0
            CR_S_BATCH_START=0 CR_S_BATCH_READS=0 CR_S_READS=0 CR_S_SHADOW=clean CR_S_EPOCH_READS=0 ;;
        compact)
            CR_S_EPOCH=$((CR_S_EPOCH + 1))
            CR_S_BATCH=0 CR_S_BATCH_START=0 CR_S_BATCH_READS=0 CR_S_EPOCH_READS=0
            if (( CR_S_EXISTS )); then
                CR_S_REASON=compact-carried
            else
                CR_S_EXPOSURE=unknown CR_S_REASON=compact-without-record CR_S_SHADOW=unknown
            fi ;;
        *)
            if (( ! CR_S_EXISTS )); then
                CR_S_EXPOSURE=unknown CR_S_REASON=resume-without-record CR_S_SHADOW=unknown
            fi ;;
    esac
    cr_emit session_start "source=$src" "exposure=$CR_S_EXPOSURE" "reason=$CR_S_REASON" \
        "prior_epoch:=$prior_epoch"
    _cr_close_state
    return 0
}

# ─── Hook entry points (called by the thin hook wrappers) ────────────────

cr_handle_post() {
    local payload="${1:-}"
    if ! cr_parse_payload "$payload"; then
        cr_emit hook_error hook=context-reset-post stage=parse
        return 0
    fi
    if [[ "$CR_EVENT" == SessionStart || ( -z "$CR_TOOL" && -n "$CR_SOURCE" ) ]]; then
        cr_session_start
        return 0
    fi
    cr_classify
    if [[ -n "$CR_EXPOSURE_CLASS" ]]; then
        cr_record_exposure "$CR_EXPOSURE_CLASS" "$CR_EXPOSURE_HOST"
    elif [[ -n "$CR_EXPOSURE_GAP" ]]; then
        cr_record_unknown coverage-gap coverage_gap surface=exposure "kind=$CR_EXPOSURE_GAP" \
            "tool=$CR_TOOL" "ref=$CR_REF" "count:=1"
    fi
    return 0
}

cr_handle_pre() {
    local payload="${1:-}"
    if ! cr_parse_payload "$payload"; then
        cr_emit hook_error hook=context-reset-pre stage=parse
        return 0
    fi
    cr_classify
    if [[ -n "$CR_APPROVAL_FAMILY" ]]; then
        cr_record_approval "$CR_APPROVAL_FAMILY"
    elif [[ -n "$CR_GAP_KIND" ]]; then
        _cr_open_state
        cr_emit coverage_gap surface=approval "kind=$CR_GAP_KIND" "tool=$CR_TOOL" "ref=$CR_REF" "count:=1"
    fi
    return 0
}