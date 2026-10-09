"""Static handoff preflight: real CLI, fixture scripts are never executed."""
import os
import hashlib
import subprocess

import pytest


# Fixture scripts spell the owner's home as @OWNER_HOME@; it is expanded when a
# fixture is written, to the owner's home (/home/<owner>).
OWNER = "mk"
OWNER_HOME = f"/home/{OWNER}"


GOOD = '''#!/usr/bin/env bash
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
THREAD=thr_example
report() {
    local rc=$?
    local result
    if (( rc == 0 )); then
        result=success
    else
        result=failure
    fi
    local message="handoff $result exit=$rc"
    runuser -u mk -- tee "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" <<< "$message" >/dev/null || true
    if ! runuser -u mk -- @OWNER_HOME@/.local/bin/bb thread tell "$THREAD" --mode auto "$message"; then
        printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' "$message"
    fi
}
trap report EXIT
cd / || exit 1
if [[ ${1:-} == --check ]]; then exit 0; fi
runuser -u mk -- touch @OWNER_HOME@/example
'''


@pytest.fixture
def lint(project_root, tmp_path):
    script = project_root / "scripts/script-lint.sh"
    def run(*args, env=None, auto_handoff=True):
        if auto_handoff and args and not str(args[-1]).startswith('-') and '--handoff-message' not in args:
            path = args[-1]
            if hasattr(path, 'read_bytes') and path.exists():
                message = tmp_path / 'auto-message.md'
                message.write_text(f'bash {path.resolve()}\n{hashlib.sha256(path.read_bytes()).hexdigest()}\n')
                args = ('--handoff-message', message, *args)
        return subprocess.run(
            ["bash", str(script), *map(str, args)], text=True,
            capture_output=True, timeout=10, env=env,
        )
    return run


@pytest.fixture
def fixture_script(tmp_path):
    def write(body=GOOD, name="handoff.sh", mode=0o755):
        path = tmp_path / name
        path.write_text(body.replace("@OWNER_HOME@", OWNER_HOME))
        path.chmod(mode)
        return path
    return write


def test_clean_script(lint, fixture_script):
    result = lint(fixture_script())
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("old,new,rule", [
    ("local message=\"handoff $result exit=$rc\"", 'local message="handoff"', "exit-report"),
    ("trap report EXIT", "trap report EXIT\ntrap - EXIT", "exit-report"),
    ("trap report EXIT", "trap report EXIT\nexit 0", "readable-cwd"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "if true; then touch @OWNER_HOME@/example; fi", "mk-home-user"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "TMP=/tmp/fixed\necho x > \"${TMP}\"", "sticky-writes"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "echo x >/tmp/fixed", "sticky-writes"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "cp /etc/hosts /tmp/fixed; chown mk /tmp/fixed", "sticky-writes"),
    ("THREAD=thr_example", "THREAD=thr_wrong\nOTHER=thr_example", "report-thread"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "echo \"unterminated", "bash-syntax"),
])
def test_static_regressions(lint, fixture_script, old, new, rule):
    args = ["--thread", "thr_example"] if rule == "report-thread" else []
    result = lint(*args, fixture_script(GOOD.replace(old, new)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[{rule}]" in result.stdout, result.stdout


@pytest.mark.parametrize("old,new,rule", [
    ("export PATH", "", "fixed-path"),
    ('"$message"\n    fi', "'no report contents'\n    fi", "paste-fallback"),
    ('    if ! runuser', '    if (( rc == 0 )); then\n    if ! runuser', "exit-report"),
    ("    fi\n}\ntrap", "    fi\n    fi\n}\ntrap", "bash-syntax"),
    ("trap report EXIT\ncd /", "cd /", "exit-report"),
])
def test_reporting_and_environment_regressions(lint, fixture_script, old, new, rule):
    body = GOOD.replace(old, new)
    if new.startswith('    if (( rc == 0 ))'):
        body = body.replace("    fi\n}\ntrap", "    fi\n    fi\n}\ntrap")
    result = lint(fixture_script(body))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[{rule}]" in result.stdout, result.stdout


def test_report_with_or_fallback(lint, fixture_script):
    body = GOOD.replace('    if ! runuser', '    runuser').replace(
        '; then\n        printf', ' || {\n        printf'
    ).replace('    fi\n}\ntrap', '    }\n}\ntrap')
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout + result.stderr


def test_handoff_literals_cannot_be_spoofed_by_heredoc(lint, fixture_script):
    body = GOOD.replace("set -euo pipefail", "cat <<TEXT\nset -u\nTEXT")
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert "[nounset]" in result.stdout


def test_safe_reexec(lint, fixture_script):
    body = GOOD.replace("cd / || exit 1", 'if [[ $(id -u) != 0 ]]; then\n    exec sudo -- "$0" "$@"\nfi\ncd / || exit 1')
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("directory", ["/tmp", "/var/tmp", "/usr"])
def test_readable_cwd_can_be_sticky(lint, fixture_script, directory):
    result = lint(fixture_script(GOOD.replace("cd / ||", f"cd {directory} ||")))
    assert result.returncode == 0, result.stdout + result.stderr


def test_relative_write_in_sticky_cwd(lint, fixture_script):
    body = GOOD.replace("cd / ||", "cd /tmp ||") + "touch fixed-name\n"
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert "[sticky-writes]" in result.stdout


def test_message_file_report(lint, fixture_script):
    body = GOOD.replace('    local message="handoff $result exit=$rc"',
                        '    local message=$(mktemp)\n    printf "handoff %s exit=%s\\n" "$result" "$rc" > "$message"\n    chmod 644 "$message" || true')
    body = body.replace('tee "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" <<< "$message"',
                        'cp "$message" "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt"')
    body = body.replace('--mode auto "$message"', '--mode auto --message-file "$message"')
    body = body.replace("printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"",
                        "printf 'BEGIN PASTE BLOCK\\n'\n        cat \"$message\"\n        printf 'END PASTE BLOCK\\n'")
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout + result.stderr


def test_trap_passes_exit_status(lint, fixture_script):
    body = GOOD.replace('local rc=$?', 'local rc=$1').replace('trap report EXIT', 'trap \'report "$?"\' EXIT')
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("old,new,rule", [
    ("trap report EXIT\ncd / || exit 1", "cd / || exit 1\ntrap report EXIT", "exit-report"),
    ("local rc=$?\n    local result", "local result\n    local rc=$?", "exit-report"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "cat <<< harmless\ntouch @OWNER_HOME@/example", "mk-home-user"),
])
def test_final_static_regressions(lint, fixture_script, old, new, rule):
    result = lint(fixture_script(GOOD.replace(old, new)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[{rule}]" in result.stdout


def test_self_referential_variable_cannot_hang(lint, fixture_script):
    result = lint(fixture_script(GOOD + 'VALUE=$VALUE\nprintf "%s\\n" "$VALUE"\n'))
    assert result.returncode in (0, 1), result.stderr


@pytest.mark.parametrize("old,new,rule", [
    ("#!/usr/bin/env bash", "#!/bin/sh", "bash-shebang"),
    ("set -euo pipefail", "set -eo pipefail", "nounset"),
    ("set -euo pipefail", "# set -u", "nounset"),
    ("PATH=/usr/sbin:/usr/bin:/sbin:/bin", "PATH=$PATH:/bin", "fixed-path"),
    ("PATH=/usr/sbin:/usr/bin:/sbin:/bin", "# PATH=/usr/bin:/bin", "fixed-path"),
    ("PATH=/usr/sbin:/usr/bin:/sbin:/bin", "PATH=.:/bin", "fixed-path"),
    ("touch @OWNER_HOME@/example", 'chown "$USER" @OWNER_HOME@/example', "ownership-assumptions"),
    ("touch @OWNER_HOME@/example", 'chown "${SUDO_USER:-mk}" @OWNER_HOME@/example', "ownership-assumptions"),
    ("touch @OWNER_HOME@/example", 'cp "$HOME/file" @OWNER_HOME@/example', "ownership-assumptions"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "touch @OWNER_HOME@/example", "mk-home-user"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "runuser -u mk -- true; touch @OWNER_HOME@/example", "mk-home-user"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "runuser -u mk -- echo x > @OWNER_HOME@/example", "mk-home-user"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "DEST=@OWNER_HOME@/example\ntouch \"$DEST\"", "mk-home-user"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "git status", "git-safe-directory"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "git status\ngit config --global --add safe.directory /srv/repo", "git-safe-directory"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "echo x > /tmp/fixed", "sticky-writes"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "echo x >> /var/tmp/fixed", "sticky-writes"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "touch /tmp/fixed", "sticky-writes"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "cp /etc/hosts /tmp/fixed", "sticky-writes"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "printf x | tee /var/tmp/fixed", "sticky-writes"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "TMP=/tmp/fixed\nprintf x > \"$TMP\"", "sticky-writes"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "scratch=$(mktemp)\necho x > /tmp/fixed", "sticky-writes"),
    ("runuser -u mk -- touch @OWNER_HOME@/example", "runuser -u mk -- sh -c 'echo x > /tmp/fixed'", "sticky-writes"),
    ("trap report EXIT", "# trap report EXIT", "exit-report"),
    ("trap report EXIT", "trap report ERR", "exit-report"),
    ("local rc=$?", "local rc=0", "exit-report"),
    ("result=failure", "result=success", "exit-report"),
    ("@OWNER_HOME@/.local/bin/bb thread tell", "bb thread tell", "exit-report"),
    ('--mode auto "$message"', "--mode auto 'success'", "exit-report"),
    ("printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"", "true", "paste-fallback"),
    ("if ! runuser", "if runuser", "paste-fallback"),
    ("cd / || exit 1", "cd relative-dir || exit 1", "readable-cwd"),
    ("cd / || exit 1", "cd \"$HOME\" || exit 1", "readable-cwd"),
    ("cd / || exit 1", "", "readable-cwd"),
    ("cd / || exit 1", "touch relative-file\ncd / || exit 1", "readable-cwd"),
])
def test_failed_rule(lint, fixture_script, old, new, rule):
    result = lint(fixture_script(GOOD.replace(old, new)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[{rule}]" in result.stdout, result.stdout


def test_executable_bit(lint, fixture_script):
    result = lint(fixture_script(mode=0o644))
    assert result.returncode == 1
    assert "[executable]" in result.stdout


@pytest.mark.parametrize("operation", [
    "as_mk() { runuser -u mk -- \"$@\"; }\nas_mk touch @OWNER_HOME@/example",
    "runuser -u mk -- git -C @OWNER_HOME@/repo status",
    "git config --global --add safe.directory /srv/repo\ngit -C /srv/repo status",
    "git -c safe.directory=/srv/repo -C /srv/repo status",
    "scratch=$(mktemp)\nprintf x > \"$scratch\"",
    "scratch=$(mktemp -d /tmp/task.XXXXXX)\nprintf x > \"$scratch/output\"",
    "cat /tmp/input",
    "cp /tmp/input /srv/output",
    "runuser -u mk -- sh -c 'printf x > @OWNER_HOME@/output'",
])
def test_safe_operations(lint, fixture_script, operation):
    result = lint(fixture_script(GOOD.replace("runuser -u mk -- touch @OWNER_HOME@/example", operation)))
    assert result.returncode == 0, result.stdout + result.stderr


def test_top_means_first_twenty_code_lines(lint, fixture_script):
    body = GOOD.replace("set -euo pipefail\n", "").replace("export PATH\n", "export PATH\n" + "X=1\n" * 21 + "set -u\n")
    result = lint(fixture_script(body))
    assert "[nounset]" in result.stdout


def test_comments_do_not_count_as_code_lines(lint, fixture_script):
    result = lint(fixture_script(GOOD.replace("set -euo", "# comment\n" * 25 + "set -euo")))
    assert result.returncode == 0, result.stdout + result.stderr


def test_reports_all_rules(lint, fixture_script):
    bad = fixture_script("#!/bin/sh\necho bad\n", "bad.sh", 0o644)
    result = lint(bad)
    assert result.returncode == 1
    for rule in ("bash-shebang", "executable", "nounset", "fixed-path", "exit-report", "paste-fallback", "readable-cwd"):
        assert f"[{rule}]" in result.stdout
    assert str(bad) in result.stdout


def test_thread_is_checked(lint, fixture_script):
    path = fixture_script()
    assert lint("--thread", "thr_example", path).returncode == 0
    result = lint("--thread", "thr_wrong", path)
    assert result.returncode == 1
    assert "[report-thread]" in result.stdout


def test_handoff_requires_absolute_command(lint, fixture_script, tmp_path):
    path = fixture_script()
    message = tmp_path / "message.md"
    message.write_text(f"Run:\n```bash\nbash {path} --check\n```\n{hashlib.sha256(path.read_bytes()).hexdigest()}\n")
    assert lint("--handoff-message", message, path).returncode == 0
    message.write_text("Run: handoff.sh --check\n")
    result = lint("--handoff-message", message, path)
    assert result.returncode == 1
    assert "[pinned-handoff]" in result.stdout


def test_never_executes_or_sources_input(lint, fixture_script, tmp_path):
    marker = tmp_path / "executed"
    path = fixture_script(GOOD + f"touch {marker}\nexit 42\n")
    before = path.read_bytes(), path.stat().st_mode
    result = lint(path, env={"PATH": "/usr/bin:/bin"})
    # It fails the sticky-write rule, without running even the unsafe payload.
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[sticky-writes]" in result.stdout
    assert not marker.exists()
    assert (path.read_bytes(), path.stat().st_mode) == before


@pytest.mark.parametrize("args", [[], ["--thread"], ["--handoff-message"], ["--unknown"]])
def test_usage_errors(lint, args):
    assert lint(*args).returncode == 2


def test_missing_inputs(lint, tmp_path, fixture_script):
    result = lint('--handoff-message', tmp_path / 'message.md', tmp_path / "missing.sh")
    assert result.returncode == 1
    assert "[readable-script]" in result.stdout
    result = lint("--handoff-message", tmp_path / "missing.md", fixture_script())
    assert result.returncode == 1
    assert "[pinned-handoff]" in result.stdout


def test_v4_single_script_cli(lint, fixture_script):
    assert lint(fixture_script(name='one.sh'), fixture_script(name='two.sh')).returncode == 2


def test_empty_environment(lint, fixture_script):
    result = lint(fixture_script(), env={})
    assert result.returncode == 0, result.stdout + result.stderr


def test_shellcheck_if_present(lint, fixture_script, tmp_path):
    # The optional checker receives a filename, never an executable command.
    checker = tmp_path / "shellcheck"
    checker.write_text("#!/bin/bash\nprintf 'SC9999 fixture finding\\n'\nexit 1\n")
    checker.chmod(0o755)
    result = lint(fixture_script(), env={**os.environ, "PATH": f"{tmp_path}:/usr/bin:/bin"})
    assert result.returncode == 1
    assert "[shellcheck]" in result.stdout
    assert "SC9999" in result.stdout


# --- Fix round 1 (review ks34-review-1) -------------------------------------

SEND = (
    '    if ! runuser -u mk -- @OWNER_HOME@/.local/bin/bb thread tell "$THREAD" --mode auto "$message"; then\n'
    "        printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"\n"
    "    fi\n"
)
TELL = 'runuser -u mk -- @OWNER_HOME@/.local/bin/bb thread tell "$THREAD" --mode auto "$message"'
PASTE = "printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\""
PAYLOAD = "runuser -u mk -- touch @OWNER_HOME@/example"


def with_payload(operation):
    return GOOD.replace(PAYLOAD, operation)


@pytest.mark.parametrize("new", [
    '"$message"',
    "--mode steer \"$message\"",
    "--mode queue \"$message\"",
    "--message \"$message\"",
    "--mode auto --message \"$message\"",
    "--mode auto",
])
def test_reporter_requires_supported_cli_form(lint, fixture_script, new):
    result = lint(fixture_script(GOOD.replace('--mode auto "$message"', new)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[exit-report]" in result.stdout, result.stdout


@pytest.mark.parametrize("new", [
    '--mode=auto "$message"',
    '"$message" --mode auto',
    '--mode auto -- "$message"',
])
def test_reporter_accepts_equivalent_cli_forms(lint, fixture_script, new):
    result = lint(fixture_script(GOOD.replace('--mode auto "$message"', new)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("operation,rule", [
    ('runuser -u mk -- printf "%s\\n" "$(touch @OWNER_HOME@/root-write)"', "mk-home-user"),
    ('runuser -u mk -- printf "%s\\n" "`touch @OWNER_HOME@/root-write`"', "mk-home-user"),
    ('runuser -u mk -- echo "$(true; touch @OWNER_HOME@/x)"', "mk-home-user"),
    ('runuser -u mk -- echo "$(echo a | tee @OWNER_HOME@/x)"', "mk-home-user"),
    ('runuser -u mk -- echo "$(echo "$(touch @OWNER_HOME@/x)")"', "mk-home-user"),
    ('x=$(touch @OWNER_HOME@/x)', "mk-home-user"),
    ('printf "%s\\n" "$(git status)"', "git-safe-directory"),
    ('x=$(git status)', "git-safe-directory"),
    ('x=`git status`', "git-safe-directory"),
    ('runuser -u mk -- echo "$(git status)"', "git-safe-directory"),
    ('echo "$(touch /tmp/fixed)"', "sticky-writes"),
    ('echo "$(echo x > /tmp/fixed)"', "sticky-writes"),
    ('x=$(cat /etc/hosts | tee /tmp/fixed)', "sticky-writes"),
    ('runuser -u mk -- echo "<(touch /tmp/fixed)"; cat <(touch /tmp/fixed)', "sticky-writes"),
])
def test_command_substitutions_run_as_root(lint, fixture_script, operation, rule):
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[{rule}]" in result.stdout, result.stdout


@pytest.mark.parametrize("operation", [
    'x=$(runuser -u mk -- cat @OWNER_HOME@/file)',
    'printf "%s\\n" "$(runuser -u mk -- cat @OWNER_HOME@/file)"',
    "printf '%s\\n' '$(touch @OWNER_HOME@/x)'",
    'x=$(printf a; printf b)',
    'x=$(printf a | tr a b)',
    'x=`printf a`',
    'x=$(( 1 + 2 ))',
    'x=$(runuser -u mk -- git -C @OWNER_HOME@/repo status)',
])
def test_safe_command_substitutions(lint, fixture_script, operation):
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("operation", [
    "printf '%s\\n' '@OWNER_HOME@/example'",
    'echo @OWNER_HOME@/example',
    'printf "%s\\n" "@OWNER_HOME@/example"',
    "mkdir -p /tmp/newdir",
    "mkdir /tmp/newdir",
    'work=$(mktemp -d /tmp/job.XXXXXX)\nmkdir -p "$work/sub"',
    'work=$(mktemp -d)\nprintf x > "$work/out"',
    "mktemp /tmp/job.XXXXXX",
    "mktemp -d -p /tmp job.XXXXXX",
])
def test_false_positives_removed(lint, fixture_script, operation):
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("operation,rule", [
    ("echo x > @OWNER_HOME@/example", "mk-home-user"),
    ("printf '%s\\n' x > @OWNER_HOME@/example", "mk-home-user"),
    ("exec 3>/tmp/fixed", "sticky-writes"),
    ("mkdir -p /tmp/newdir\ntouch /tmp/newdir/file", "sticky-writes"),
    ("mkdir -p /tmp/newdir\nprintf x > /tmp/newdir/file", "sticky-writes"),
    (": > /tmp/fixed", "sticky-writes"),
])
def test_real_writes_still_flagged(lint, fixture_script, operation, rule):
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[{rule}]" in result.stdout, result.stdout


@pytest.mark.parametrize("old,new", [
    ("trap report EXIT", "if true; then\n    trap report EXIT\nfi"),
    ("trap report EXIT", '[[ -n "$THREAD" ]] && trap report EXIT'),
    ("trap report EXIT", 'false || trap report EXIT'),
    ("trap report EXIT", "trap report EXIT &"),
    ("trap report EXIT", "setup() {\n    trap report EXIT\n}\nsetup"),
    ("trap report EXIT", "while false; do\n    trap report EXIT\ndone"),
    ("trap report EXIT", "{ trap report EXIT; } &"),
    ("trap report EXIT", "( trap report EXIT )"),
])
def test_trap_must_be_installed_unconditionally(lint, fixture_script, old, new):
    result = lint(fixture_script(GOOD.replace(old, new)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[exit-report]" in result.stdout, result.stdout


@pytest.mark.parametrize("old,new,rule", [
    (SEND, "    if false; then\n" + SEND + "    fi\n", "exit-report"),
    (SEND, "    while false; do\n" + SEND + "    done\n", "exit-report"),
    (SEND, "    (( rc == 0 )) || " + TELL + " || " + PASTE + "\n", "exit-report"),
    (SEND, "    [[ -n $THREAD ]] && " + TELL + " || " + PASTE + "\n", "exit-report"),
    (SEND, "    : | " + TELL + " || " + PASTE + "\n", "exit-report"),
    ("    local rc=$?\n", "    local rc=$?\n    return 0\n", "exit-report"),
    ("    local rc=$?\n", "    local rc=$?\n    exit 0\n", "exit-report"),
    ("    local rc=$?\n", "    local rc=$?\n    exit \"$rc\"\n", "exit-report"),
    ("    if ! runuser", "    if (( rc == 0 )); then\n        return 0\n    fi\n    if ! runuser", "exit-report"),
    ("    if ! runuser", "    (( rc == 0 )) && return 0\n    if ! runuser", "exit-report"),
    (SEND, "    if ! runuser -u mk -- @OWNER_HOME@/.local/bin/bb thread tell \"$THREAD\" --mode auto \"$message\"; then\n"
           "        if false; then\n            " + PASTE + "\n        fi\n    fi\n", "paste-fallback"),
    (SEND, "    if ! runuser -u mk -- @OWNER_HOME@/.local/bin/bb thread tell \"$THREAD\" --mode auto \"$message\"; then\n"
           "        :\n    else\n        " + PASTE + "\n    fi\n", "paste-fallback"),
    (SEND, "    " + TELL + " || true\n", "paste-fallback"),
    (SEND, "    " + TELL + "\n    " + PASTE + "\n", "paste-fallback"),
    (SEND, "    if ! runuser -u mk -- @OWNER_HOME@/.local/bin/bb thread tell \"$THREAD\" --mode auto \"$message\"; then\n"
           "        return 0\n        " + PASTE + "\n    fi\n", "exit-report"),
])
def test_report_must_be_reachable(lint, fixture_script, old, new, rule):
    assert old in GOOD
    result = lint(fixture_script(GOOD.replace(old, new)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[{rule}]" in result.stdout, result.stdout


@pytest.mark.parametrize("new", [
    # then-branch of a negated header (GOOD itself), else-branch of a plain header
    "    if " + TELL + "; then\n        :\n    else\n        " + PASTE + "\n    fi\n",
    "    " + TELL + " || " + PASTE + "\n",
    "    " + TELL + " || {\n        " + PASTE + "\n    }\n",
    SEND + "    return \"$rc\"\n",
])
def test_reachable_report_forms(lint, fixture_script, new):
    result = lint(fixture_script(GOOD.replace(SEND, new)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("guard", [
    'if [[ $EUID -eq 0 ]]; then\n    exit 1\nfi',
    '[ "$(id -u)" = 0 ] && exit 1',
    'if [ "${EUID}" -eq 0 ]; then\n    return 1\nfi',
])
def test_root_refusal_is_flagged(lint, fixture_script, guard):
    result = lint(fixture_script(GOOD.replace("cd / || exit 1", guard + "\ncd / || exit 1")))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[root-refusal]" in result.stdout, result.stdout


def test_root_check_without_exit_is_fine(lint, fixture_script):
    body = GOOD.replace("cd / || exit 1", 'if [[ $(id -u) -ne 0 ]]; then\n    exec sudo -- "$0" "$@"\nfi\ncd / || exit 1')
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def minimal_path(tmp_path):
    """A PATH holding only the tools the linter itself needs (no shellcheck)."""
    import shutil
    bin_dir = tmp_path / "minimal-bin"
    bin_dir.mkdir()
    for tool in ("bash", "awk", "gawk", "env", "realpath", "grep", "sed", "cat", "sort", "mktemp"):
        found = shutil.which(tool, path="/usr/bin:/bin")
        if found:
            (bin_dir / tool).symlink_to(found)
    return str(bin_dir)


def test_shellcheck_skip_is_disclosed(lint, fixture_script, minimal_path):
    result = lint(fixture_script(), env={"PATH": minimal_path})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SKIP shellcheck not installed" in result.stdout


def test_missing_shellcheck_does_not_mask_other_rules(lint, fixture_script, minimal_path):
    result = lint(fixture_script(GOOD.replace("set -euo pipefail", "set -eo pipefail")),
                  env={"PATH": minimal_path})
    assert result.returncode == 1
    assert "[nounset]" in result.stdout
    assert "SKIP shellcheck not installed" in result.stdout


def test_no_skip_message_when_shellcheck_runs(lint, fixture_script, tmp_path):
    checker = tmp_path / "shellcheck"
    checker.write_text("#!/bin/bash\nprintf '%s\\n' \"$*\" > \"$0.args\"\nexit 0\n")
    checker.chmod(0o755)
    script = fixture_script()
    result = lint(script, env={**os.environ, "PATH": f"{tmp_path}:/usr/bin:/bin"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SKIP shellcheck" not in result.stdout
    args = (tmp_path / "shellcheck.args").read_text()
    assert str(script) in args
    assert "SC2154" in args


@pytest.mark.parametrize("operation", [
    "git config --global --add safe.directory /srv/repo\ngit -C /srv/repo status",
    "git config --global --add safe.directory /srv/a\ngit config --global --add safe.directory /srv/b\n"
    "git -C /srv/a status\ngit -C /srv/b status",
    "git config --global --add safe.directory '*'\ngit -C /srv/anything status",
    "git config --global --add safe.directory /srv/repo\ncd /srv/repo\ngit status",
    "git -c safe.directory=/srv/repo -C /srv/repo status",
    "git config --global --add safe.directory /srv/repo/\ngit -C /srv/repo status",
])
def test_safe_directory_per_repository(lint, fixture_script, operation):
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("operation", [
    "git config --global --add safe.directory /srv/other\ngit -C /srv/repo status",
    "git config --global --add safe.directory /srv/a\ngit -C /srv/a status\ngit -C /srv/b status",
    "git -c safe.directory=/srv/other -C /srv/repo status",
    "git config --global --add safe.directory /srv/repo\ncd /srv/other\ngit status",
    "git config --global --add safe.directory /srv/repo\ngit status",
    "git config --global --add safe.directory /srv/repo\ngit -C /srv/repo status\ngit -C /srv/repo2 status",
    "git config --global --add safe.directory /srv/repo\nsudo git -C /srv/other status",
])
def test_safe_directory_wrong_repository(lint, fixture_script, operation):
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[git-safe-directory]" in result.stdout, result.stdout


def test_git_word_in_data_is_not_a_git_command(lint, fixture_script):
    result = lint(fixture_script(with_payload("printf '%s\\n' git status\necho git")))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("line", [
    "bash {path} --check",
    "$ bash {path} --check",
    "  bash '{path}' --check",
    "bash \"{path}\"",
])
def test_handoff_accepts_pinned_commands(lint, fixture_script, tmp_path, line):
    path = fixture_script()
    message = tmp_path / "message.md"
    message.write_text("Run:\n```bash\n" + line.format(path=path) + "\n```\n" + hashlib.sha256(path.read_bytes()).hexdigest() + '\n')
    result = lint("--handoff-message", message, path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("text", [
    "Reference only: {path}\n",
    "The script {path} is attached.\n",
    "sudo {path} --check\n",
    "# bash {path}\n",
    "bash {path}.bak\n",
    "echo {path}\n",
    "bash relative.sh {path}\n",
    "",
])
def test_handoff_rejects_unpinned_text(lint, fixture_script, tmp_path, text):
    path = fixture_script()
    message = tmp_path / "message.md"
    message.write_text(text.format(path=path))
    result = lint("--handoff-message", message, path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[pinned-handoff]" in result.stdout, result.stdout


def test_handoff_absent_is_disclosed(lint, fixture_script):
    result = lint(fixture_script(), auto_handoff=False)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[pinned-handoff]" in result.stdout


def test_handoff_present_has_no_skip(lint, fixture_script, tmp_path):
    path = fixture_script()
    message = tmp_path / "message.md"
    message.write_text(f"bash {path}\n")
    result = lint("--handoff-message", message, path)
    assert "SKIP handoff-message" not in result.stdout


def test_help_discloses_heuristics(lint):
    result = lint("--help")
    assert result.returncode == 0
    assert "heuristic" in result.stdout.lower()


@pytest.mark.parametrize("old,new,rule", [
    ('if ! runuser -u mk -- @OWNER_HOME@/.local/bin/bb',
     'if ! echo @OWNER_HOME@/.local/bin/bb', 'exit-report'),
    ('runuser -u mk -- touch @OWNER_HOME@/example', 'if true; then trap - EXIT; fi', 'exit-report'),
    ('runuser -u mk -- touch @OWNER_HOME@/example', 'report() { :; }', 'exit-report'),
    ('runuser -u mk -- touch @OWNER_HOME@/example', 'command trap - EXIT', 'exit-report'),
    ('runuser -u mk -- touch @OWNER_HOME@/example', 'report() { }', 'exit-report'),
    ('local message="handoff $result exit=$rc"', "local message='handoff $result exit=$rc'", 'exit-report'),
    ('"$message"\n    fi', '"$message" >/dev/null\n    fi', 'paste-fallback'),
    ('"$message"\n    fi', '"$message" 1>/tmp/paste\n    fi', 'paste-fallback'),
    ('"$message"\n    fi', '"$message">/dev/null\n    fi', 'paste-fallback'),
    ('"$message"\n    fi', "'$message'\n    fi", 'paste-fallback'),
])
def test_round2_report_regressions(lint, fixture_script, old, new, rule):
    result = lint(fixture_script(GOOD.replace(old, new)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[{rule}]" in result.stdout


@pytest.mark.parametrize("operation,rule", [
    ('git config --global --get safe.directory /srv/repo\ngit -C /srv/repo status', 'git-safe-directory'),
    ('git config --local --add safe.directory /srv/repo\ngit -C /srv/repo status', 'git-safe-directory'),
    ('if false; then git config --global --add safe.directory /srv/repo; fi\ngit -C /srv/repo status', 'git-safe-directory'),
    ("runuser -u mk -- bash -c 'true; touch /tmp/fixed'", 'sticky-writes'),
    ("bash -c 'true; git -C /srv/repo status'", 'git-safe-directory'),
    ("bash -c 'true; touch @OWNER_HOME@/file'", 'mk-home-user'),
    ('command touch /tmp/fixed', 'sticky-writes'),
    ("bash -c 'command touch /tmp/fixed'", 'sticky-writes'),
    ("runuser -u mk -- bash -c 'true; builtin printf x >/tmp/fixed'", 'sticky-writes'),
    ('builtin printf x >/tmp/fixed', 'sticky-writes'),
    ('command touch @OWNER_HOME@/file', 'mk-home-user'),
    ('builtin printf x >@OWNER_HOME@/file', 'mk-home-user'),
])
def test_round2_command_regressions(lint, fixture_script, operation, rule):
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[{rule}]" in result.stdout


@pytest.mark.parametrize("operation", [
    'git -c safe.directory=/srv/repo -C/srv/repo status',
    'git config --global --set safe.directory /srv/repo\ngit -C/srv/repo status',
    "runuser -u mk -- bash -c 'true; touch @OWNER_HOME@/file; git -C @OWNER_HOME@/repo status'",
    'command printf "%s\\n" @OWNER_HOME@/example',
    'builtin printf "%s\\n" @OWNER_HOME@/example',
    "bash -c 'true; runuser -u mk -- touch @OWNER_HOME@/file'",
    "bash -c 'printf %s @OWNER_HOME@/example'",
])
def test_round2_valid_commands(lint, fixture_script, operation):
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("guard", [
    'if [[ $EUID -ne 0 ]]; then exit 1; fi',
    'if [[ $(id -u) -ne 0 ]]; then exit 1; fi',
    '[[ $(id -u) -ne 0 ]] && exit 1',
    '(( EUID != 0 )) && exit 1',
    '[[ $EUID -eq 0 ]] || exit 1',
    '[ "$(id -u)" = 0 ] || exit 1',
    'if ! [[ $EUID -eq 0 ]]; then exit 1; fi',
    '! [[ $EUID -eq 0 ]] && exit 1',
])
def test_round2_guards_permit_root(lint, fixture_script, guard):
    result = lint(fixture_script(GOOD.replace('cd / || exit 1', guard + '\ncd / || exit 1')))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("suffix", [" '", ' "', ' ||', ' &&', ' |'])
def test_round2_handoff_must_parse(lint, fixture_script, tmp_path, suffix):
    path = fixture_script()
    message = tmp_path / 'message.md'
    message.write_text(f'bash {path}' + suffix + '\n')
    result = lint('--handoff-message', message, path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[pinned-handoff]' in result.stdout


@pytest.mark.parametrize("old,new,rule", [
    ('runuser -u mk -- touch @OWNER_HOME@/example', 'trap - 0', 'exit-report'),
    ('runuser -u mk -- touch @OWNER_HOME@/example', 'trap - EXIT INT', 'exit-report'),
    ('    if ! runuser', '    false\n    if ! runuser', 'exit-report'),
    ('        printf', '        false\n        printf', 'exit-report'),
    ('trap report EXIT', "trap 'report >/dev/null' EXIT", 'paste-fallback'),
    ('trap report EXIT', "trap 'report 1>/tmp/paste' EXIT", 'paste-fallback'),
    ('trap report EXIT', 'wrapper() { report >/dev/null; }\ntrap wrapper EXIT', 'paste-fallback'),
    ('    local message="handoff $result exit=$rc"',
     '    local message="constant"\n    if false; then message="handoff $result exit=$rc"; fi', 'exit-report'),
    ('    local message="handoff $result exit=$rc"',
     '    local message="constant"\n    while false; do message="handoff $result exit=$rc"; done', 'exit-report'),
    ('    local message="handoff $result exit=$rc"',
     '    local message="constant"\n    false && message="handoff $result exit=$rc"', 'exit-report'),
    ('    local message="handoff $result exit=$rc"',
     '    local message="constant"\n    true || message="handoff $result exit=$rc"', 'exit-report'),
    ('    local rc=$?', '    local rc=$?\n    rc=0', 'exit-report'),
    ('cd / || exit 1', 'if false; then cd /; fi\ntouch ./fixed', 'readable-cwd'),
])
def test_round3_report_regressions(lint, fixture_script, old, new, rule):
    result = lint(fixture_script(GOOD.replace(old, new)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f'[{rule}]' in result.stdout


@pytest.mark.parametrize('operation', [
    '/usr/bin/touch /tmp/fixed', 'runuser -u mk -- touch /tmp/fixed',
    'sudo -u mk touch /tmp/fixed', 'env FOO=x /usr/bin/touch /tmp/fixed',
    'sudo -u mk env FOO=x /usr/bin/touch /tmp/fixed',
])
def test_round3_wrapped_writes(lint, fixture_script, operation):
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[sticky-writes]' in result.stdout


@pytest.mark.parametrize('reset', [
    '--unset-all safe.directory', '--unset safe.directory /srv/repo',
    '--add safe.directory ""', 'safe.directory ""',
    '--replace-all safe.directory /srv/other',
])
def test_round3_removed_trust(lint, fixture_script, reset):
    operation = 'git config --global --add safe.directory /srv/repo\n'
    operation += 'git config --global ' + reset + '\ngit -C /srv/repo status'
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[git-safe-directory]' in result.stdout


@pytest.mark.parametrize('operation', [
    'git config --global safe.directory /srv/repo\ngit -C /srv/repo status',
    'git config --global --replace-all safe.directory /srv/repo\ngit -C /srv/repo status',
])
def test_round3_valid_trust(lint, fixture_script, operation):
    result = lint(fixture_script(with_payload(operation)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('old,new', [
    ('trap report EXIT', 'trap report EXIT INT'),
    ('trap report EXIT', 'trap report 0 INT'),
    ('    if ! runuser', '    set +e\n    false\n    if ! runuser'),
    ('    if ! runuser', '    false || true\n    if ! runuser'),
    ('        printf', '        set +e\n        false\n        printf'),
])
def test_round3_valid_reporting(lint, fixture_script, old, new):
    result = lint(fixture_script(GOOD.replace(old, new)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('suffix', [' <<EOF', " <<'EOF'", ' <<-EOF'])
def test_round3_unterminated_handoff_heredoc(lint, fixture_script, tmp_path, suffix):
    path = fixture_script()
    message = tmp_path / 'message.md'
    message.write_text(f'bash {path}{suffix}\n')
    result = lint('--handoff-message', message, path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[pinned-handoff]' in result.stdout


def test_round3_known_limits(lint, project_root):
    result = lint('--help')
    assert 'KNOWN LIMITS' in result.stdout
    assert 'KNOWN LIMITS' in (project_root / 'scripts/script-lint.sh').read_text()


DOWNLOAD_OUTPUTS = [
    'curl -fsSLo{target} https://example.com/tool',
    'curl -4fsSLo{target} https://example.com/tool',
    'curl -fsSLo {target} https://example.com/tool',
    'curl -fsSLOo{target} https://example.com/tool',
    'curl -o {target} https://example.com/tool',
    'curl -vLo{target} https://example.com/tool',
    'wget -qO{target} https://example.com/tool',
    'wget -qO {target} https://example.com/tool',
    'wget -qo{target} https://example.com/tool',
    'wget -qa{target} https://example.com/tool',
    'wget -qa {target} https://example.com/tool',
    'wget -qP{target} https://example.com/tool',
    'wget -qP {target} https://example.com/tool',
    'wget -nvO{target} https://example.com/tool',
    'curl -fsSL https://example.com/tool -o{target}',
    'curl -fsSL https://example.com/tool --output {target}',
    'curl -fsSL https://example.com/tool --output={target}',
    'wget https://example.com/tool -o{target}',
    'wget https://example.com/tool -O{target}',
    'wget https://example.com/tool --output={target}',
    'wget https://example.com/tool --output {target}',
    'wget https://example.com/tool --output-document={target}',
    'wget https://example.com/tool --output-document {target}',
]


@pytest.mark.parametrize('command', DOWNLOAD_OUTPUTS)
@pytest.mark.parametrize('target', ['/tmp/fixed', '/var/tmp/fixed', '"$OUTPUT"'])
def test_round4_download_output_sticky_writes(lint, fixture_script, command, target):
    operation = 'OUTPUT=/tmp/fixed\n' + command.format(target=target)
    result = lint(fixture_script(GOOD.replace(
        'runuser -u mk -- touch @OWNER_HOME@/example', operation)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[sticky-writes]' in result.stdout


@pytest.mark.parametrize('command', DOWNLOAD_OUTPUTS)
@pytest.mark.parametrize('setup,target', [
    ('OUTPUT=$(mktemp)', '"$OUTPUT"'),
    ('OUTPUT=$(mktemp -d)', '"$OUTPUT/tool"'),
    ('mkdir /srv/newdir', '/srv/newdir/tool'),
])
def test_round4_download_output_safe(lint, fixture_script, command, setup, target):
    operation = setup + '\n' + command.format(target=target)
    result = lint(fixture_script(GOOD.replace(
        'runuser -u mk -- touch @OWNER_HOME@/example', operation)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('command', [
    'curl -fsSL -o "$(mktemp)" https://example.com/tool',
    'curl -fsSLo"$(mktemp)" https://example.com/tool',
    'curl -fsSL https://example.com/tool',
    'wget -qO "$(mktemp)" https://example.com/tool',
    'wget -qO"$(mktemp)" https://example.com/tool',
    'wget -q https://example.com/tool',
])
def test_bundled_download_output_clean_variants(lint, fixture_script, command):
    result = lint(fixture_script(with_payload(command)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('command', [
    'curl -4fsSLO https://example.com/tool',
    'curl -O /tmp/input',
    'curl -T /tmp/input https://example.com/tool',
    'curl -K /tmp/config https://example.com/tool',
    'curl -fsSLTo/tmp/input https://example.com/tool',
    'curl -fsSLKo/tmp/config https://example.com/tool',
    'curl -T -o/tmp/input https://example.com/tool',
    'curl -K -o/tmp/config https://example.com/tool',
    'curl -- https://example.com/tool -o/tmp/input',
    'wget -- https://example.com/tool -O/tmp/input',
])
def test_download_option_arguments_are_not_output_flags(lint, fixture_script, command):
    result = lint(fixture_script(with_payload(command)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('command', [
    'curl -T /srv/input -4fsSLo /tmp/x https://example.com/tool',
    'curl -K/srv/config -o /tmp/x https://example.com/tool',
    'curl -fsSLOo /tmp/x https://example.com/tool',
    'command curl -4fsSLo/tmp/x https://example.com/tool',
])
def test_download_output_after_other_options(lint, fixture_script, command):
    result = lint(fixture_script(with_payload(command)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[sticky-writes]' in result.stdout


@pytest.mark.parametrize('command', [
    'curl -AT -o /tmp/x',
    'curl -AK -o /tmp/x',
    'wget -UO -O /tmp/x',
    'curl -A agent -o /tmp/x',
    'curl -4fsSLo/tmp/x',
    'curl -fsSLo /tmp/x',
    'wget -qO /tmp/x',
    'curl -? -o /tmp/x',
    'curl -?argument -fsSLo/tmp/x',
    'wget -? -O /tmp/x',
    'wget -?argument --output-document=/tmp/x',
    'curl -? -A -o/tmp/x',
    'curl -? -T -o/tmp/x',
    'curl -? -o -o/tmp/x',
    'wget -g -i -O/tmp/x',
    'wget -Y -U -qO/tmp/x',
])
def test_download_cluster_argument_regressions(lint, fixture_script, command):
    result = lint(fixture_script(with_payload(command)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[sticky-writes]' in result.stdout


# Argument-taking shorts from curl 8.5.0 --help all and wget 1.21.4 --help.
@pytest.mark.parametrize('tool,options', [
    ('curl', 'AbcCdDeEFhHKmoPQrtTuUwxXyYz'),
    ('wget', 'aABDeiIloOPQRtTUwX'),
])
def test_all_download_short_arguments_end_clusters(lint, fixture_script, tool, options):
    output = 'o' if tool == 'curl' else 'O'
    for option in options:
        # An attached argument that looks like an input/output flag is data.
        command = f'{tool} -{option}T -{output} /tmp/x'
        result = lint(fixture_script(with_payload(command)))
        assert '[sticky-writes]' in result.stdout, (command, result.stdout)
        if option not in ('ocD' if tool == 'curl' else 'OoaP'):
            for argument in (f'o/tmp/input', f'-{output}/tmp/input'):
                separator = ' ' if argument.startswith('-') else ''
                command = f'{tool} -{option}{separator}{argument} https://x'
                result = lint(fixture_script(with_payload(command)))
                assert result.returncode == 0, (command, result.stdout, result.stderr)
        command = f'{tool} -{option} -{output}/srv/safe -{output} /tmp/x'
        result = lint(fixture_script(with_payload(command)))
        assert '[sticky-writes]' in result.stdout, (command, result.stdout)


@pytest.mark.parametrize('command', [
    'curl -A -o "$(mktemp)"',
    "curl -A 'o' https://x | tar",
    'curl -Ao/tmp/input https://x',
    'wget -UO/tmp/input https://x',
    'wget -FHO /srv/safe https://x',
    'curl -? -o "$(mktemp)"',
])
def test_download_cluster_argument_clean_variants(lint, fixture_script, command):
    result = lint(fixture_script(with_payload(command)))
    assert result.returncode == 0, result.stdout + result.stderr


def test_round4_known_limits(lint, project_root):
    help_text = lint('--help').stdout
    header = (project_root / 'scripts/script-lint.sh').read_text().split('set -u', 1)[0]
    for text in (help_text, header):
        assert 'later PATH reassignment' in text
        assert 'git config --remove-section' in text
        assert 'stale trust' in text
        assert 'success/failure text' in text
        assert 'reach the message' in text


WRITE_OPTIONS = {
    'curl': [('o', 'output'), ('D', 'dump-header'), ('', 'stderr'),
             ('c', 'cookie-jar'), ('', 'trace'), ('', 'trace-ascii'),
             ('', 'libcurl'), ('', 'etag-save'), ('', 'hsts'), ('', 'alt-svc')],
    'wget': [('O', 'output-document'), ('o', 'output-file'),
             ('a', 'append-output'), ('', 'save-cookies'),
             ('P', 'directory-prefix'), ('', 'rejected-log'),
             ('', 'warc-file'), ('', 'hsts-file'), ('', 'warc-tempdir')],
}
WRITE_FORMS = [
    (tool, form)
    for tool, options in WRITE_OPTIONS.items()
    for short, long in options
    for form in ([f'-{short} {{target}}', f'-q{short}{{target}}',
                  f'-{short}={{target}}'] if short else []) +
                [f'--{long} {{target}}', f'--{long}={{target}}',
                 f'--{long[:3]} {{target}}', f'--{long[:3]}={{target}}']
]


@pytest.mark.parametrize('tool,form', WRITE_FORMS)
@pytest.mark.parametrize('target,bad', [('/tmp/fixed', True),
                                      ('/var/tmp/fixed', True),
                                      ('/srv/safe', False),
                                      ('"$(mktemp)"', False)])
def test_complete_download_write_options(lint, fixture_script, tool, form, target, bad):
    command = f'{tool} {form.format(target=target)} https://example.com/tool'
    result = lint(fixture_script(with_payload(command)))
    assert ('[sticky-writes]' in result.stdout) == bad, (command, result.stdout)
    assert result.returncode == int(bad), result.stdout + result.stderr


@pytest.mark.parametrize('options', [
    '--output-dir {directory} -o fixed',
    '-o fixed --output-dir={directory}',
    '--out={directory} -o fixed',
    '--output-dir {directory} -O',
    '--output-dir={directory} -J',
    '--create-dirs --output-dir {directory} -o nested/fixed',
    '--cre --output-dir={directory} --output=nested/fixed',
])
@pytest.mark.parametrize('directory,bad', [('/tmp', True), ('/var/tmp', True),
                                         ('/srv/safe', False), ('"$(mktemp -d)"', False)])
def test_download_output_directory_composition(lint, fixture_script, options, directory, bad):
    command = 'curl ' + options.format(directory=directory) + ' https://example.com/tool'
    result = lint(fixture_script(with_payload(command)))
    assert ('[sticky-writes]' in result.stdout) == bad, (command, result.stdout)
    assert result.returncode == int(bad), result.stdout + result.stderr


@pytest.mark.parametrize('flag', ['-O', '-J', '-fsSLJO', '--remote-name',
                                  '--remote-header-name', '--remote-name-all',
                                  '--rem', '--remote-n'])
@pytest.mark.parametrize('cwd,bad', [('/tmp', True), ('/var/tmp', True), ('/srv', False)])
def test_remote_name_sticky_cwd(lint, fixture_script, flag, cwd, bad):
    body = with_payload(f'curl {flag} https://example.com/tool').replace('cd / ||', f'cd {cwd} ||')
    result = lint(fixture_script(body))
    assert ('[sticky-writes]' in result.stdout) == bad, result.stdout
    assert result.returncode == int(bad), result.stdout + result.stderr


@pytest.mark.parametrize('command', [
    'wget --save-headers /tmp/input',
    'curl --create-dirs https://example.com/tool',
    'curl --output-dir /tmp -o /srv/safe https://example.com/tool',
    'curl --output-dir /tmp -o - https://example.com/tool',
    'curl --trace - --stderr - --dump-header -',
    'curl --trace-ascii %',
    'curl --etag-compare /tmp/input',
    'wget --load-cookies=/tmp/input',
    'curl --trace-time --trace-ids https://example.com/tool',
    'curl -- --dump-header /tmp/input',
    'wget -- --save-cookies=/tmp/input',
])
def test_complete_download_write_clean_variants(lint, fixture_script, command):
    result = lint(fixture_script(with_payload(command)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('tool,long', [
    (tool, long) for tool, options in WRITE_OPTIONS.items() for _, long in options
])
def test_every_download_write_prefix(lint, fixture_script, tool, long):
    for size in range(1, len(long) + 1):
        for separator in (' ', '='):
            command = f'{tool} --{long[:size]}{separator}/tmp/fixed https://example.com/tool'
            result = lint(fixture_script(with_payload(command)))
            assert '[sticky-writes]' in result.stdout, (command, result.stdout)


@pytest.mark.parametrize('option', ['--trace', '--trace-ascii'])
def test_trace_stdout_in_sticky_cwd(lint, fixture_script, option):
    body = with_payload(f'curl {option} % https://example.com/tool').replace('cd / ||', 'cd /tmp ||')
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('directory,bad', [('/srv/safe', False), ('/tmp', True)])
def test_output_directory_overrides_sticky_cwd(lint, fixture_script, directory, bad):
    body = with_payload(f'curl --create-dirs -o fixed --output-dir {directory} https://example.com/tool')
    body = body.replace('cd / ||', 'cd /tmp ||')
    result = lint(fixture_script(body))
    assert result.returncode == int(bad), result.stdout + result.stderr


def test_download_known_limits_are_disclosed(lint, project_root):
    header = (project_root / 'scripts/script-lint.sh').read_text().split('set -u', 1)[0]
    for text in (lint('--help').stdout, header):
        for limit in ('.curlrc', '.wgetrc', 'wget -e', '%output{file}',
                      '--expand-*', '--variable', 'implicit', '--next',
                      'Long read-option' if text == header else 'long read-option'):
            assert limit.lower() in text.lower()


@pytest.mark.parametrize('body,rule', [
    (GOOD.replace('if [[ ${1:-} == --check ]]; then exit 0; fi', '# no safe dry run'), 'check-mode'),
    (GOOD.replace('runuser -u mk -- tee', 'tee'), 'report-storage'),
    (GOOD.replace('<<< "$message"', '<<< "unrelated"'), 'report-storage'),
    (GOOD.replace('if ! runuser -u mk -- @OWNER_HOME@/.local/bin/bb', 'if ! sudo -u mk -- @OWNER_HOME@/.local/bin/bb'), 'exit-report'),
    (GOOD.replace('runuser -u mk -- touch', 'sudo -u mk -- touch'), 'mk-home-user'),
])
def test_v4_requirements(lint, fixture_script, body, rule):
    result = lint(fixture_script(body))
    assert result.returncode == 1, result.stdout
    assert f'[{rule}]' in result.stdout


def test_v4_hash_tracks_final_bytes(lint, fixture_script, tmp_path):
    path = fixture_script()
    message = tmp_path / 'message.md'
    message.write_text(f'bash {path}\n{hashlib.sha256(path.read_bytes()).hexdigest()}\n')
    assert lint('--handoff-message', message, path).returncode == 0
    path.write_text(GOOD + '\n# changed\n')
    result = lint('--handoff-message', message, path)
    assert result.returncode == 1
    assert '[handoff-sha256]' in result.stdout


@pytest.mark.parametrize('operation', [
    'chmod 777 /srv/file', 'chown mk /srv/file', 'setfacl -m u:mk:rw /srv/file',
    'usermod -aG root mk', 'visudo', 'echo x >/etc/sudoers.d/mk',
    'echo x > /srv/settings.local.json', 'echo x > /srv/.claude/settings.json',
    'echo "permission rule"', 'mystery-command --do-stuff',
])
def test_v4_manual_review(lint, fixture_script, operation):
    path = fixture_script(with_payload('# authorized permission edit\n' + operation))
    result = lint(path)
    assert result.returncode == 0, result.stdout
    assert 'REVIEW' in result.stdout
    assert lint('--strict', path).returncode == 1


@pytest.mark.parametrize('operation', [
    'install -m 0777 /srv/input /srv/output',
    'mkdir -m 0777 /srv/output', 'mkdir -pm0777 /srv/output',
    'install --mode=0777 /srv/input /srv/output',
    'mkdir --mode 0777 /srv/output',
    'install -o mk /srv/input /srv/output',
    'install -gmk /srv/input /srv/output',
    'install --owner=mk --group=mk /srv/input /srv/output',
    'runuser -u mk -- /usr/bin/install -Dm755 /srv/input /srv/output',
    'command mkdir --mode=755 /srv/output',
])
def test_permission_changing_creation_options(lint, fixture_script, operation):
    path = fixture_script(with_payload(operation))
    result = lint(path)
    assert result.returncode == 0, result.stdout
    assert 'REVIEW' in result.stdout
    assert lint('--strict', path).returncode == 1


@pytest.mark.parametrize('operation', [
    'install /srv/input /srv/output', 'mkdir -p /srv/output',
    'install -t /srv/output /srv/input',
    'install -S -m /srv/input /srv/output',
    'install --suffix=--mode=0777 /srv/input /srv/output',
    'install -- --mode=0777 /srv/output', 'mkdir -- -m',
    "printf '%s\\n' 'install -m 0777'",
])
def test_creation_options_clean_variants(lint, fixture_script, operation):
    result = lint('--strict', fixture_script(with_payload(operation)))
    assert result.returncode == 0, result.stdout
    assert 'REVIEW' not in result.stdout


@pytest.mark.parametrize('grant', ['chmod o+r "$message.other"', 'chown mk "$message.other"',
                                   'chmod o+r --reference="$message" "$message"'])
def test_v4_readable_grant_must_name_the_report_file(lint, fixture_script, grant):
    body = GOOD.replace('local message="handoff $result exit=$rc"',
                        'local message=$(mktemp)\n    printf "handoff %s exit=%s\\n" "$result" "$rc" > "$message"\n    ' + grant)
    body = body.replace('--mode auto "$message"', '--mode auto --message-file "$message"')
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[report-readable]' in result.stdout


def test_v4_message_file_must_be_readable(lint, fixture_script):
    body = GOOD.replace('local message="handoff $result exit=$rc"',
                        'local message=$(mktemp)\n    printf "handoff %s exit=%s\\n" "$result" "$rc" > "$message"')
    body = body.replace('--mode auto "$message"', '--mode auto --message-file "$message"')
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[report-readable]' in result.stdout


@pytest.mark.parametrize('header,code', [('', 1), ('# vizier-script\n', 0)])
def test_v4_vizier_reporter(lint, fixture_script, header, code):
    body = vizier_report(header)
    result = lint(fixture_script(body))
    assert result.returncode == code, result.stdout


def test_v4_clean_script_has_no_manual_review(lint, fixture_script):
    result = lint('--strict', fixture_script())
    assert result.returncode == 0, result.stdout
    assert 'REVIEW' not in result.stdout


@pytest.mark.parametrize('replacement', [
    '# --check', 'echo "--check $1"', 'if echo "--check $1"; then true; fi',
])
def test_v4_check_must_be_argument_handler(lint, fixture_script, replacement):
    body = GOOD.replace('if [[ ${1:-} == --check ]]; then exit 0; fi', replacement)
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[check-mode]' in result.stdout


def test_v4_case_check_handler(lint, fixture_script):
    body = GOOD.replace('if [[ ${1:-} == --check ]]; then exit 0; fi',
                        'case "${1:-}" in\n --check) exit 0 ;;\n esac')
    assert lint(fixture_script(body)).returncode == 0


@pytest.mark.parametrize('line', ['{path}', '/bin/bash {path}', '/usr/bin/bash {path}'])
def test_v4_handoff_requires_bash_literal(lint, fixture_script, tmp_path, line):
    path = fixture_script()
    message = tmp_path / 'message.md'
    message.write_text(line.format(path=path) + '\n' + hashlib.sha256(path.read_bytes()).hexdigest())
    result = lint('--handoff-message', message, path)
    assert result.returncode == 1
    assert '[pinned-handoff]' in result.stdout


@pytest.mark.parametrize('storage', [
    'runuser -u mk -- tee "@OWNER_HOME@/.local/share/bb/threads/other/report.txt" <<< "$message" >/dev/null || true',
    'runuser -u mk -- cp /srv/unrelated "@OWNER_HOME@/.local/share/bb/threads/$THREAD/$message" || true',
    'runuser -u mk -- tee "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" < /dev/null; echo "$message"',
])
def test_v4_storage_must_save_report_for_target(lint, fixture_script, storage):
    body = GOOD.replace('runuser -u mk -- tee "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" <<< "$message" >/dev/null || true', storage)
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[report-storage]' in result.stdout


@pytest.mark.parametrize('producer', [
    "printf 'send failed\\n' \"$message\"",
    "printf '%%s\\n' \"$message\"",
    "printf '%s %d\\n' unrelated \"$message\"",
    "printf '%.3s\\n' \"$message\"",
    "printf 'send failed\\c%s' \"$message\"",
    'printf "send failed\\c$message"',
    "printf '%s\\n' '$message'",
])
def test_printf_storage_must_consume_full_message(lint, fixture_script, producer):
    body = GOOD.replace('<<< "$message"', '').replace(
        'runuser -u mk -- tee', producer + ' | runuser -u mk -- tee')
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[report-storage]' in result.stdout


@pytest.mark.parametrize('producer', [
    "printf '%s\\n' \"$message\"", "printf '%b\\n' \"$message\"",
    'printf "report: $message\\n"',
    "printf '%%s %s\\n' \"${message}\"",
    "printf '%d %s\\n' 0 \"$message\"",
    "printf '%s\\n' unrelated \"$message\"",
    "printf '\\\\c %s\\n' \"$message\"",
    'echo "$message"',
])
def test_printf_storage_clean_variants(lint, fixture_script, producer):
    body = GOOD.replace('<<< "$message"', '').replace(
        'runuser -u mk -- tee', producer + ' | runuser -u mk -- tee')
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout


def file_report():
    body = GOOD.replace('local message="handoff $result exit=$rc"',
                        'local message=$(mktemp)\n    printf "handoff %s exit=%s\\n" "$result" "$rc" > "$message"\n    chown mk "$message" || true')
    body = body.replace('--mode auto "$message"', '--mode auto --message-file "$message"')
    body = body.replace('tee "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" <<< "$message"',
                        'cp "$message" "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt"')
    return body


@pytest.mark.parametrize('isfile,producer', [
    (False, "printf '%s\\n' \"$message\""),
    (False, 'echo "$message"'),
    (True, 'cat "$message"'),
])
@pytest.mark.parametrize('redirect', [
    '>/dev/null', '> /srv/report', '1>/dev/null', '>>/srv/report',
    '>&2', '&>/dev/null', '> /srv/report 2>&1',
])
def test_storage_producer_stdout_must_reach_tee(lint, fixture_script, isfile, producer, redirect):
    storage = 'runuser -u mk -- tee "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" >/dev/null || true'
    if isfile:
        body = file_report().replace(
            "printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"",
            'cat "$message"').replace(
            'runuser -u mk -- cp "$message" "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" >/dev/null || true',
            producer + ' ' + redirect + ' | ' + storage)
    else:
        body = GOOD.replace(
            'runuser -u mk -- tee "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" <<< "$message" >/dev/null || true',
            producer + ' ' + redirect + ' | ' + storage)
    result = lint(fixture_script(body))
    assert result.returncode == 1, result.stdout
    assert '[report-storage]' in result.stdout


@pytest.mark.parametrize('isfile,producer', [
    (False, "printf '%s\\n' \"$message\""),
    (False, 'echo "$message"'),
    (True, 'cat "$message"'),
])
@pytest.mark.parametrize('redirect', ['', '2>/dev/null', '2>>/srv/errors'])
def test_storage_producer_unredirected_stdout_is_clean(lint, fixture_script, isfile, producer, redirect):
    storage = 'runuser -u mk -- tee "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" >/dev/null || true'
    if isfile:
        body = file_report().replace(
            "printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"",
            'cat "$message"').replace(
            'runuser -u mk -- cp "$message" "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" >/dev/null || true',
            producer + ' ' + redirect + ' | ' + storage)
    else:
        body = GOOD.replace(
            'runuser -u mk -- tee "@OWNER_HOME@/.local/share/bb/threads/$THREAD/report.txt" <<< "$message" >/dev/null || true',
            producer + ' ' + redirect + ' | ' + storage)
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout


def vizier_report(header='# vizier-script\n'):
    body = file_report().replace('set -euo pipefail', header + 'set -euo pipefail')
    body = body.replace('@OWNER_HOME@/.local/bin/bb thread tell "$THREAD" --mode auto',
                        '@OWNER_HOME@/.local/bin/vizier-tell')
    return body.replace("printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"",
                        'cat "$message"')


@pytest.mark.parametrize('thread', [None, 'thr_example'])
def test_vizier_message_file_without_positional_thread(lint, fixture_script, thread):
    body = vizier_report().replace('message=', 'MSG=').replace('$message', '$MSG')
    args = ('--thread', thread) if thread else ()
    result = lint(*args, fixture_script(body))
    assert result.returncode == 0, result.stdout


def test_vizier_storage_uses_creating_thread(lint, fixture_script):
    body = vizier_report().replace('/threads/$THREAD/report.txt', '/threads/other/report.txt')
    result = lint('--thread', 'thr_example', fixture_script(body))
    assert result.returncode == 1
    assert '[report-storage]' in result.stdout


def test_vizier_rejects_bb_arguments(lint, fixture_script):
    body = vizier_report().replace('vizier-tell --message-file',
                                   'vizier-tell "$THREAD" --mode auto --message-file')
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[exit-report]' in result.stdout


@pytest.mark.parametrize('fallback', [
    "printf 'send failed\\n' \"$message\"",
    "printf '%%s\\n' \"$message\"",
    "printf '%s\\n' unrelated \"$message\" >/dev/null",
    "printf '%s %d\\n' unrelated \"$message\"",
    "printf '%.3s\\n' \"$message\"",
    "printf 'send failed\\c%s' \"$message\"",
    'printf "send failed\\c$message"',
    "printf '%s\\n' '$message'",
])
def test_printf_fallback_must_consume_full_message(lint, fixture_script, fallback):
    body = GOOD.replace("printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"", fallback)
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[paste-fallback]' in result.stdout


@pytest.mark.parametrize('fallback', [
    "printf '%s\\n' \"$message\"", "printf '%b\\n' \"$message\"",
    'printf "report: $message\\n"',
    "printf '%%s %s\\n' \"${message}\"",
    "printf '%d %s\\n' 0 \"$message\"",
    "printf '%s\\n' unrelated \"$message\"",
    "printf '\\\\c %s\\n' \"$message\"",
    'echo "$message"',
])
def test_printf_fallback_clean_variants(lint, fixture_script, fallback):
    body = GOOD.replace("printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"", fallback)
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout


def test_v4_filename_is_not_full_report_fallback(lint, fixture_script):
    result = lint(fixture_script(file_report()))
    assert result.returncode == 1
    assert '[paste-fallback]' in result.stdout


def test_v4_owned_file_and_cat_fallback(lint, fixture_script):
    body = file_report().replace("printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"",
                                 "printf 'BEGIN PASTE BLOCK\\n'\n        cat \"$message\"\n        printf 'END PASTE BLOCK\\n'")
    assert lint(fixture_script(body)).returncode == 0


def test_v4_permission_label_alone_is_not_review(lint, fixture_script):
    result = lint('--strict', fixture_script(with_payload('# permission rule authorized\ntrue')))
    assert result.returncode == 0, result.stdout


def test_v4_full_report_needs_no_paste_label(lint, fixture_script):
    body = GOOD.replace("printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n'", "printf '%s\\n'")
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout


def test_v4_vizier_marker_must_be_header(lint, fixture_script):
    body = GOOD.replace('local result', '# vizier-script\n    local result')
    body = body.replace('@OWNER_HOME@/.local/bin/bb thread tell', '@OWNER_HOME@/.local/bin/vizier-tell')
    assert lint(fixture_script(body)).returncode == 1


@pytest.mark.parametrize('consumer_redirect', ['< /dev/null', '0< /dev/null', '<<< "x"'])
def test_storage_pipeline_consumer_stdin_redirect_is_rejected(lint, fixture_script, consumer_redirect):
    # The producer's stdout never reaches tee when tee's stdin is redirected.
    body = GOOD.replace('<<< "$message" >/dev/null', consumer_redirect + ' >/dev/null').replace(
        'runuser -u mk -- tee', "printf '%s\\n' \"$message\" | runuser -u mk -- tee")
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[report-storage]' in result.stdout


@pytest.mark.parametrize('cat_form', ['cat "$message.other"', 'cat "${message}x"', 'cat -n "$message"'])
def test_file_report_cat_must_read_exact_report_file(lint, fixture_script, cat_form):
    body = file_report().replace(
        "printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"",
        "printf 'BEGIN PASTE BLOCK\\n'\n        " + cat_form + "\n        printf 'END PASTE BLOCK\\n'")
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[paste-fallback]' in result.stdout


def test_file_report_cat_double_dash_is_accepted(lint, fixture_script):
    body = file_report().replace(
        "printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"",
        "printf 'BEGIN PASTE BLOCK\\n'\n        cat -- \"$message\"\n        printf 'END PASTE BLOCK\\n'")
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize('cat_form', ['cat "$message" 2>&1 -n', 'cat "$message" 2>/dev/null extra',
                                       'cat "$message" 2<&0 --help', 'cat "$message" "<" --help'])
def test_file_report_cat_rejects_operands_after_redirect(lint, fixture_script, cat_form):
    body = file_report().replace(
        "printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"",
        "printf 'BEGIN PASTE BLOCK\\n'\n        " + cat_form + "\n        printf 'END PASTE BLOCK\\n'")
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[paste-fallback]' in result.stdout


def test_storage_last_stdin_redirect_wins(lint, fixture_script):
    body = GOOD.replace('<<< "$message" >/dev/null', '<<< "$message" < /dev/null >/dev/null')
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[report-storage]' in result.stdout


def test_storage_other_input_fd_does_not_block_pipeline(lint, fixture_script):
    body = GOOD.replace('<<< "$message" >/dev/null', '3< /dev/null >/dev/null').replace(
        'runuser -u mk -- tee', "printf '%s\\n' \"$message\" | runuser -u mk -- tee")
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout


def test_storage_zero_padded_fd_zero_redirect_is_stdin(lint, fixture_script):
    body = GOOD.replace('<<< "$message" >/dev/null', '00< /dev/null >/dev/null').replace(
        'runuser -u mk -- tee', "printf '%s\\n' \"$message\" | runuser -u mk -- tee")
    result = lint(fixture_script(body))
    assert result.returncode == 1
    assert '[report-storage]' in result.stdout


def test_file_report_cat_accepts_separated_fd_dup(lint, fixture_script):
    body = file_report().replace(
        "printf 'BEGIN PASTE BLOCK\\n%s\\nEND PASTE BLOCK\\n' \"$message\"",
        "printf 'BEGIN PASTE BLOCK\\n'\n        cat \"$message\" 2>& 1\n        printf 'END PASTE BLOCK\\n'")
    result = lint(fixture_script(body))
    assert result.returncode == 0, result.stdout
