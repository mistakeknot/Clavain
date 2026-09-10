#!/usr/bin/env python3
"""Opt-in native preparation, then resume the same session.

The caller supplies its normal native command and existing environment. This
entry point restricts model tools in the first phase; existing host hooks remain
active outside that boundary. It never installs or rewrites host
configuration. It is deliberately limited to the verified rollout hosts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid

import readiness

TIMEOUT = 180
MAX_OUTPUT = 64 * 1024**2
READ_TOOLS = {"Read", "Glob", "Grep", "StructuredOutput"}
ROUTER = "clavain:using-clavain"
DENIED = "Bash,PowerShell,Edit,Write,NotebookEdit,Agent,WebFetch,WebSearch,Skill"


class LauncherInterrupted(BaseException):
    """Cannot be swallowed by routine filesystem OSError handling."""


def stop_group(process):
    """Reap the leader and terminate descendants, including after leader exit."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
    descendants = False
    try:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            descendants = True
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        return {"group_present_at_cleanup": descendants, "group_termination_attempted": True}
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def without(command, names):
    result = []
    index = 0
    while index < len(command):
        arg = command[index]
        if arg in names:
            if index + 1 >= len(command):
                raise ValueError("missing native option value")
            index += 2
        elif any(arg.startswith(name + "=") for name in names):
            index += 1
        else:
            result.append(arg)
            index += 1
    return result


class NativeProcess:
    """Bounded native JSON stream; no model/tool requests are approved here."""
    def __init__(self, command, folder, project, env, name, *, private_control=False):
        self.started = time.monotonic()
        self.deadline = self.started + TIMEOUT
        self.events = queue.Queue()
        self.out = (folder / (name + ".stdout")).open("x")
        self.err = (folder / (name + ".stderr")).open("x")
        self.process = subprocess.Popen(command, cwd=project, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.err, text=True, start_new_session=True)
        self.private_control = private_control
        self.reader = threading.Thread(target=self._read, daemon=True)
        # The reader must inherit blocked termination signals so CPython cannot
        # schedule their main-thread handlers while cleanup masks them there.
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        try:
            self.reader.start()
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    def _read(self):
        count = 0
        try:
            for line in self.process.stdout:
                count += len(line.encode())
                if count > MAX_OUTPUT:
                    raise ValueError("native output exceeded 64 MiB")
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("native stream requires object records")
                # Native config responses can contain authentication settings;
                # never persist them. Claude inventory retains command names only.
                retained = row
                if self.private_control:
                    retained = {"control_response_observed": True, "id": row.get("id")}
                elif row.get("type") == "control_response":
                    body = row.get("response", {})
                    retained = {"type": "control_response", "response": {
                        "subtype": body.get("subtype"), "request_id": body.get("request_id"),
                        "command_names": [c.get("name") for c in body.get("response", {}).get("commands", [])]}}
                self.out.write(json.dumps(retained) + "\n")
                self.out.flush()
                self.events.put(row)
        except (ValueError, OSError) as error:
            self.events.put({"readiness_error": str(error)})
        finally:
            self.events.put({"readiness_eof": True})

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def receive(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("native stage deadline expired")
        try:
            row = self.events.get(timeout=remaining)
        except queue.Empty as error:
            raise TimeoutError("native stage deadline expired") from error
        if row.get("readiness_error") or row.get("readiness_eof"):
            raise ValueError("native stream ended before required completion")
        return row

    def close(self, abort=False):
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        try:
            if abort:
                cleanup = stop_group(self.process)
            try:
                self.process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            if not abort:
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
                cleanup = stop_group(self.process)
            self.reader.join(timeout=1)
            self.process.stdout.close()
            self.out.close()
            self.err.close()
            return {"exit_code": self.process.returncode,
                    "cleanup": cleanup,
                    "duration_seconds": round(time.monotonic() - self.started, 3)}
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)

def codex_config(binary, folder, project, env):
    native = NativeProcess([binary, "app-server"], folder, project, env, "configuration", private_control=True)
    try:
        native.send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "clavain-readiness", "version": "1"}}})
        while native.receive().get("id") != 1:
            pass
        native.send({"method": "initialized", "params": {}})
        native.send({"id": 2, "method": "config/read", "params": {"cwd": str(project), "includeLayers": False}})
        while True:
            row = native.receive()
            if row.get("id") == 2:
                if row.get("error"):
                    raise ValueError("native configuration unavailable")
                config = row.get("result", {}).get("config", {})
                selected = {key: config.get(key) for key in ("approval_policy", "sandbox_mode")}
                selected["mcp_server_names"] = sorted(config.get("mcp_servers", {}))
                return selected
    finally:
        native.close(abort=sys.exc_info()[0] is not None)


def claude_control(command, folder, project, env, name, prompt, session, model):
    command = without(command, {"--input-format"}) + ["--input-format", "stream-json"]
    native = NativeProcess(command, folder, project, env, name)
    rows = []
    try:
        native.send({"type": "control_request", "request_id": "inventory",
                     "request": {"subtype": "initialize"}})
        while True:
            row = native.receive()
            if row.get("type") == "control_response":
                response = row.get("response", {})
                if response.get("subtype") != "success" or response.get("request_id") != "inventory":
                    raise ValueError("native skill inventory unavailable")
                break
        native.send({"type": "user", "session_id": session, "parent_tool_use_id": None,
                     "message": {"role": "user", "content": prompt}})
        inits = []
        while True:
            row = native.receive()
            rows.append(row)
            if row.get("type") == "system" and row.get("subtype") == "init":
                inits.append(row)
                if (not isinstance(row.get("tools"), list) or set(row["tools"]) - READ_TOOLS
                        or row.get("mcp_servers") != [] or row.get("permissionMode") != "dontAsk"
                        or row.get("model") != model or row.get("session_id") != session):
                    raise ValueError("unexpected preparation tool or connector")
            if row.get("type") == "result":
                if len(inits) != 1 or row.get("subtype") != "success" or row.get("is_error") or row.get("session_id") != session:
                    raise ValueError("native preparation did not complete successfully")
                return rows
    finally:
        failed = sys.exc_info()[0] is not None
        stage = native.close(abort=failed)
        save(folder / (name + ".stage.json"), stage)
        if not failed and stage["exit_code"] != 0:
            raise ValueError("native preparation process exited unsuccessfully")


def bounded(command, prompt, folder, project, env, name, timeout=TIMEOUT):
    started = time.monotonic()
    with (folder / (name + ".stdout")).open("xb") as out, (folder / (name + ".stderr")).open("xb") as err:
        process = subprocess.Popen(command, cwd=project, env=env, stdin=subprocess.PIPE,
                                   stdout=out, stderr=err, start_new_session=True)
        try:
            process.communicate(prompt.encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            raise TimeoutError("native stage deadline expired")
        finally:
            cleanup = stop_group(process)
    if process.returncode:
        raise ValueError("native process failed; retain stderr and do not restart")
    raw = readiness.read_regular(folder / (name + ".stdout"), MAX_OUTPUT)
    rows = [json.loads(line) for line in raw.splitlines()]
    return {"exit_code": process.returncode, "status": "exited",
            "cleanup": cleanup,
            "duration_seconds": round(time.monotonic() - started, 3)}, rows


def preparation_command(host, command, folder, mcp_servers=()):
    if host == "codex":
        cmd = without(command, {"-s", "--sandbox", "-o", "--output-last-message", "--output-schema"})
        cmd += ["-s", "read-only", "--output-schema", str(folder / "schema.json"),
                "-o", str(folder / "decision-output.json")]
        for value in ['approval_policy="never"', 'web_search="disabled"', "agents.enabled=false",
                      "features.multi_agent=false", "features.apps=false", "features.plugins=false",
                      "features.browser_use=false", "features.computer_use=false", "features.in_app_browser=false",
                      "features.image_generation=false"]:
            cmd += ["-c", value]
        for name in mcp_servers:
            cmd += ["-c", "mcp_servers." + json.dumps(name) + ".enabled=false"]
        return cmd
    cmd = without(command, {"--tools", "--allowedTools", "--allowed-tools", "--disallowedTools",
                           "--disallowed-tools", "--permission-mode", "--json-schema"})
    existing_denies = [command[i + 1] for i, value in enumerate(command[:-1])
                       if value in ("--disallowedTools", "--disallowed-tools")]
    denied = ",".join([DENIED, *existing_denies])
    cmd += ["--tools", "Read,Glob,Grep", "--allowedTools", "Read,Glob,Grep",
            "--disallowedTools", denied, "--permission-mode", "dontAsk", "--strict-mcp-config",
            "--settings", json.dumps({"disableSkillShellExecution": True, "disableBundledSkills": True}),
            "--json-schema", json.dumps(readiness.SCHEMA)]
    return cmd


def validate_request(request):
    if not isinstance(request, dict):
        raise ValueError("structured native request required")
    host = request.get("host")
    command = request.get("command")
    if host not in readiness.MODELS or not isinstance(command, list) or not command:
        raise ValueError("supported native host and command required")
    if any(not isinstance(arg, str) or not arg or "\x00" in arg for arg in command):
        raise ValueError("invalid native argument")
    forbidden = {"--dangerously-skip-permissions", "--allow-dangerously-skip-permissions", "--yolo",
                 "--dangerously-bypass-approvals-and-sandbox", "--resume", "--continue", "--fork-session",
                 "--plugin-url", "--remote-control", "--cloud", "--background", "--bg", "--bare", "--safe-mode"}
    if any(arg.split("=", 1)[0] in forbidden for arg in command):
        raise ValueError("unsafe or nonfresh native launch")
    if "bypassPermissions" in command or "danger-full-access" in command or "--" in command:
        raise ValueError("unsupported normal permission bypass or inline prompt")
    if not Path(command[0]).is_absolute() or not Path(command[0]).is_file():
        raise ValueError("absolute native executable required")
    if host == "codex" and (len(command) < 2 or command[1] != "exec" or "resume" in command[2:]):
        raise ValueError("fresh Codex exec command required")
    values = ({"-m", "--model", "-c", "--config", "-s", "--sandbox"} if host == "codex" else
              {"--model", "--effort", "--setting-sources", "--plugin-dir", "--permission-mode", "--tools",
               "--allowedTools", "--allowed-tools", "--disallowedTools", "--disallowed-tools",
               "--max-turns", "--session-id", "--output-format"})
    switches = ({"--skip-git-repo-check", "--json"} if host == "codex" else
                {"--strict-mcp-config", "--verbose", "--include-hook-events", "-p", "--print"})
    index, models, seen = (2 if host == "codex" else 1), 0, set()
    while index < len(command):
        option = command[index]
        canonical = {"-m": "--model", "-s": "--sandbox", "-c": "--config", "-p": "--print",
                     "--allowed-tools": "--allowedTools", "--disallowed-tools": "--disallowedTools"}.get(option, option)
        if canonical in seen and canonical != "--plugin-dir":
            raise ValueError("duplicate native option")
        seen.add(canonical)
        if option in switches:
            index += 1
            continue
        if option not in values or index + 1 >= len(command):
            raise ValueError("unsupported native option; no unvalidated launch overrides")
        value = command[index + 1]
        if option == "--session-id":
            if str(uuid.UUID(value)) != value:
                raise ValueError("canonical native session UUID required")
        if option in ("-m", "--model"):
            models += 1
        if option in ("-c", "--config") and value != 'model_reasoning_effort="high"':
            raise ValueError("normal command overrides are limited to pinned effort")
        if option in ("-s", "--sandbox") and value not in ("read-only", "workspace-write"):
            raise ValueError("unsupported normal sandbox")
        if option == "--output-format" and value != "stream-json":
            raise ValueError("native stream-json output required")
        index += 2
    if models != 1:
        raise ValueError("exactly one native model assignment required")
    expected = request.get("expected_model", readiness.MODELS[host])
    if expected != readiness.MODELS[host]:
        if host != "claude" or expected != "claude-opus-5":
            raise ValueError("model change requires the recorded user-authorized capacity fallback")
        readiness.validate_fallback(request.get("fallback"))
    model_flag = "--model" if "--model" in command else "-m"
    if model_flag not in command or command[command.index(model_flag) + 1] != expected:
        raise ValueError("normal command model differs from fixed assignment")
    if host == "claude" and ("--effort" not in command or command[command.index("--effort") + 1] != "high"):
        raise ValueError("Claude high effort must be explicit")
    if host == "codex" and 'model_reasoning_effort="high"' not in command:
        raise ValueError("Codex high effort must be explicit")
    if not isinstance(request.get("prompt"), str) or not request["prompt"].strip():
        raise ValueError("original task prompt required")
    if len(request["prompt"].encode()) > 256 * 1024:
        raise ValueError("task prompt exceeds supported bound")
    timeout = request.get("execution_timeout_seconds", 3600)
    if type(timeout) is not int or not 1 <= timeout <= 43200:
        raise ValueError("execution timeout must be an explicit bounded number of seconds")
    for key in ("source", "project"):
        if not isinstance(request.get(key), str) or not Path(request[key]).is_dir():
            raise ValueError("existing source and project directories required")
    return expected


def verify_router_source(source):
    path = source / "skills/using-clavain/SKILL.md"
    text = readiness.read_regular(path, 64 * 1024).decode()
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError("router frontmatter is not the verified simple form")
    for line in parts[1].splitlines():
        if line.strip() and not line.startswith(("name: ", "description: ")):
            raise ValueError("router contains unverified executable or extended frontmatter")
    if "!`" in text or "```!" in text:
        raise ValueError("router contains shell preprocessing")
    return parts[2].strip()


def verify_router_loaded(original, snapshot, source, body):
    marker = "Base directory for this skill: " + str(source / "skills/using-clavain")
    prefix = readiness.read_regular(snapshot)
    raw = readiness.read_regular(original)
    if not raw.startswith(prefix):
        raise ValueError("native preparation prefix changed")
    call, succeeded, loaded = None, False, False
    for line in raw[len(prefix):].splitlines():
        row = json.loads(line)
        content = row.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for item in content:
            if row.get("type") == "assistant" and item.get("type") == "tool_use":
                if item.get("name") == "Skill" and item.get("input", {}).get("skill") == ROUTER and call is None:
                    call = item.get("id")
                elif not loaded and item.get("name") not in {"Read", "Glob", "Grep"}:
                    raise ValueError("execution tool used before verified router load")
            if row.get("type") == "user" and item.get("type") == "tool_result" and call and item.get("tool_use_id") == call:
                succeeded = not item.get("is_error")
            text = item.get("text", "")
            if (row.get("type") == "user" and row.get("isMeta") and call and succeeded
                    and row.get("sourceToolUseID") == call and marker in text and body in text):
                loaded = True
    if not loaded:
        raise ValueError("native router call, result, body or selected source was not verified")


def project_snapshot(project):
    """Bounded task-state check, excluding Git's internal caches and objects."""
    result, total = {}, 0
    for root, dirs, files in os.walk(project, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files + [d for d in dirs if (Path(root) / d).is_symlink()]:
            path = Path(root) / name
            key = str(path.relative_to(project))
            if path.is_symlink():
                result[key] = {"link": os.readlink(path)}
                continue
            raw = readiness.read_regular(path, 64 * 1024**2)
            total += len(raw)
            if total > 128 * 1024**2 or len(result) >= 20000:
                raise ValueError("project exceeds supported preparation snapshot bound")
            result[key] = hashlib.sha256(raw).hexdigest()
    return result


def input_snapshot(command, source, project, env):
    home = Path(env.get("HOME", str(Path.home())))
    codex = Path(env.get("CODEX_HOME", str(home / ".codex")))
    claude = Path(env.get("CLAUDE_CONFIG_DIR", str(home / ".claude")))
    paths = [Path(command[0]).resolve(), source / "scripts/readiness.py", source / "scripts/native-readiness.py",
             source / "config/routing.yaml", source / "skills/using-clavain/SKILL.md",
             source / "docs/canon/reasoning-routing.md", source / "hooks/hooks.json",
             codex / "config.toml", codex / "hooks.json", codex / "AGENTS.md",
             claude / "settings.json", claude / "CLAUDE.md",
             project / ".claude/settings.json", project / ".claude/settings.local.json",
             project / ".codex/config.toml"]
    paths += [Path(command[i + 1]) / "hooks/hooks.json" for i, arg in enumerate(command[:-1]) if arg == "--plugin-dir"]
    result = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None for path in paths}
    legacy = Path(env.get("CLAUDE_CONFIG_DIR", str(home))) / ".claude.json"
    alternate = claude / ".config.json"
    if alternate.is_file():
        legacy = alternate
    config = json.loads(legacy.read_text()) if legacy.is_file() else {}
    project_config = config.get("projects", {}).get(str(project), {})
    defaults = {"mcpServers": {}, "allowedTools": [], "enabledMcpjsonServers": [],
                "disabledMcpjsonServers": [], "hasTrustDialogAccepted": False}
    relevant = {"global": {k: config.get(k, v) for k, v in defaults.items()},
                "project": {k: project_config.get(k, v) for k, v in defaults.items()}}
    result[str(legacy) + "#permission-and-mcp-projection"] = hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()
    return result


def hook_inventory(command, source, project, env):
    """Observe configured hooks without disabling existing guards or copying commands."""
    home = Path(env.get("HOME", str(Path.home())))
    codex = Path(env.get("CODEX_HOME", str(home / ".codex")))
    claude = Path(env.get("CLAUDE_CONFIG_DIR", str(home / ".claude")))
    paths = [codex / "hooks.json", claude / "settings.json", project / ".claude/settings.json",
             project / ".claude/settings.local.json", source / "hooks/hooks.json"]
    paths += [Path(command[i + 1]) / "hooks/hooks.json" for i, arg in enumerate(command[:-1]) if arg == "--plugin-dir"]
    rows = []
    for path in sorted(set(paths)):
        if not path.is_file():
            continue
        value = json.loads(path.read_text())
        hooks = value.get("hooks", {})
        rows.append({"path": str(path), "configured_hooks_sha256": hashlib.sha256(json.dumps(hooks, sort_keys=True).encode()).hexdigest(),
                     "events": sorted(hooks) if isinstance(hooks, dict) else [],
                     "selection": "configured candidate; native hook events remain separate evidence"})
    return {"scope": "Model tools are restricted; existing host hooks are not sandboxed or disabled by this launcher.",
            "coverage": "Known settings and plugin hook files; not a claim of complete effective host configuration.", "sources": rows}


def native_path(host, session, env):
    if str(uuid.UUID(session)) != session:
        raise ValueError("canonical native session UUID required")
    home = Path(env.get("HOME", str(Path.home())))
    if host == "codex":
        root = Path(env.get("CODEX_HOME", str(home / ".codex")))
        candidates = list(root.glob("sessions/*/*/*/*" + session + ".jsonl"))
    else:
        root = Path(env.get("CLAUDE_CONFIG_DIR", str(home / ".claude")))
        candidates = list(root.glob("projects/*/" + session + ".jsonl"))
    if len(candidates) != 1:
        raise ValueError("exactly one matching native session-store transcript required")
    return candidates[0]


def authorize_resume(folder, decision, binding):
    decision = readiness.validate_decision(json.dumps(decision, ensure_ascii=False))
    if not binding.get("session_id") or binding.get("acceptance") != "not-established":
        raise ValueError("validated native preparation binding required")
    save(folder / "decision.json", decision)
    save(folder / "resume-authorized.json", {"binding": binding,
        "meaning": "Preparation complete; existing task permissions apply. Independent acceptance remains required."})


def verify_execution_native(host, original, snapshot, session, model, sandbox=None, approval=None):
    prefix = readiness.read_regular(snapshot)
    raw = readiness.read_regular(original)
    if not raw.startswith(prefix):
        raise ValueError("native preparation prefix changed during execution")
    rows = [json.loads(line) for line in raw[len(prefix):].splitlines()]
    contexts = []
    for row in rows:
        if host == "codex" and row.get("type") == "turn_context":
            context = row.get("payload", {})
            if sandbox is not None and (context.get("sandbox_policy", {}).get("type") != sandbox or context.get("approval_policy") != approval):
                raise ValueError("native execution permissions differ from normal command")
            contexts.append(context)
        elif host == "claude" and row.get("type") == "assistant":
            if row.get("sessionId") != session or row.get("isSidechain"):
                raise ValueError("execution native identity changed")
            message = row.get("message", {})
            if message.get("model") == "<synthetic>" and all(
                    item.get("type") == "text" for item in message.get("content", [])):
                continue
            contexts.append({"model": message.get("model"), "effort": row.get("effort")})
    if not contexts or any(c.get("model") != model or c.get("effort") != "high" for c in contexts):
        raise ValueError("native execution model or effort evidence differs from assignment")
    return {"path": str(original), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "model": model, "effort": "high"}


def execute_request(request, folder, env=None):
    folder = Path(folder)
    folder.mkdir(mode=0o700)  # Never reuse an interrupted or failed attempt.
    folder = folder.resolve()
    env = dict(os.environ if env is None else env)
    previous_term = signal.getsignal(signal.SIGTERM)
    def interrupted(signum, frame):
        raise LauncherInterrupted("native launcher interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        expected = validate_request(request)
        host = request["host"]
        project, source = Path(request["project"]).resolve(), Path(request["source"]).resolve()
        if Path(__file__).resolve().parent != source / "scripts" or Path(readiness.__file__).resolve().parent != source / "scripts":
            raise ValueError("running launcher and selected source differ")
        router_body = verify_router_source(source)
        if folder == project or project in folder.parents:
            raise ValueError("private launch evidence must be outside the task directory")
        command = list(request["command"])
        command[0] = str(Path(command[0]).resolve())
        before = input_snapshot(command, source, project, env)
        state = project_snapshot(project)
        save(folder / "request.json", request)
        save(folder / "prelaunch.json", {"input_hashes": before, "project": state,
            "hooks": hook_inventory(command, source, project, env),
            "coverage": "Selected configuration and source inputs; credentials are never copied. Runtime counters in .claude.json are excluded from permission/MCP projection."})
        save(folder / "schema.json", readiness.SCHEMA)
        prompt = ("This is the read-only preparation phase of the authorized Clavain two-phase launch. "
            "Read the selected using-clavain router and reasoning-routing canon, plus task evidence needed to classify the work. "
            "During this preparation phase, read the router body directly from the selected source; native Skill is unavailable. "
            "Do not plan an implementation, edit task files, delegate, invoke other skills, publish or use external services. "
            "Emit your own accountable JSON reasons and rationale only; reasons [] is valid for settled work. "
            "The host will persist and bind your native response, then resume this exact session with the original task. "
            "No further permission request is needed for already authorized work. Existing independent acceptance and publication boundaries remain.\n"
            "Selected Clavain source: " + str(source) + "\nOriginal task:\n" + request["prompt"])
        if host == "codex":
            config = codex_config(command[0], folder, project, env)
            save(folder / "native-configuration.json", config)
            if config["approval_policy"] not in ("never", "on-request", "on-failure", "untrusted"):
                raise ValueError("native normal approval policy unavailable or unsupported")
            preparation = preparation_command(host, command, folder, mcp_servers=config["mcp_server_names"])
            save(folder / "preparation-command.json", preparation)
            stage, events = bounded(preparation, prompt, folder, project, env, "preparation")
            save(folder / "preparation.stage.json", stage)
            sessions = {e["thread_id"] for e in events if e.get("type") == "thread.started"}
            if (len(sessions) != 1 or not any(e.get("type") == "turn.completed" for e in events)
                    or any(e.get("type") in ("error", "turn.failed") for e in events)):
                raise ValueError("native preparation completion and identity required")
            session = sessions.pop()
            decision = readiness.validate_decision(readiness.read_regular(folder / "decision-output.json", 16384).decode())
        else:
            session = command[command.index("--session-id") + 1] if "--session-id" in command else str(uuid.uuid4())
            command = without(command, {"--session-id"}) + ["--session-id", session]
            preparation = preparation_command(host, command, folder)
            save(folder / "preparation-command.json", preparation)
            events = claude_control(preparation, folder, project, env, "preparation", prompt, session, expected)
            decision = readiness.validate_decision(json.dumps(events[-1].get("structured_output"), ensure_ascii=False))
        if input_snapshot(command, source, project, env) != before or project_snapshot(project) != state:
            raise ValueError("task or launch inputs changed during preparation")
        original = native_path(host, session, env)
        snapshot = folder / "preparation-native.jsonl"
        snapshot.write_bytes(readiness.read_regular(original))
        binding = readiness.bind_decision(host, snapshot, session, decision, expected, request.get("fallback"))
        binding["source_native_path"] = str(original)
        binding["prelaunch_sha256"] = hashlib.sha256((folder / "prelaunch.json").read_bytes()).hexdigest()
        save(folder / "binding.json", binding)
        if host == "codex":
            sandbox_flag = next((flag for flag in ("-s", "--sandbox") if flag in command), None)
            sandbox = command[command.index(sandbox_flag) + 1] if sandbox_flag else config["sandbox_mode"]
            if sandbox not in ("read-only", "workspace-write"):
                raise ValueError("normal native sandbox unsupported; no permissions widened")
            resume = [command[0], "exec", "resume", session, "--json", "-m", expected,
                "-c", 'model_reasoning_effort="high"', "-c", "sandbox_mode=" + json.dumps(sandbox),
                "-c", "approval_policy=" + json.dumps(config["approval_policy"])]
            if "--skip-git-repo-check" in command:
                resume.append("--skip-git-repo-check")
        else:
            resume = without(command, {"--session-id"}) + ["--resume", session]
        preparation_stage = dict(stage) if host == "codex" else json.loads((folder / "preparation.stage.json").read_text())
        authorize_resume(folder, decision, binding)
        followup = ("Preparation is complete in this same native session. "
            + ("First invoke clavain:using-clavain through the native Skill tool to verify the selected installation. " if host == "claude" else "")
            + "Your own decision is recorded at "
            + str(folder / "decision.json") + ". Use it as CLAVAIN_DECISION_CONTEXT; do not replace its judgment. "
            "Complete the original task under existing permissions and required skill, verification and approval boundaries.\n"
            + request["prompt"])
        save(folder / "resume-request.json", {"command": resume, "prompt": followup, "session_id": session})
        evidence_hashes = {p.name: hashlib.sha256(readiness.read_regular(p)).hexdigest() for p in folder.iterdir()}
        env["CLAVAIN_DECISION_CONTEXT"] = str(folder / "decision.json")
        execution_timeout = request.get("execution_timeout_seconds", 3600)
        if type(execution_timeout) is not int or not 1 <= execution_timeout <= 43200:
            raise ValueError("execution timeout must be an explicit bounded number of seconds")
        stage, events = bounded(resume, followup, folder, project, env, "execution", execution_timeout)
        observed = ({e["thread_id"] for e in events if e.get("type") == "thread.started"} if host == "codex"
                    else {e["session_id"] for e in events if e.get("session_id")})
        if observed != {session}:
            raise ValueError("execution did not preserve exact native session identity")
        terminal = [e for e in events if e.get("type") == ("turn.completed" if host == "codex" else "result")]
        if (not terminal or any(e.get("type") in ("error", "turn.failed") for e in events)
                or (host == "claude" and (terminal[-1].get("subtype") != "success" or terminal[-1].get("is_error")))):
            raise ValueError("native execution completion evidence missing")
        for name, expected_hash in evidence_hashes.items():
            if hashlib.sha256(readiness.read_regular(folder / name)).hexdigest() != expected_hash:
                raise ValueError("preparation evidence changed during execution: " + name)
        if input_snapshot(command, source, project, env) != before:
            raise ValueError("launch inputs changed during execution")
        actual_decision = readiness.validate_decision(readiness.read_regular(folder / "decision.json", 16384).decode())
        digest = hashlib.sha256(json.dumps(actual_decision, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if digest != binding["decision_sha256"] or hashlib.sha256(readiness.read_regular(snapshot)).hexdigest() != binding["native_sha256"]:
            raise ValueError("preparation evidence changed during execution")
        execution_native = verify_execution_native(host, original, snapshot, session, expected,
            sandbox if host == "codex" else None, config["approval_policy"] if host == "codex" else None)
        if host == "claude":
            verify_router_loaded(original, snapshot, source, router_body)
        result = {"native_session_id": session, "binding": binding, "execution_stage": stage,
                  "execution_native": execution_native,
                  "preparation_stage": preparation_stage, "preparation_evidence_sha256": evidence_hashes,
                  "independent_acceptance": None, "status": "executed"}
        save(folder / "result.json", result)
        return result
    except BaseException as error:
        save(folder / "failure.json", {"error": str(error), "status": "failed", "rerun_allowed": False,
                                      "interrupted": isinstance(error, (LauncherInterrupted, KeyboardInterrupt))})
        raise
    finally:
        signal.signal(signal.SIGTERM, previous_term)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(readiness.read_regular(args.request, 512 * 1024))
    print(json.dumps(execute_request(request, args.evidence_dir)))


if __name__ == "__main__":
    main()
