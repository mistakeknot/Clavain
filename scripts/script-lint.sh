#!/usr/bin/env bash
# Static preflight for scripts handed to mk. Never source or execute an input.
#
# HEURISTIC: this is a conservative source lint, not a proof of arbitrary shell
# behavior. A regex/lexer linter cannot be sound; a script can always defeat it
# (eval, indirect expansion, sourced files, aliases, computed command names).
# KNOWN LIMITS:
#   * No eval, sourced-file, alias, indirect-expansion or computed-command model.
#   * No complete control/data flow, runtime exit-status or shell-option model;
#     printf/echo/cat I/O failures and assignment substitutions are not proved.
#   * No invalidation of initial PATH checks by later PATH reassignment.
#   * git config --remove-section can leave stale trust in the textual model.
#   * success/failure text is not required to reach the message; status-to-text
#     data flow is not proved.
#   * No filesystem/symlink resolution, command execution or delivery proof.
#   * Download options: no config-file/.curlrc/.wgetrc or wget -e model,
#     curl --write-out %output{file}, --expand-* or --variable expansion model.
#     Implicit wget downloads/cache/log names and protocol side effects are
#     not modeled; explicit destinations and curl remote-name flags are checked.
#     Long read-option arguments can be mistaken for write flags. Ambiguous
#     prefixes, repeated options and curl --next are conservative unions, not
#     a per-transfer/last-option-wins model. Future options require table updates.
# Heuristic rules, in particular:
#   * exit-report reachability: a small structural walk of if/while/for/case/{ }
#     nesting and && || | & operators. It recognises the report only as an EXIT
#     trap that calls a function defined in the script, with the send either as
#     an `if [!] <send>; then/else` header or as `<send> || <paste>` / `|| { }`.
#   * command substitutions ($(...), backticks, <(...), unquoted heredocs) are
#     lexed and linted as root commands, but nested quoting is approximated.
#   * git safe.directory is matched textually per repository path (-C, --git-dir,
#     --work-tree, tracked `cd`), not by resolving symlinks or relative paths.
#     Only unconditional protected/global add/set operations establish trust.
#   * literal bash/sh -c lists use the same scans; command/builtin prefixes are
#     stripped. Reporter sends must occupy executable command positions. Later
#     trap changes and the last function definition determine reporting, and
#     paste output must expand the message without redirecting stdout.
#   * root-refusal evaluates simple zero comparisons and predicate polarity;
#     unknown predicates are conservative, and helper functions are not followed.
#   * the unset-variable check relies on shellcheck (SC2154); without it the
#     rule is skipped and the skip is disclosed in the output.
# Keep commands explicit: nounset and an exported literal absolute PATH in the
# first 20 code lines; a readable absolute cwd before payload work; an EXIT
# reporter with status, success/failure, bb tell (--mode auto), and a
# failed-send paste block.
set -u

usage() {
    printf 'Usage: script-lint.sh [--thread ID] [--handoff-message FILE] PATH...\n'
}
help_text() {
    usage
    cat <<'TEXT'

Static preflight for scripts handed to mk. Inputs are only read, never run.
Exit status: 0 clean, 1 findings, 2 usage error.

This is a HEURISTIC source lint, not a proof of shell behavior; it can be
defeated by eval, indirection, sourced files or computed command names.

KNOWN LIMITS:
  * eval, sourced files, aliases, indirect expansion and computed commands
  * complete control/data flow, runtime exit statuses and shell-option semantics
    (printf/echo/cat I/O failures and assignment substitutions are not proved)
  * later PATH reassignment does not invalidate the initial PATH checks
  * git config --remove-section can leave stale trust in the textual model
  * success/failure text is not required to reach the message; status-to-text
    data flow is not proved
  * filesystem/symlink resolution, execution and live report delivery
  * download config-file/.curlrc/.wgetrc and wget -e settings; curl --write-out
    %output{file}, --expand-* and --variable expansion are not modeled
  * implicit wget downloads/cache/log names and protocol side effects are not
    modeled; explicit destinations and curl remote-name flags are checked
  * long read-option arguments can be mistaken for write flags; ambiguous
    prefixes, repeated options and curl --next use conservative unions, not
    per-transfer/last-option-wins semantics; future options need table updates

Rules:
  readable-script, bash-shebang, executable, bash-syntax (bash -n)
  nounset, fixed-path         set -u and literal exported PATH, first 20 lines
  readable-cwd                cd to an absolute directory before payload work
  ownership-assumptions       no $USER/$HOME/$SUDO_USER
  mk-home-user                work under mk's home must go through runuser/sudo -u mk
  sticky-writes               no fixed-name writes under /tmp or /var/tmp
  git-safe-directory          safe.directory per repository path (heuristic);
                              unconditional protected/global add/set only
  exit-report                 top-level EXIT trap calling a function that sends
                              `bb thread tell <thread> --mode auto <message>`
                              (or --message-file) on success and failure
                              (structural reachability walk is heuristic;
                              later traps and last function definitions count)
  paste-fallback              failed send prints an expanded paste block with
                              unredirected stdout (heuristic)
  report-thread               reporter targets --thread ID when supplied
  root-refusal                exit/return on the root branch of a simple
                              EUID/UID/id -u zero comparison (heuristic)
  shellcheck                  unset-variable use (SC2154) when shellcheck is
                              installed; otherwise SKIP is printed, exit stays 0
  pinned-handoff              with --handoff-message, a line must start with the
                              absolute script path or `bash <absolute path>`;
                              command must also parse with bash -n
                              otherwise "SKIP handoff-message not provided"

Command substitutions $(...), `...`, <(...) and unquoted heredocs are linted
as root commands: their ownership, git and sticky-directory effects count.
Literal bash/sh -c command lists use the same checks with the selected user;
command/builtin prefixes do not bypass checks. Send paths in data do not count.
TEXT
}
thread='' handoff='' failed=0
# The handoff owner is mk; their home is /home/<owner>.
owner_user=mk
owner_home=/home/$owner_user
paths=()
while (($#)); do
    case "$1" in
        --thread|--handoff-message)
            if (($# < 2)) || [[ -z $2 || $2 == --* ]]; then
                usage >&2; exit 2
            fi
            if [[ $1 == --thread ]]; then thread=$2; else handoff=$2; fi
            shift 2 ;;
        --) shift; paths+=("$@"); break ;;
        --help|-h) help_text; exit 0 ;;
        -*) usage >&2; exit 2 ;;
        *) paths+=("$1"); shift ;;
    esac
done
if ((${#paths[@]} == 0)); then usage >&2; exit 2; fi

have_shellcheck=0
if command -v shellcheck >/dev/null 2>&1; then
    have_shellcheck=1
else
    printf 'SKIP shellcheck not installed\n'
fi
if [[ -z $handoff ]]; then printf 'SKIP handoff-message not provided\n'; fi

finding() { printf '%s: [%s] %s\n' "$1" "$2" "$3"; failed=1; }
for path in "${paths[@]}"; do
    if [[ ! -f $path || ! -r $path ]]; then
        finding "$path" readable-script 'Expected a readable regular script file.'
        continue
    fi
    IFS= read -r first < "$path" || first=''
    if [[ ! $first =~ ^\#![[:space:]]*(/bin/bash|/usr/bin/bash|/usr/bin/env[[:space:]]+bash)([[:space:]]|$) ]]; then
        finding "$path" bash-shebang 'Use #!/bin/bash or #!/usr/bin/env bash.'
    fi
    if [[ ! -x $path ]]; then finding "$path" executable 'Set the executable bit.'; fi

    # awk lexes source only. Quoted text and comments cannot create commands;
    # literal sh/bash -c payloads are separately inspected for filesystem use.
    if ! awk -v file="$path" -v expected_thread="$thread" -v owner_home="$owner_home" '
    BEGIN {
        # owner_home as a literal regex; "/" needs no escape in a dynamic regex.
        for(k=1;k<=length(owner_home);k++) {
            c=substr(owner_home,k,1)
            owner_re=owner_re (index("[]\\.*^$(){}+?|",c) ? "\\" : "") c
        }
    }
    function fail(rule, detail) {
        printf "%s: [%s] %s\n", file, rule, detail
        bad=1
    }
    function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
    # Retain only text that can expand: single quotes and escaped dollars are
    # literal data, even though words() removes their syntactic quoting.
    function expanding(s,    i,c,q,esc,out) {
        q=""; esc=0; out=""
        for(i=1;i<=length(s);i++) {
            c=substr(s,i,1)
            if(esc) {esc=0; continue}
            if(c=="\\" && q!="\047") {esc=1; continue}
            if(q=="\047") {if(c==q) q=""; continue}
            if(c=="\047" && q=="") {q=c; continue}
            if(c=="\042") {q=(q=="") ? c : ""; continue}
            out=out c
        }
        return out
    }
    function prefixes(s) {
        while(s ~ /^(command|builtin)[ \t]+/)
            sub(/^(command|builtin)[ \t]+(--[ \t]+)?/, "", s)
        return s
    }
    function stdout_redirect(s,    i,c,q,esc,prev) {
        q=""; esc=0
        for(i=1;i<=length(s);i++) {
            c=substr(s,i,1)
            if(esc) {esc=0; continue}
            if(c=="\\" && q!="\047") {esc=1; continue}
            if(q!="") {if(c==q) q=""; continue}
            if(c=="\047" || c=="\042") {q=c; continue}
            if(c==">") {
                prev=substr(s,i-1,1)
                if(prev !~ /[0-9]/ || prev=="1") return 1
                # Skip the second > of a non-stdout append redirect.
                if(substr(s,i+1,1)==">") i++
            }
        }
        return 0
    }
    function words(s, a,    i,c,q,esc,n,w,quoted_word) {
        split("", a); n=0; w=""; q=""; esc=0
        for(i=1;i<=length(s);i++) {
            c=substr(s,i,1)
            if(esc) { w=w c; esc=0; continue }
            if(c=="\\" && q!="\047") { esc=1; continue }
            if(q!="") { if(c==q) q=""; else w=w c; continue }
            if(c=="\047" || c=="\042") { q=c; quoted_word=1; continue }
            if(c==">") {
                if(w!="" && w !~ /^[0-9]*>+$/) {a[++n]=w; w=""}
                w=w c; continue
            }
            if(w ~ /^[0-9]*>+$/ && c!="&") {a[++n]=w; w=""}
            if(c ~ /[ \t\n]/) { if(w!="" || quoted_word) {a[++n]=w; w=""; quoted_word=0}; continue }
            w=w c
        }
        if(w!="" || quoted_word) a[++n]=w
        return n
    }
    function expand(s,    i,c,key,tail,size,out) {
        # Scan the original input once; never recursively expand replacement
        # text (self-referential shell assignments must not hang the linter).
        out=""
        for(i=1;i<=length(s);i++) {
            c=substr(s,i,1)
            if(c!="$") {out=out c; continue}
            tail=substr(s,i+1); size=0; key=""
            if(tail ~ /^\{[A-Za-z_][A-Za-z0-9_]*\}/) {
                match(tail,/^\{[A-Za-z_][A-Za-z0-9_]*\}/)
                size=RLENGTH; key=substr(tail,2,size-2)
            } else if(tail ~ /^[A-Za-z_][A-Za-z0-9_]*/) {
                match(tail,/^[A-Za-z_][A-Za-z0-9_]*/)
                size=RLENGTH; key=substr(tail,1,size)
            }
            if(size && key in literal) {out=out literal[key]; i+=size}
            else out=out c
        }
        return out
    }
    function mk(s,    a,n) {
        sub(/^(if[ \t]+)?![ \t]+/, "", s)
        s=prefixes(s)
        n=words(s,a)
        return (a[1]=="runuser" && a[2]=="-u" && a[3]=="mk" && a[4]=="--") ||
               (a[1]=="sudo" && a[2]=="-u" && a[3]=="mk") || (a[1] in wrappers)
    }
    function sticky(path) {
        return path ~ /^\/(var\/)?tmp\// ||
               (sticky_cwd && path !~ /^[/&$-]/ && path!="")
    }
    function download_kind(cmd,option,    table,items,count,k,name,kind,result) {
        # Literal write destinations from the installed help. Match ALL write
        # prefixes, including ambiguous ones; do not guess which wins at runtime.
        table=(cmd=="curl") ? "output:body dump-header:file stderr:file cookie-jar:file trace:file trace-ascii:file libcurl:file etag-save:file hsts:file alt-svc:file output-dir:dir remote-name:remote remote-header-name:remote remote-name-all:remote create-dirs:create" : "output-document:file output-file:file append-output:file save-cookies:file directory-prefix:prefix rejected-log:file warc-file:file hsts-file:file warc-tempdir:prefix"
        count=split(table,items," "); result=""
        for(k=1;k<=count;k++) {
            name=items[k]; sub(/:.*/,"",name)
            kind=items[k]; sub(/^[^:]*:/,"",kind)
            if(option!="" && index(name,option)==1) result=result " " kind
        }
        return result
    }
    function download_outputs(a,n,start,cmd,conservative,    i,j,k,option,target,kind,arg_options,noarg_options,output_options,unknown_start,dirs,bodies,nd,nb,remote) {
        # Complete single-letter tables from curl 8.5.0 --help all and
        # GNU wget 1.21.4 --help. wget -F/-H are flags, -R takes an argument;
        # curl -h takes a category. Keep unknown/version-specific shorts safe.
        arg_options=(cmd=="curl") ? "AbcCdDeEFhHKmoPQrtTuUwxXyYz" : "aABDeiIloOPQRtTUwX"
        noarg_options=(cmd=="curl") ? "aBfgGIikjlLMnNOpqJRsS012346vVZ:#" : "bcdEFhHkKLmNnpqrsSvVx46"
        output_options=(cmd=="curl") ? "ocD" : "OoaP"
        unknown_start=0; nd=0; nb=0; remote=0
        for(i=start;i<=n;i++) {
            target=""; kind=""
            if(a[i]=="--" && !conservative) break
            if(a[i] ~ /^--./) {
                option=substr(a[i],3); sub(/=.*/,"",option)
                kind=download_kind(cmd,option)
                if(kind ~ /remote/) remote=1
                if(kind ~ /(file|body|dir|prefix)/) {
                    if(index(a[i],"=")) {
                        target=a[i]; sub(/^[^=]*=/,"",target)
                    } else if(i<n) {
                        target=a[i+1]
                        if(!conservative) i++
                    }
                }
                # Trace accepts % for stderr, in addition to - for stdout.
                if(cmd=="curl" && target=="%" && option!="" &&
                   (index("trace",option)==1 || index("trace-ascii",option)==1)) target=""
            } else if(a[i] ~ /^-[^-]/) {
                # No-argument letters continue the cluster. Any other letter
                # ends it: the remainder (or next token) is its argument.
                for(j=2;j<=length(a[i]);j++) {
                    option=substr(a[i],j,1)
                    if(cmd=="curl" && option ~ /^[JO]$/) remote=1
                    if(index(noarg_options,option)) continue
                    if(!index(arg_options,option) && !unknown_start)
                        unknown_start=i+1
                    target=substr(a[i],j+1)
                    if(target=="" && i<n) {
                        target=a[i+1]
                        if(!conservative) i++
                    }
                    sub(/^=/,"",target)
                    if(index(output_options,option)) {
                        kind=(cmd=="curl" && option=="o") ? "body" : ((cmd=="wget" && option=="P") ? "prefix" : "file")
                    } else target=""
                    break
                }
            }
            if(kind ~ /dir/ && target!="") dirs[++nd]=target
            if(kind ~ /body/ && target!="" && target!="-") bodies[++nb]=target
            if(kind ~ /file/ && sticky(target)) sticky_bad=1
            if(kind ~ /body/ && target ~ /^\// && sticky(target)) sticky_bad=1
            if(kind ~ /prefix/ && (sticky(target) || target ~ /^\/(var\/)?tmp\/?$/)) sticky_bad=1
        }
        # Directory options affect relative body names regardless of order.
        # Keep every literal candidate conservatively rather than assuming a
        # complete per-transfer/last-option-wins model.
        if(remote && nd==0 && sticky_cwd) sticky_bad=1
        if(nd==0) for(k=1;k<=nb;k++) if(sticky(bodies[k])) sticky_bad=1
        for(j=1;j<=nd;j++) {
            target=dirs[j]
            if(remote && (sticky(target) || target ~ /^\/(var\/)?tmp\/?$/)) sticky_bad=1
            for(k=1;k<=nb;k++) if(bodies[k] !~ /^[/&$-]/ &&
                sticky(target "/" bodies[k])) sticky_bad=1
        }
        # An unknown short may consume a real output flag as its argument.
        # Rescan EVERY later token, including consumed arguments, for output
        # forms. Known argument text within a cluster still remains data.
        if(unknown_start && !conservative)
            download_outputs(a,n,unknown_start,cmd,1)
    }
    function filesystem(s, user,    a,n,i,target,cmd,e,payload,outer_data) {
        e=expand(s); n=words(e,a); cmd=a[1]
        payload=0; outer_data=""
        for(i=1;i+2<=n;i++) if(a[i] ~ /(^|\/)(bash|sh)$/ && cmd_position(a,i) && a[i+1]=="-c") {payload=i+2; break}
        for(i=1;i<=n;i++) if(i!=payload) outer_data=outer_data a[i] " "
        # printf/echo arguments are string data; only their redirects touch files.
        # Shell payload tokens are scanned separately with their own commands.
        if(outer_data ~ (owner_re "(/|[ \t]|$)") && !user && !mk(s) && cmd !~ /^(printf|echo)$/)
            home_bad=1
        for(i=1;i<=n;i++) {
            if(i==payload) continue
            target=a[i]; sub(/^[0-9]*>+[&]?/, "", target)
            # Only standalone redirection tokens are parent-shell redirects.
            # A quoted sh -c argument is handled recursively above.
            if(!user && i>1 && a[i-1] ~ /^[0-9]*>+$/ && target ~ ("^" owner_re "(/|$)")) home_bad=1
            if(sticky(target) && (a[i] ~ />/ ||
               (i>1 && a[i-1] ~ /^[0-9]*>+$/))) sticky_bad=1
        }
        # mkdir/mktemp create a new directory (or fail); they never open another
        # user'"'"'s regular file for writing, so they are not listed here.
        # Find the real executable through common user/environment wrappers.
        for(i=1;i<=n;i++) {
            cmd=a[i]; sub(/^.*\//,"",cmd)
            if(cmd ~ /^(runuser|sudo|env|command|builtin)$/ || a[i] ~ /^-/ ||
               a[i] ~ /^[A-Za-z_][A-Za-z0-9_]*=/ ||
               (i>1 && a[i-1] ~ /^(-u|-g|--user|--group)$/)) continue
            break
        }
        if(cmd ~ /^(touch|tee|truncate)$/) {
            for(i=i+1;i<=n;i++) if(sticky(a[i])) sticky_bad=1
        }
        if(cmd ~ /^(cp|mv|install|ln)$/ && sticky(a[n])) sticky_bad=1
        if(cmd ~ /^(curl|wget)$/) download_outputs(a,n,i+1,cmd,0)
        if(cmd ~ /^(dd|sed)$/) {
            for(i=2;i<=n;i++) if(a[i] ~ /^(of=)?\/(var\/)?tmp\// &&
                (cmd=="dd" || a[i-1] ~ /^(-o|-O|--output)$/ || s ~ /sed[ \t]+-i/)) sticky_bad=1
        }
    }

    # ---- command substitutions (run as root in the parent shell) ----
    # extract(s, subs, raw): fills subs[] with the bodies of $(...), `...` and
    # <(...)/>(...) found outside single quotes; ex_out is s with each replaced
    # by a placeholder word. raw=1 (heredoc text) ignores quote characters.
    function extract(s, subs, raw,    i,L,c,nx,q,esc,out,n,d,j,cc,qq,bs,stk,nst,body,isproc) {
        n=0; out=""; q=""; esc=0; L=length(s); i=1
        while(i<=L) {
            c=substr(s,i,1); nx=substr(s,i+1,1)
            if(esc) {out=out c; esc=0; i++; continue}
            if(c=="\\" && (raw || q!="\047")) {out=out c; esc=1; i++; continue}
            if(!raw) {
                if(q=="\047") {out=out c; if(c=="\047") q=""; i++; continue}
                if(c=="\047" && q=="") {q=c; out=out c; i++; continue}
                if(c=="\042") {q=(q=="") ? c : ""; out=out c; i++; continue}
            }
            isproc=(!raw && q=="" && (c=="<" || c==">") && nx=="(")
            if((c=="$" && nx=="(") || isproc) {
                d=1; j=i+2; qq=""; bs=0; split("", stk); split("", nst); nst[1]=0
                while(j<=L && d>0) {
                    cc=substr(s,j,1)
                    if(bs) bs=0
                    else if(cc=="\\" && qq!="\047") bs=1
                    else if(qq=="\047") { if(cc=="\047") qq="" }
                    else if(cc=="$" && substr(s,j+1,1)=="(") { stk[d]=qq; d++; nst[d]=0; qq=""; j++ }
                    else if(qq=="\042") { if(cc=="\042") qq="" }
                    else if(cc=="\047" || cc=="\042") qq=cc
                    else if(cc=="(") nst[d]++
                    else if(cc==")") {
                        if(nst[d]>0) nst[d]--
                        else { d--; if(d>0) qq=stk[d] }
                    }
                    j++
                }
                body=(d>0) ? substr(s,i+2) : substr(s,i+2,j-i-3)
                subs[++n]=body; out=out "$__SUBST__"; i=j; continue
            }
            if(c=="`") {
                j=i+1
                while(j<=L) { cc=substr(s,j,1); if(cc=="\\") {j+=2; continue}; if(cc=="`") break; j++ }
                subs[++n]=substr(s,i+1,j-i-1); out=out "$__SUBST__"; i=j+1; continue
            }
            out=out c; i++
        }
        ex_out=out
        return n
    }
    # split_list(body, parts): split a command list on ; & && || | and newlines
    # outside quotes, nested parentheses and backticks.
    function split_list(s, parts,    i,L,c,nx,pv,q,esc,d,bt,cur,n) {
        n=0; cur=""; q=""; esc=0; d=0; bt=0; L=length(s); split("", parts)
        for(i=1;i<=L;i++) {
            c=substr(s,i,1); nx=substr(s,i+1,1); pv=substr(s,i-1,1)
            if(esc) {cur=cur c; esc=0; continue}
            if(c=="\\" && q!="\047") {cur=cur c; esc=1; continue}
            if(q!="") {cur=cur c; if(c==q) q=""; continue}
            if(c=="\047" || c=="\042") {q=c; cur=cur c; continue}
            if(c=="`") {bt=!bt; cur=cur c; continue}
            if(c=="(") d++
            if(c==")" && d>0) d--
            if(!d && !bt && (c==";" || c=="|" || c=="&" || c=="\n")) {
                if(c=="&" && (pv==">" || nx==">")) {cur=cur c; continue}
                if(trim(cur)!="") parts[++n]=trim(cur)
                cur=""; continue
            }
            cur=cur c
        }
        if(trim(cur)!="") parts[++n]=trim(cur)
        return n
    }
    # ---- git safe.directory, matched per repository path ----
    function norm_dir(p) { if(p!="/") sub(/\/+$/, "", p); return p }
    function safe_match(repo, spec) {
        spec=norm_dir(spec); repo=norm_dir(repo)
        if(spec=="*") return 1
        if(spec ~ /\/\*$/) return index(repo, substr(spec,1,length(spec)-1))==1
        return spec==repo
    }
    function is_safe(repo, extra,    k) {
        if(repo=="") return 0
        for(k in safe_dir) if(safe_match(repo, k)) return 1
        for(k in extra) if(safe_match(repo, extra[k])) return 1
        return 0
    }
    function cmd_position(a, i,    k) {
        for(k=1;k<i;k++) {
            if(a[k] ~ /^(if|!|then|do|else|elif|while|until|time|command|builtin|exec|env|nohup|nice|timeout|stdbuf|ionice|sudo|doas|runuser)$/) continue
            if(a[k] ~ /^[A-Za-z_][A-Za-z0-9_]*=/) continue
            if(a[k] ~ /^-/ || a[k] ~ /^[0-9]+[smhd]?$/) continue
            if(k>1 && a[k-1] ~ /^-[ugCT]$/) continue
            return 0
        }
        return 1
    }
    function gitcheck(s, user,    e,n,a,i,gi,w,repo,extra,pc,sub_cmd,k,val,global_config,write_config,read_config) {
        e=expand(s); n=words(e,a); gi=0
        for(i=1;i<=n;i++) if(a[i] ~ /(^|\/)git$/ && cmd_position(a,i)) {gi=i; break}
        if(!gi || user || mk(s)) return
        repo=""; pc=0; split("", extra); i=gi+1
        while(i<=n) {
            w=a[i]
            if(w=="-C") { repo=a[i+1]; i+=2 }
            else if(w ~ /^-C./) { repo=substr(w,3); i++ }
            else if(w=="-c") { if(a[i+1] ~ /^safe\.directory=/) extra[++pc]=substr(a[i+1],16); i+=2 }
            else if(w=="--git-dir" || w=="--work-tree") { repo=a[i+1]; i+=2 }
            else if(w ~ /^--(git-dir|work-tree)=/) { repo=w; sub(/^[^=]*=/,"",repo); i++ }
            else if(w ~ /^-/) i++
            else break
        }
        sub_cmd=a[i]
        if(sub_cmd=="config") {
            global_config=0; write_config=0; read_config=0
            for(k=i+1;k<=n;k++) {
                if(a[k] ~ /^--(global|system)$/) global_config=1
                if(a[k] ~ /^--(local|worktree|file)$/ || a[k] ~ /^--file=/) read_config=1
                if(a[k] ~ /^--(add|set|replace-all)$/ || a[k]=="set") write_config=1
                if(a[k] ~ /^--(get|list|remove|show)/ || a[k] ~ /^(get|list)$/) read_config=1
            }
            for(k=i+1;k<=n;k++) if(a[k]=="safe.directory" && global_config && !read_config && scan_uncond) {
                val=a[k+1]
                # Reads have already returned; positional writes are valid too.
                # Conservatively revoke trust on unset (value patterns can be regex).
                if(e ~ /--unset(-all)?([ \t]|$)/) { split("",safe_dir); continue }
                if(k==n) continue
                if(val=="" || e ~ /--(replace-all|set)([ \t]|$)/ || !write_config)
                    split("",safe_dir)
                if(val!="" && val !~ /^-/) safe_dir[val]=1
            }
            return
        }
        if(repo=="") repo=cwd_path
        if(!is_safe(repo, extra)) git_bad=1
    }
    # scan(s, level): lint one statement. Substitutions run first, as root,
    # regardless of any runuser/sudo wrapper on the enclosing command.
    function scan(s, level, user,    outer, n, subs, i, np, parts, k,a,na,inner,saved_uncond,saved_cwd) {
        n=extract(s, subs, 0); outer=ex_out
        if(level<8) for(i=1;i<=n;i++) {
            np=split_list(subs[i], parts)
            for(k=1;k<=np;k++) scan(parts[k], level+1, user)
        }
        outer=trim(outer)
        while(outer ~ /^(if|then|else|elif|do|while|until|!|\{)[ \t]+/)
            sub(/^(if|then|else|elif|do|while|until|!|\{)[ \t]+/, "", outer)
        while(outer ~ /^(export|local|readonly|declare|typeset)[ \t]+/) {
            sub(/^(export|local|readonly|declare|typeset)[ \t]+/, "", outer)
            while(outer ~ /^-[A-Za-z]+[ \t]+/) sub(/^-[A-Za-z]+[ \t]+/, "", outer)
            if(outer !~ /^[A-Za-z_][A-Za-z0-9_]*(\+)?=/) { outer=""; break }
        }
        while(match(outer, /^[A-Za-z_][A-Za-z0-9_]*\+?=("[^"]*"|\047[^\047]*\047|[^ \t]*)([ \t]+|$)/))
            outer=substr(outer, RLENGTH+1)
        if(outer=="") return
        outer=prefixes(outer)
        filesystem(outer,user); gitcheck(outer,user)
        # A literal shell payload is a command list, not a single filesystem
        # command. Apply the same scans with the shell selected by the wrapper.
        na=words(outer,a)
        if(level<8) for(i=1;i<na;i++) if(a[i] ~ /(^|\/)(bash|sh)$/ && cmd_position(a,i) && a[i+1]=="-c") {
            inner=a[i+2]; np=split_list(inner,parts)
            saved_uncond=scan_uncond; saved_cwd=cwd_path
            if(inner ~ /(^|[;\n])[ \t]*(if|while|for|case) / || inner ~ /&&|\|\|/) scan_uncond=0
            for(k=1;k<=np;k++) scan(parts[k],level+1,user || mk(outer))
            scan_uncond=saved_uncond; cwd_path=saved_cwd
        }
    }
    function scan_doc(text,    n, subs, i, np, parts, k) {
        n=extract(text, subs, 1)
        for(i=1;i<=n;i++) {
            np=split_list(subs[i], parts)
            for(k=1;k<=np;k++) scan(parts[k], 1)
        }
    }

    # ---- statement collection ----
    function emit(    s) {
        s=trim(buffer); buffer=""
        if(s=="") return 0
        statements[++count]=s; scope[count]=current; line[count]=start_line
        before[count]=pending; pending=""
        return 1
    }
    function pseudo(tok) { start_line=NR; buffer=tok; emit() }

    # ---- structural walk: nesting context of every statement in a scope ----
    function kw_split(s) {
        if(match(s, /^[ \t\n]*[^ \t\n]+/)) {
            kw_w=substr(s,RSTART,RLENGTH); sub(/^[ \t\n]+/, "", kw_w)
            kw_rest=substr(s,RLENGTH+1); sub(/^[ \t\n]+/, "", kw_rest)
        } else { kw_w=""; kw_rest="" }
    }
    function entry(kind, branch, hdr, neg, bop, prev) {
        return kind ":" branch ":#" hdr ":" neg ":" bop ":" prev
    }
    function joinp(p, e) { return (p=="") ? e : p "/" e }
    function refresh(t) {
        cur_path=joinp(fpath[t], entry(fk[t], fb[t], fh[t], fn[t], fo[t], fv[t]))
    }
    function dead_path(p,    n,parts,i,f,h,t) {
        n=split(p,parts,"/")
        for(i=1;i<=n;i++) {
            split(parts[i],f,":"); h=f[3]; sub(/^#/,"",h); t=trim(Rtext[h])
            if(t=="false" || t=="true" || t==":") {
                truth=(t!="false"); if(f[4]) truth=!truth
                if((f[1]=="if" && ((f[2]=="then" && !truth) || (f[2]=="else" && truth))) ||
                   (f[1]=="loop" && !truth)) return 1
            }
        }
        return 0
    }
    function dead_record(r,    t,v) {
        if(dead_path(Rpath[r])) return 1
        if(r>1 && Rpath[r]==Rpath[r-1] && Rbop[r] ~ /^(&&|\|\|)$/) {
            t=trim(Rtext[r-1])
            if(t=="false" || t=="true" || t==":") {
                v=(t!="false"); if(Rneg[r-1]) v=!v
                return (Rbop[r]=="&&" && !v) || (Rbop[r]=="||" && v)
            }
        }
        return 0
    }
    function push(t, kind, branch, hdr, neg, bop, prev) {
        fk[t]=kind; fb[t]=branch; fh[t]=hdr; fn[t]=neg; fo[t]=bop; fv[t]=prev
        fpath[t]=cur_path; refresh(t)
    }
    function walk(sc, base, level,    j, rest, bop, aop, lv, top, push_if, neg, w, hdr_rec, name, ce, saved) {
        saved=cur_path; cur_path=base; lv=level*1000; top=lv
        for(j=1;j<=count;j++) {
            if(scope[j]!=sc || (sc!="" && j<last_def[sc])) continue
            rest=statements[j]; bop=before[j]; aop=after[j]; push_if=0; neg=0
            while(1) {
                kw_split(rest); w=kw_w
                if(w=="if") { push_if=1; rest=kw_rest; continue }
                if(w=="!") { neg=!neg; rest=kw_rest; continue }
                if(w=="then" || w=="else" || w=="elif") {
                    if(top>lv && fk[top]=="if") {
                        fb[top]=(w=="then") ? "then" : ((w=="else") ? "else" : "elif")
                        # an elif/else chain is not a plain send/failure branch
                        if(w=="elif") fh[top]=""
                        refresh(top)
                    }
                    rest=kw_rest; continue
                }
                if(w=="fi" || w=="done" || w=="esac" || w=="}") {
                    if(top>lv) { cur_path=fpath[top]; top-- }
                    rest=kw_rest; continue
                }
                if(w ~ /^(while|until|for|select|case)$/) {
                    top++; push(top, "loop", "", rn+1, w=="until", bop, rn); bop=""
                    rest=kw_rest; continue
                }
                if(w=="do") { rest=kw_rest; continue }
                if(w=="{") {
                    top++; push(top, "group", "", "", "", bop, rn); bop=""
                    rest=kw_rest; continue
                }
                break
            }
            hdr_rec=0
            rest=prefixes(rest)
            if(rest!="") {
                rn++; hdr_rec=rn
                Rtext[rn]=rest; Rpath[rn]=cur_path; Rbop[rn]=bop; Raop[rn]=aop; Rstmt[rn]=j
                Rneg[rn]=neg
                Rredirect[rn]=call_redirect[level]
                if(push_if) { Rifhdr[rn]=1; Rifneg[rn]=neg }
                kw_split(rest); name=kw_w
                if(level<4 && (name in bodies) && !(name in active)) {
                    ce=cur_path
                    if(bop!="" || aop ~ /^(&|\|)$/) ce=joinp(cur_path, entry("call", "", "", "", bop, aop))
                    call_redirect[level+1]=(call_redirect[level] || stdout_redirect(rest))
                    active[name]=1; walk(name, ce, level+1); delete active[name]
                }
            }
            if(push_if) { top++; push(top, "if", "cond", hdr_rec, neg+0, "", "") }
        }
        cur_path=saved
    }
    function early_exit_word(t) { kw_split(t); return kw_w ~ /^(return|exit|exec)$/ }
    function root_truth(t,    v) {
        # Unknown predicates retain conservative behavior. For recognised zero
        # comparisons return their truth value when UID is zero.
        v=-1
        if(t ~ /(-eq|==|=)[ \t\042\047]*0([^0-9]|$)/) v=1
        if(t ~ /(-ne|!=)[ \t\042\047]*0([^0-9]|$)/) v=0
        return v
    }
    function why_add(s) { why=why (why=="" ? "" : "; ") s }

    {
        if(heredoc!="") {
            terminator=$0; sub(/\r$/, "", terminator)
            if(heredoc_tabs) sub(/^\t+/, "", terminator)
            if(terminator==heredoc) {
                heredoc=""
                if(heredoc_expand && hd_text!="") docs[++ndocs]=hd_text
                hd_text=""
            } else if(heredoc_expand) hd_text=hd_text $0 "\n"
            next
        }
        # Small shell lexer: remove comments outside quotes, separate command
        # lists outside quotes, and record function scopes. No eval is used.
        for(pos=1;pos<=length($0);pos++) {
            c=substr($0,pos,1); nx=substr($0,pos+1,1)
            if(escape) { buffer=buffer c; escape=0; continue }
            if(c=="\\" && quote!="\047") { buffer=buffer c; escape=1; continue }
            if(quote=="\047") { buffer=buffer c; if(c==quote) quote=""; continue }
            # Substitutions are opaque to the statement splitter.
            if((c=="$" && nx=="(") || (quote=="" && (c=="<" || c==">") && nx=="(")) {
                cs_depth++; cs_quote[cs_depth]=quote; cs_nest[cs_depth]=0; quote=""
                buffer=buffer c "("; pos++; continue
            }
            if(cs_depth>0 && quote=="") {
                if(c=="(") cs_nest[cs_depth]++
                else if(c==")") {
                    if(cs_nest[cs_depth]>0) cs_nest[cs_depth]--
                    else { quote=cs_quote[cs_depth]; cs_depth--; buffer=buffer c; continue }
                }
            }
            if(c=="`") { bt=!bt; buffer=buffer c; continue }
            if(quote!="") { buffer=buffer c; if(c==quote) quote=""; continue }
            if(c=="\047" || c=="\042") { quote=c; buffer=buffer c; continue }
            if(cs_depth>0 || bt) { buffer=buffer c; continue }
            if(c=="#" && (pos==1 || substr($0,pos-1,1) ~ /[ \t;]/)) break
            if(c=="<" && nx=="<" && substr($0,pos+2,1)!="<" &&
               (pos==1 || substr($0,pos-1,1)!="<")) {
                tail=substr($0,pos+2); heredoc_tabs=(tail ~ /^-/); sub(/^-/, "", tail)
                pending_expand=(tail !~ /^[ \t]*[\\\042\047]/)
                words(tail,hd); pending_heredoc=hd[1]
            }
            # Braces in parameter expansions are not function boundaries.
            if(c=="{" && buffer ~ /\$$/) { parameter++; buffer=buffer c; continue }
            if(c=="}" && parameter) {parameter--; buffer=buffer c; continue}
            if(c=="{" && trim(buffer) ~ /^(function[ \t]+)?[A-Za-z_][A-Za-z0-9_]*[ \t]*(\([ \t]*\))?$/) {
                name=trim(buffer); sub(/^function[ \t]+/, "", name); sub(/[ \t]*\(.*/, "", name)
                current=name; last_def[name]=count+1; bodies[name]=""; block_depth=1; buffer=""; continue
            }
            if(c=="{" && current!="") {emit(); block_depth++; pseudo("{"); continue}
            if(c=="}" && current!="") {
                emit(); if(block_depth>1) pseudo("}")
                block_depth--; if(!block_depth) current=""; continue
            }
            if(c==";" || c=="|" || c=="&") {
                if(c=="&" && buffer ~ />$/) {buffer=buffer c; continue}
                op=c
                if((c=="|" || c=="&") && nx==c) { op=c c; pos++ }
                else if(c=="|" && nx=="&") pos++
                else if(c==";" && nx==";") pos++
                if(emit()) after[count]=op
                pending=(op=="&&" || op=="||" || op=="|") ? op : ""
                continue
            }
            if(buffer=="") start_line=NR
            buffer=buffer c
        }
        if(quote!="" || cs_depth>0 || bt) buffer=buffer "\n"
        else if(escape) {sub(/\\$/, "", buffer); escape=0}
        else emit()
        if(pending_heredoc!="") {
            heredoc=pending_heredoc; heredoc_expand=pending_expand; pending_heredoc=""
        }
    }
    END {
        emit()
        # First collect explicit user-switch wrappers and function bodies.
        for(j=1;j<=count;j++) if(scope[j]!="" && j>=last_def[scope[j]]) {
            bodies[scope[j]]=bodies[scope[j]] statements[j] "\n"
            if(statements[j] ~ /^runuser[ \t]+-u[ \t]+mk[ \t]+--[ \t]+[\042\047]*\$[@]/ ||
               statements[j] ~ /^sudo[ \t]+-u[ \t]+mk[ \t]+(--[ \t]+)?[\042\047]*\$[@]/) wrappers[scope[j]]=1
        }
        # Structural walks: top level, then every function (for root-refusal).
        walk("", "", 0)
        for(r=1;r<=rn;r++) {
            kw_split(Rtext[r])
            stmt_dead[Rstmt[r]]=dead_record(r)
            stmt_uncond[Rstmt[r]]=(Rpath[r]=="" && !Rifhdr[r] && Rbop[r] !~ /^(&&|\|\||\|)$/ && Raop[r] !~ /^(&|\|)$/)
            if(kw_w=="trap") {
                trap_text[Rstmt[r]]=Rtext[r]
                trap_uncond[Rstmt[r]]=(scope[Rstmt[r]]=="" && Rpath[r]=="" && Rbop[r] !~ /^(&&|\|\||\|)$/ && Raop[r] !~ /^(&|\|)$/)
            }
        }
        for(k in bodies) walk(k, "", 0)
        for(r=1;r<=rn;r++) {
            t=Rtext[r]
            if(t ~ /(^|[^A-Za-z0-9_])(EUID|UID)([^A-Za-z0-9_]|$)/ || t ~ /(^|[^A-Za-z0-9_])id[ \t]+-[A-Za-z]*u/) {
                truth=root_truth(t)
                if(Rneg[r] && truth>=0) truth=!truth
                root_setup[Rstmt[r]]=1
                if(Rifhdr[r]) {
                    for(q=r+1;q<=rn;q++) if(early_exit_word(Rtext[q]) && kw_w != "exec" &&
                        (truth<0 && index(Rpath[q], ":#" r ":") ||
                         truth==1 && index(Rpath[q], "if:then:#" r ":") ||
                         truth==0 && index(Rpath[q], "if:else:#" r ":"))) root_bad=1
                } else if(Raop[r] ~ /^(&&|\|\|)$/ && r<rn && scope[Rstmt[r+1]]==scope[Rstmt[r]]) {
                    if((truth==0 && Raop[r]=="&&") || (truth==1 && Raop[r]=="||")) root_setup[Rstmt[r+1]]=1
                    if((truth<0 || (truth==1 && Raop[r]=="&&") || (truth==0 && Raop[r]=="||")) &&
                        early_exit_word(Rtext[r+1]) && kw_w != "exec") root_bad=1
                }
            }
        }
        for(d=1;d<=ndocs;d++) scan_doc(docs[d])
        for(j=1;j<=count;j++) {
            if(scope[j]!="" && j<last_def[scope[j]]) continue
            s=statements[j]; n=words(s,a); cmd=a[1]
            scan_uncond=stmt_uncond[j]
            if(line[j]!=previous_line) code_lines++
            previous_line=line[j]
            if(code_lines<=20 && s ~ /^set[ \t]+/ &&
               (s ~ /^set[ \t]+-[a-zA-Z]*u/ || s ~ /^set[ \t]+-o[ \t]+nounset/)) nounset=1
            if(s ~ /^(export[ \t]+)?PATH=/) {
                value=s; sub(/^(export[ \t]+)?PATH=/,"",value)
                words(value,v); value=v[1]; parts=split(value,p,":"); fixed=parts>0
                for(i=1;i<=parts;i++) if(p[i] !~ /^\// || p[i] ~ /[$`]/) fixed=0
                if(code_lines<=20 && fixed) path_fixed=1
                if(s ~ /^export[ \t]+PATH=/) path_exported=1
            }
            if(code_lines<=20 && s ~ /^export[ \t]+PATH([ \t]|$)/) path_exported=1
            if(s ~ /\$(\{)?(USER|HOME|SUDO_USER)([^A-Za-z0-9_]|$)/) ownership_bad=1
            assignment=s; sub(/^(export|local|readonly)[ \t]+/,"",assignment)
            if(assignment ~ /^[A-Za-z_][A-Za-z0-9_]*=/ && !stmt_dead[j]) {
                key=assignment; sub(/=.*/,"",key)
                value=substr(assignment,length(key)+2); words(value,v)
                dynamic[key]=expanding(value)
                if(value !~ /\$\(|`/) {
                    expanded_value=expand(v[1])
                    literal[key]=(expanded_value ~ /^\//) ? expanded_value : v[1]
                }
                scan(s, 0)
                continue
            }
            if(j in trap_text) {
                n=words(trap_text[j],a)
            }
            if(j in trap_text && !stmt_dead[j]) {
                action=(a[2]=="--") ? 3 : 2
                for(i=action+1;i<=n;i++) if(a[i]=="EXIT" || a[i]=="0") {
                    trap_body=a[action]; trap_ok=trap_uncond[j]
                    if(a[action]=="-" || a[action]=="") trap_body=""
                }
            }
            if(scope[j]=="" && !trap_body && cmd !~ /^(set|export|readonly|trap|function|if|then|fi)$/)
                pretrap_payload=1
            if(scope[j]=="" && !cwd && !root_setup[j] && cmd !~ /^(set|export|readonly|trap|function|if|then|fi|exec)$/) {
                if(cmd=="cd" && stmt_uncond[j] && a[2] ~ /^\// &&
                   a[2] !~ /[$`]/) cwd=1
                else cwd_bad=1
            }
            if(scope[j]=="" && cmd=="cd" && stmt_uncond[j]) {
                sticky_cwd=(a[2] ~ /^\/(var\/)?tmp(\/|$)/)
                cwd_path=expand(a[2]); if(cwd_path ~ /[$`]/) cwd_path=""
            }
            scan(s, 0)
        }

        # ---- EXIT reporter: installation, reachability, content ----
        why=""; T=0; r0=0; r1=-1; report=trap_body "\n"
        words(trap_body,call); fname=call[1]
        if(!trap_body) why_add("no EXIT trap")
        else if(!trap_ok) why_add("EXIT trap is not installed unconditionally at top level")
        else if(!(fname in bodies)) why_add("EXIT trap must call a reporter function defined in the script")
        if(pretrap_payload) why_add("payload runs before the EXIT trap")
        if(trap_body && trap_ok && (fname in bodies)) {
            call_redirect[0]=stdout_redirect(trap_body)
            r0=rn+1; active[fname]=1; walk(fname, "", 0); delete active[fname]; r1=rn
            for(r=r0;r<=r1;r++) report=report Rtext[r] "\n"
        }
        bb=owner_re "/\\.local/bin/bb[ \t]+thread[ \t]+tell[ \t]+"
        capture_first=(r1>=r0 && Rtext[r0] ~ /^(local[ \t]+)?[A-Za-z_][A-Za-z0-9_]*=\$(\?|1)([ \t\n;]|$)/)
        captured=""
        if(capture_first && match(Rtext[r0], /[A-Za-z_][A-Za-z0-9_]*=\$(\?|1)/)) {
            captured=substr(Rtext[r0],RSTART,RLENGTH); sub(/=.*/,"",captured)
            if(Rtext[r0] ~ /=\$1([ \t\n;]|$)/ && trap_body !~ /\$\?/) { capture_first=0; captured="" }
        }
        if(!capture_first) why_add("first reporter statement must capture $? (or $1 with trap passing \"$?\")")
        has_status=(report ~ /\$\?/ && report ~ /(success|SUCCESS)/ && report ~ /(fail|FAIL)/)
        if(!has_status) why_add("report does not distinguish success and failure from $?")
        for(r=r0;r<=r1;r++) {
            n=words(Rtext[r],a)
            for(i=1;i+2<=n;i++) if(a[i]==owner_home "/.local/bin/bb" && a[i+1]=="thread" && a[i+2]=="tell" && cmd_position(a,i)) {T=r; break}
            if(T) break
        }
        if(!T) why_add("no " owner_home "/.local/bin/bb thread tell in the reporter")
        dynamic_message=0; message_var=""; report_target=""; fallback=0
        if(T) {
            # Rebuild message state in reporter execution order. Dead branches
            # and assignments after the send cannot supply message content.
            split("",dynamic)
            for(r=r0;r<T;r++) if(!dead_record(r)) {
                assignment=Rtext[r]; sub(/^(local|export|readonly)[ \t]+/,"",assignment)
                if(assignment ~ /^[A-Za-z_][A-Za-z0-9_]*=/) {
                    key=assignment; sub(/=.*/,"",key)
                    dynamic[key]=expanding(substr(assignment,length(key)+2))
                    if(r>r0 && key==captured) why_add("captured status is reassigned before the send")
                }
            }
            if(!(Rpath[T]=="" && Rbop[T] !~ /^(&&|\|\||\|)$/ && Raop[T] !~ /^(&|\|)$/))
                why_add("bb send is conditional or not reached on every exit")
            n=words(Rtext[T],a); ti=0
            for(i=3;i<=n;i++) if(a[i]=="tell" && a[i-1]=="thread" && a[i-2] ~ /(^|\/)bb$/) {ti=i; break}
            np=0; mode=""; msgfile=""; unsupported=""; split("", targs)
            for(i=ti+1;i<=n;i++) {
                tk=a[i]
                if(tk=="--") { for(i=i+1;i<=n;i++) targs[++np]=a[i]; break }
                else if(tk=="--mode") { mode=a[i+1]; i++ }
                else if(tk ~ /^--mode=/) { mode=tk; sub(/^[^=]*=/,"",mode) }
                else if(tk=="--message-file") { msgfile=a[i+1]; i++ }
                else if(tk ~ /^--message-file=/) { msgfile=tk; sub(/^[^=]*=/,"",msgfile) }
                else if(tk ~ /^--(model|service-tier|reasoning-level|permission-mode|send-at|file|image)$/) i++
                else if(tk ~ /^--(model|service-tier|reasoning-level|permission-mode|send-at|file|image)=/ || tk ~ /^--(json|plan)$/) { }
                else if(tk ~ /^-/) unsupported=tk
                else targs[++np]=tk
            }
            if(mode!="auto") why_add("bb thread tell must pass --mode auto")
            if(unsupported!="") why_add("unsupported bb thread tell option " unsupported " (use --message-file or a positional message)")
            if(np<1 || (msgfile=="" && np<2)) why_add("bb thread tell needs <thread> and a message")
            report_target=expand(targs[1])
            mtoken=(msgfile!="") ? msgfile : targs[2]
            if(msgfile!="") message_file=1
            if(mtoken ~ /^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?$/) { message_var=mtoken; gsub(/[${}]/,"",message_var); message_text=dynamic[message_var] }
            else message_text=expanding(Rtext[T])
            if(message_var!="" && expanding(Rtext[T]) !~ ("\\$(\\{)?" message_var "([^A-Za-z0-9_]|$)")) message_text=""
            if(captured!="" && message_text ~ ("\\$(\\{)?" captured "([^A-Za-z0-9_]|$)")) dynamic_message=1
            if(message_file && captured!="" && message_var!="") {
                for(r=r0;r<T;r++) if(!dead_record(r) && Rtext[r] ~ ("\\$(\\{)?" captured "([^A-Za-z0-9_]|$)") &&
                    Rtext[r] ~ (">[ \t]*[\042\047]*\\$(\\{)?" message_var "([^A-Za-z0-9_]|$)")) dynamic_message=1
            }
            if(!dynamic_message) why_add("message does not carry the captured status")

            # The failure branch of the send: where the paste block must live.
            rp=""; direct=0
            if(Rifhdr[T] && Raop[T] !~ /^(&&|\|\||\||&)$/)
                rp=joinp(Rpath[T], entry("if", Rifneg[T] ? "then" : "else", T, Rifneg[T], "", ""))
            else if(Raop[T]=="||") {
                rp=joinp(Rpath[T], entry("group", "", "", "", "||", T))
                direct=(T+1<=r1 && Rbop[T+1]=="||" && Rpath[T+1]==Rpath[T])
            }
            paste_contents=0; paste_word=0; lastsig=T
            for(r=T+1;r<=r1;r++) if((rp!="" && Rpath[r]==rp) || (direct && r==T+1)) {
                lastsig=r
                kw_split(Rtext[r])
                if(kw_w ~ /^(printf|echo|cat)$/ && message_var!="" &&
                   expanding(Rtext[r]) ~ ("\\$(\\{)?" message_var "([^A-Za-z0-9_]|$)") &&
                   !stdout_redirect(Rtext[r]) && !Rredirect[r]) paste_contents=1
                if(Rtext[r] ~ /[Pp][Aa][Ss][Tt][Ee]/) paste_word=1
            }
            fallback=(paste_contents && paste_word)
            # An early return/exit before the send or its failure branch skips it.
            for(r=r0;r<lastsig;r++) if(early_exit_word(Rtext[r])) {
                why_add("return/exit/exec before the send or its failure branch"); break
            }
            # A bare command may fail under inherited errexit. Accept explicit
            # disabling or shell guards; do not assume arbitrary commands succeed.
            for(r=r0;r<lastsig;r++) if(!dead_record(r)) {
                t=Rtext[r]
                errexit=1
                for(q=r0;q<=r;q++) if(!dead_record(q)) {
                    # A conditional set +e only protects its own branch.
                    if(Rpath[q]=="" || Rpath[q]==Rpath[r] || index(Rpath[r],Rpath[q] "/")==1) {
                        if(Rtext[q] ~ /^set[ \t]+\+([A-Za-z]*e|o[ \t]+errexit)([ \t]|$)/) errexit=0
                        if(Rtext[q] ~ /^set[ \t]+-([A-Za-z]*e|o[ \t]+errexit)([ \t]|$)/) errexit=1
                    }
                }
                kw_split(t)
                if(errexit && !Rifhdr[r] && Raop[r] !~ /^(&&|\|\|)$/ &&
                   t !~ /^(local|export|readonly|set|true|:|printf|echo|cat)([ \t]|$)/ &&
                   t !~ /^[A-Za-z_][A-Za-z0-9_]*=/ &&
                   !(kw_w in bodies)) {
                    why_add("bare command under errexit can prevent reporting; use set +e or a guard")
                    break
                }
            }
        }
        if(!trap_body || !trap_ok || (trap_body && !(fname in bodies)) || !T || why!="" || pretrap_payload)
            fail("exit-report", "Install an unconditional top-level EXIT trap whose reporter captures $? and sends via " owner_home "/.local/bin/bb thread tell <thread> --mode auto <message> on success and failure (" why ").")
        if(!fallback) fail("paste-fallback", "On a failed bb send, print a paste block containing the report (in the failure branch of the send).")
        if(expected_thread!="") {
            if(report_target!=expected_thread)
                fail("report-thread", "EXIT reporter must target the supplied --thread ID.")
        }
        if(!nounset) fail("nounset", "Enable set -u within the first 20 code lines.")
        if(!path_fixed || !path_exported) fail("fixed-path", "Set and export a literal PATH of absolute directories within the first 20 code lines.")
        if(ownership_bad) fail("ownership-assumptions", "Use explicit mk identity; do not rely on $USER, $HOME or $SUDO_USER.")
        if(home_bad) fail("mk-home-user", "Operations under " owner_home " require runuser -u mk -- or sudo -u mk; parent-shell redirects and command substitutions are still root operations.")
        if(git_bad) fail("git-safe-directory", "Configure git safe.directory for each repository path before root git commands, or run git as mk.")
        if(sticky_bad) fail("sticky-writes", "Avoid fixed writes under /tmp or /var/tmp; use mktemp or a mk-owned non-sticky directory.")
        if(root_bad) fail("root-refusal", "Do not exit/return on the root branch of EUID/UID/id -u tests; handoff scripts run as root.")
        if(!cwd || cwd_bad) fail("readable-cwd", "First payload step (including after re-exec) must cd to a readable absolute directory such as / or /tmp.")
        exit bad ? 1 : 0
    }' < "$path"; then failed=1; fi

    # Syntax-only parsing with no inherited startup hooks or shell options.
    # bash -n reads the input but does not run substitutions, traps, or commands.
    if ! output=$(env -i PATH=/usr/bin:/bin bash --noprofile --norc -n -- "$path" 2>&1); then
        finding "$path" bash-syntax "$output"
    fi

    # Unset-variable use under set -u (SC2154). Reads the file; never runs it.
    if ((have_shellcheck)); then
        if ! output=$(shellcheck --shell=bash --include=SC2154 -- "$path" 2>&1); then
            finding "$path" shellcheck "$output"
        fi
    fi

    if [[ -n $handoff ]]; then
        absolute=$(realpath -- "$path")
        pinned=0
        if [[ -f $handoff && -r $handoff ]]; then
            while IFS= read -r line || [[ -n $line ]]; do
                line=${line#"${line%%[![:space:]]*}"}
                line=${line#'$ '}
                for q in '' "'" '"'; do
                    quoted="$q$absolute$q"
                    for cand in "$quoted" "bash $quoted" "/bin/bash $quoted" "/usr/bin/bash $quoted"; do
                        if [[ $line == "$cand" || $line == "$cand "* || $line == "$cand"$'\t'* ]]; then
                            # Parse the candidate command without executing it;
                            # prefix matching alone accepts broken quoting and
                            # dangling command-list operators.
                            if output=$(printf '%s\n' "$line" | env -i PATH=/usr/bin:/bin bash --noprofile --norc -n 2>&1) && [[ -z $output ]]; then
                                pinned=1
                            fi
                        fi
                    done
                done
            done < "$handoff"
        fi
        if ((!pinned)); then
            finding "$path" pinned-handoff "Hand-off message needs a runnable line starting with $absolute or bash $absolute"
        fi
    fi
done
exit "$failed"
