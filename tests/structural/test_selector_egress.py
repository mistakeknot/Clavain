"""Tests for scripts/clavain_selector/egress.py (mk-42j9.7 Task 2).

Every secret-like value used below is assembled at runtime by concatenation
(never written as a single literal), per the plan's Task 2 Step 1 and the
stdlib-only/no-network/no-credential-file constraint for this task. This
module reads no real transcript and no real credential file.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from selector_helpers import make_candidate, make_request, selector_socket_guard  # noqa: F401

from clavain_selector import egress
from clavain_selector.contract import Point, SessionRef

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"


def _cat(*parts: str) -> str:
    return "".join(parts)


def _rep(char: str, n: int) -> str:
    return char * n


def _hexrun(n: int, seed: str) -> str:
    """A deterministic, non-literal lowercase-hex string of length n."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    out = digest
    while len(out) < n:
        out += hashlib.sha256(out.encode("utf-8")).hexdigest()
    return out[:n]


def _mixed_alnum(n: int, seed: str) -> str:
    """A deterministic mixed-case alphanumeric string (upper+lower+digit) of length n."""
    raw = hashlib.sha256(seed.encode("utf-8")).digest()
    out_chars: list[str] = []
    alphabet_upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    alphabet_lower = "abcdefghijklmnopqrstuvwxyz"
    digits = "0123456789"
    i = 0
    while len(out_chars) < n:
        b = raw[i % len(raw)]
        bucket = i % 3
        if bucket == 0:
            out_chars.append(alphabet_upper[b % len(alphabet_upper)])
        elif bucket == 1:
            out_chars.append(alphabet_lower[b % len(alphabet_lower)])
        else:
            out_chars.append(digits[b % len(digits)])
        i += 1
    return "".join(out_chars)


def _b64_secret(n: int, seed: str) -> str:
    """A deterministic standard-base64-alphabet string of length n (mixed case likely)."""
    raw = hashlib.sha256(seed.encode("utf-8")).digest() + hashlib.sha256((seed + "x").encode("utf-8")).digest()
    s = base64.b64encode(raw).decode("ascii").rstrip("=")
    while len(s) < n:
        raw = hashlib.sha256(s.encode("utf-8")).digest()
        s += base64.b64encode(raw).decode("ascii").rstrip("=")
    return s[:n]


def _b64_secret_with_slash(n: int, seed: str, pos: int) -> str:
    s = _b64_secret(n, seed)
    pos = max(1, min(n - 2, pos))
    return s[:pos] + "/" + s[pos + 1 :]


def _refused(text: str, *, point: Point = Point.LIBRARY, high_entropy: bool | None = None) -> egress.Refusal:
    req = make_request(point=point, task=text)
    result = egress.admit(req, high_entropy=high_entropy)
    assert isinstance(result, egress.Refusal), f"expected refusal for: {text[:40]}...(len={len(text)})"
    return result


def _admitted(text: str, *, point: Point = Point.LIBRARY, high_entropy: bool | None = None):
    req = make_request(point=point, task=text)
    result = egress.admit(req, high_entropy=high_entropy)
    assert isinstance(result, egress.AdmittedRequest), (
        f"expected admission for: {text[:60]!r} -- got {result!r}"
    )
    return result


def _refused_in_candidate_description(text: str, *, point: Point = Point.LIBRARY) -> egress.Refusal:
    req = make_request(point=point, task="ordinary task", candidates=(make_candidate(description=text),))
    result = egress.admit(req)
    assert isinstance(result, egress.Refusal)
    return result


# ---------------------------------------------------------------------------
# One test per rule id
# ---------------------------------------------------------------------------


def test_cred_aws_key():
    secret = _cat("AKI", "A", _rep("A", 16))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.aws_key",)
    assert secret not in repr(refusal)
    assert secret not in refusal.detail


def test_cred_aws_secret():
    # A short value (<8 chars) keeps this isolated to cred.aws_secret: the key
    # text also matches cred.assignment's "access_key"/"secret" alternatives,
    # but cred.assignment's VALUE8 requires length >=8.
    secret = _cat("aws_secret_access_key", " = ", _mixed_alnum(5, "aws-secret-short"))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.aws_secret",)


def test_cred_github_token():
    secret = _cat("gh", "p_", _rep("A", 36))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.github_token",)
    assert secret not in repr(refusal)


def test_cred_gitlab_token():
    secret = _cat("glpa", "t-", _rep("A", 20))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.gitlab_token",)


def test_cred_anthropic_key():
    secret = _cat("sk-an", "t-", _rep("A", 20))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.anthropic_key",)


def test_cred_openai_style_key():
    secret = _cat("sk-", "abcDEF", "123456789012345")
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.openai_style_key",)


def test_cred_stripe_key():
    secret = _cat("sk_", "live_", _rep("A", 16))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.stripe_key",)


def test_cred_google_api_key():
    secret = _cat("AIz", "a", _rep("A", 35))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.google_api_key",)


def test_cred_vault_token():
    secret = _cat("hv", "s.", _rep("A", 20))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.vault_token",)


def test_cred_azure_account_key():
    # The "SharedAccessSignature=" form (rather than "AccountKey=") avoids
    # also matching cred.assignment's "access_key" alternative.
    secret = _cat("SharedAccessSignature=", _b64_secret(20, "azure"))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.azure_account_key",)


def test_cred_gcp_service_account():
    secret = _cat('"type": "service_account"')
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.gcp_service_account",)


def test_cred_slack_token():
    secret = _cat("xoxb-", _rep("1234567890", 2))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.slack_token",)


def test_cred_private_key():
    secret = _cat("-----BEGIN ", "RSA PRIVATE KEY", "-----")
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.private_key",)


def test_cred_package_token():
    secret = _cat("npm_", _rep("A", 36))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.package_token",)


def test_cred_netrc():
    secret = _cat("machine api.example.com login bot ", "password ", _mixed_alnum(10, "netrc"))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.netrc",)


def test_cred_jwt():
    secret = _cat("eyJ", _rep("A", 10), ".", _rep("B", 10), ".", _rep("C", 10))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.jwt",)


def test_cred_assignment():
    secret = _cat("api_key", ": ", _mixed_alnum(20, "assignment"))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.assignment",)


def test_cred_password_assignment():
    secret = _cat("password", ": ", "x")
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.password_assignment",)


def test_cred_bearer():
    secret = _cat("Authorization: Bearer ", _mixed_alnum(24, "bearer"))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.bearer",)


def test_cred_basic_auth():
    secret = _cat("Authorization: Basic ", _b64_secret(16, "basic"))
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.basic_auth",)


def test_cred_cookie():
    secret = _cat("Set-Cookie: sessionid=", _hexrun(32, "cookie"), "; Path=/")
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.cookie",)


def test_cred_url_userinfo():
    secret = _cat("https://", "bot", ":", _mixed_alnum(12, "userinfo"), "@example.com/path")
    refusal = _refused(secret)
    assert refusal.rule_ids == ("cred.url_userinfo",)


def test_cred_high_entropy():
    secret = _mixed_alnum(40, "entropy-standalone")
    refusal = _refused(secret, point=Point.POST_TOOL_OUTPUT)
    assert refusal.rule_ids == ("cred.high_entropy",)


def test_cred_loaded_key():
    req = make_request(task=_cat("the key is ", "sekrit-literal-value-xyz"))
    result = egress.admit(req, key_literal="sekrit-literal-value-xyz")
    assert isinstance(result, egress.Refusal)
    assert result.rule_ids == ("cred.loaded_key",)


def test_src_denylisted_path(tmp_path):
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    target = home / ".ssh" / "id_rsa"
    target.write_text("x")
    req = make_request(sources=(target,), project_root=home)
    import os

    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        result = egress.admit(req)
    finally:
        if old_home is not None:
            os.environ["HOME"] = old_home
    assert isinstance(result, egress.Refusal)
    assert "src.denylisted_path" in result.rule_ids


def test_src_outside_project(tmp_path):
    project = tmp_path / "proj"
    # An allowed-owner repo, so this stays isolated to src.outside_project
    # (an unowned project_root would also raise proj.unowned).
    _init_repo_with_origin(project, "git@github.com:mistakeknot/proj.git")
    outside = tmp_path / "elsewhere" / "file.txt"
    outside.parent.mkdir()
    outside.write_text("x")
    req = make_request(sources=(outside,), project_root=project)
    result = egress.admit(req)
    assert isinstance(result, egress.Refusal)
    assert result.rule_ids == ("src.outside_project",)


def test_proj_unowned(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    req = make_request(project_root=repo)
    result = egress.admit(req)
    assert isinstance(result, egress.Refusal)
    assert result.rule_ids == ("proj.unowned",)


def test_size_over_limit():
    req = make_request(task="x" * 90_001)
    result = egress.admit(req)
    assert isinstance(result, egress.Refusal)
    assert result.rule_ids == ("size.over_limit",)


# ---------------------------------------------------------------------------
# test_realistic_payloads_refused
# ---------------------------------------------------------------------------

REALISTIC_REFUSALS = [
    ("password_json", _cat('{"password": "', "hunter2hunter2hunter2", '"}'), "cred.password_assignment"),
    ("api_key_json", _cat('{"api_key":"', _mixed_alnum(24, "apikeyjson"), '"}'), "cred.assignment"),
    ("db_pass_12", _cat("DB_PASS=", _mixed_alnum(12, "dbpass")), "cred.assignment"),
    ("session_key_64hex", _cat("SESSION_KEY=", _hexrun(64, "sessionkey")), "cred.assignment"),
    ("stripe", _cat("sk_", "live_", _rep("Z", 16)), "cred.stripe_key"),
    (
        "gcp_fragment",
        _cat('{"type": "service_account", "private_key_id": "', _hexrun(40, "gcp"), '"}'),
        "cred.gcp_service_account",
    ),
    ("azure_conn", _cat("DefaultEndpointsProtocol=https;AccountKey=", _b64_secret(24, "azureconn")), "cred.azure_account_key"),
    ("aws_secret_spaced", _cat("aws_secret_access_key = ", _mixed_alnum(40, "awssecretspaced")), "cred.aws_secret"),
    ("gitlab", _cat("glpa", "t-", _rep("Q", 20)), "cred.gitlab_token"),
    ("google", _cat("AIz", "a", _rep("Q", 35)), "cred.google_api_key"),
    ("vault", _cat("hv", "s.", _rep("Q", 20)), "cred.vault_token"),
    ("basic_auth", _cat("Authorization: Basic ", _b64_secret(16, "realisticbasic")), "cred.basic_auth"),
    ("bearer_lower", _cat("authorization: bearer ", _mixed_alnum(10, "realisticbearer")), "cred.bearer"),
    ("set_cookie", _cat("Set-Cookie: sessionid=", _hexrun(32, "realisticcookie"), "; Path=/"), "cred.cookie"),
    ("password_x", "password: x", "cred.password_assignment"),
    ("password_hunter2", "password: hunter2", "cred.password_assignment"),
    ("password_phrase", '"password": "correct horse battery staple"', "cred.password_assignment"),
    ("pgp_block", _cat("-----BEGIN ", "PGP PRIVATE KEY BLOCK", "-----"), "cred.private_key"),
    ("netrc_inline", _cat("machine api.example.com login bot password ", _mixed_alnum(10, "netrcinline")), "cred.netrc"),
    (
        "netrc_multiline",
        _cat("machine api.example.com\n  login bot\n  password ", _mixed_alnum(10, "netrcmulti")),
        "cred.netrc",
    ),
    ("npm_token", _cat("npm_", _rep("Q", 36)), "cred.package_token"),
    ("pypi_token", _cat("pypi-AgEI", _rep("Q", 50)), "cred.package_token"),
    ("x_api_key", _cat("x-api-key: ", _mixed_alnum(20, "xapikey")), "cred.assignment"),
    (
        "npm_registry_authtoken",
        _cat("//registry.npmjs.org/:_authToken=", _mixed_alnum(25, "npmregistry")),
        "cred.assignment",
    ),
    ("db_pwd_8", _cat("DB_PWD=", _mixed_alnum(8, "dbpwd")), "cred.assignment"),
    ("password_yourmom", "password=yourmom123", "cred.password_assignment"),
    ("api_key_examplekey", "api_key=examplekey987654", "cred.assignment"),
    ("secret_stay_here", "secret=stay_here", "cred.assignment"),
    ("token_redacted9x", "token=Redacted9x9x9x9x", "cred.assignment"),
    (
        "netrc_indented",
        _cat("  machine h login u password ", _mixed_alnum(8, "netrcindented")),
        "cred.netrc",
    ),
    ("x_bearer", _cat("x bearer ", _mixed_alnum(25, "xbearer")), "cred.bearer"),
]


@pytest.mark.parametrize("name,payload,rule_id", REALISTIC_REFUSALS, ids=[r[0] for r in REALISTIC_REFUSALS])
def test_realistic_payloads_refused(name, payload, rule_id):
    refusal = _refused(payload)
    assert rule_id in refusal.rule_ids, f"{name}: expected {rule_id} in {refusal.rule_ids}"

    refusal2 = _refused_in_candidate_description(payload)
    assert rule_id in refusal2.rule_ids, f"{name} (candidate description): expected {rule_id} in {refusal2.rule_ids}"


# ---------------------------------------------------------------------------
# test_false_positives_admitted
# ---------------------------------------------------------------------------

FALSE_POSITIVES = [
    ("desk_org", "desk-organization-toolkit"),
    ("risk_assessment", "risk-assessment-framework-tool"),
    ("scikit_learn", "scikit-learn"),
    ("git_sha40", _hexrun(40, "gitsha")),
    ("sha256_prose", _cat("the digest is ", _hexrun(64, "sha256prose"), " for this build")),
    ("token_budget", "token budget: 1500ms"),
    ("input_tokens_json", '"input_tokens": 18000000'),
    ("token_environ", 'token = os.environ.get("X")'),
    ("credentials_call", "credentials = get_credentials()"),
    ("bypass", "bypass: enabled_by_default"),
    ("passthrough", "passthrough: true"),
    ("sk_learn_slug", "sk-learn-based-classification-model"),
    ("password_required", "password: required"),
    ("password_dollar_var", "password: ${DB_PASSWORD}"),
    ("password_angle", "password = <your password>"),
    ("pwd_env", "PWD=/home/mk/projects/x"),
    ("declare_pwd", 'declare -x PWD="/home/mk"'),
    ("oldpwd", "OLDPWD=~/src"),
    ("nsswitch_passwd", "passwd: files systemd"),
    ("password_schema", '"password": {"type": "string"}'),
    ("password_redacted_brackets", "password: [REDACTED]"),
    ("password_template", '"password": "{{ vault_pw }}"'),
    ("password_stars", '"password": "***"'),
    ("password_newline_type", "password:\n  type: string"),
    ("token_subshell", "token=$(cat f)"),
    ("api_key_your", "api_key: YOUR_API_KEY"),
    ("token_your_token_here_angle", "token: <your-token-here>"),
    ("token_your_token_here", "token: your_token_here"),
    ("password_example", "password: example"),
    ("password_redacted_quoted", '"password": "REDACTED"'),
    ("api_key_paste_here", "api_key=PASTE_TOKEN_HERE"),
    ("bearer_dollar_var", "Authorization: Bearer ${ACCESS_TOKEN}"),
    ("bearer_your_token_angle", "Authorization: Bearer <your-token-here>"),
    ("bearer_your_api_key", "Authorization: Bearer YOUR_API_KEY"),
    ("prose_default_password", "By default password fields are hidden"),
    ("prose_machine_learning", "We tried machine learning password reset flows"),
]


@pytest.mark.parametrize("name,payload", FALSE_POSITIVES, ids=[f[0] for f in FALSE_POSITIVES])
def test_false_positives_admitted(name, payload):
    _admitted(payload)


def test_false_positives_skill_descriptions():
    skill_dirs = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
    assert len(skill_dirs) == 26
    descriptions = []
    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        assert text.startswith("---")
        _, frontmatter, _ = text.split("---", 2)
        description = None
        for line in frontmatter.splitlines():
            if line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
                break
        assert description, f"{skill_dir.name} has no description"
        descriptions.append(description)

    for description in descriptions:
        _admitted(description)


# ---------------------------------------------------------------------------
# test_high_entropy_rule
# ---------------------------------------------------------------------------


def test_high_entropy_rule():
    secret = _mixed_alnum(40, "he-context-secret")

    _refused(secret, point=Point.POST_TOOL_OUTPUT)
    _refused(secret, point=Point.PRE_COMPACT)

    _admitted(secret, point=Point.LAUNCH_PROFILE)
    _refused(secret, point=Point.LAUNCH_PROFILE, high_entropy=True)

    sha = _hexrun(40, "he-sha-at-every-point")
    for point in (Point.POST_TOOL_OUTPUT, Point.PRE_COMPACT, Point.LAUNCH_PROFILE, Point.LIBRARY):
        _admitted(sha, point=point)


def test_high_entropy_admitted_shapes_at_post_tool_output():
    deep_path = (
        "find results: /Users/mk/Projects/ClavainSelector/tests/structural/"
        "DeepNestedDirectoryNameExample/AnotherLongDirectoryNameHere/module_output.py"
    )
    _admitted(deep_path, point=Point.POST_TOOL_OUTPUT)

    slug = "-home-mk--bb-machines-autarch-getbb-app-thr-ay39nh2cpv"
    _admitted(_cat("project dir: ", slug), point=Point.POST_TOOL_OUTPUT)

    uuid_suffixed = "backup-550e8400-e29b-41d4-a716-446655440000.tar.gz"
    _admitted(uuid_suffixed, point=Point.POST_TOOL_OUTPUT)

    ssh_ed25519 = _cat(
        "ssh-ed25519 ", _b64_secret(68, "sshed25519"), " user@host"
    )
    _admitted(ssh_ed25519, point=Point.POST_TOOL_OUTPUT)

    ssh_rsa = _cat("ssh-rsa ", _b64_secret(200, "sshrsa"), " user@host")
    _admitted(ssh_rsa, point=Point.POST_TOOL_OUTPUT)

    data_uri = _cat("data:image/png;base64,", _b64_secret(80, "datauri"))
    _admitted(data_uri, point=Point.POST_TOOL_OUTPUT)

    gosum = _cat("example.com/pkg v1.2.3 h1:", _b64_secret(43, "gosum"), "=")
    _admitted(gosum, point=Point.POST_TOOL_OUTPUT)

    sri = _cat('integrity="sha512-', _b64_secret(88, "sri"), '"')
    _admitted(sri, point=Point.POST_TOOL_OUTPUT)

    dated_bead_path = "docs/2026-09-25-mk-42j9.7-decision-notes-v2.md"
    _admitted(dated_bead_path, point=Point.POST_TOOL_OUTPUT)

    json_escaped_listing = _cat(
        "docs/file1.py\\n", "docs/file2.py\\n", "docs/file3.py"
    )
    _admitted(json_escaped_listing, point=Point.POST_TOOL_OUTPUT)


def test_high_entropy_single_slash_secret_refused():
    secret = _b64_secret_with_slash(40, "single-slash", pos=20)
    _refused(_cat("token found: ", secret), point=Point.POST_TOOL_OUTPUT)


def test_high_entropy_json_secret_refused():
    secret = _mixed_alnum(40, "json-secret")
    payload = _cat('{"k": "', secret, '"}')
    _refused(payload, point=Point.POST_TOOL_OUTPUT)


def test_high_entropy_revision5_slash_secret_fixtures():
    secret_a = _b64_secret_with_slash(40, "sentence-secret-a", pos=20)
    secret_b = _b64_secret_with_slash(40, "dotted-key-secret-b", pos=20)

    _refused(_cat("the value is ", secret_a, "."), point=Point.POST_TOOL_OUTPUT)
    _refused(_cat("config line: app.hmac=", secret_b), point=Point.POST_TOOL_OUTPUT)
    _refused(_cat("the value is ", secret_a, "..."), point=Point.POST_TOOL_OUTPUT)


# ---------------------------------------------------------------------------
# test_candidate_ids_scanned
# ---------------------------------------------------------------------------


def test_candidate_ids_scanned():
    aws_shaped = _cat("AKI", "A", _rep("B", 16))
    req = make_request(candidates=(make_candidate(id=aws_shaped, description="ordinary"),))
    result = egress.admit(req)
    assert isinstance(result, egress.Refusal)
    assert result.rule_ids == ("cred.aws_key",)
    assert aws_shaped not in repr(result)


# ---------------------------------------------------------------------------
# test_clean_request_admitted
# ---------------------------------------------------------------------------


def test_clean_request_admitted():
    req = make_request(
        task="Decide the next step for the selector layer.",
        context="No secrets here, just ordinary planning context.",
        candidates=(
            make_candidate(id="brainstorming", description="Brainstorm the next step."),
            make_candidate(id="plan-review", description="Review the current plan for gaps."),
        ),
    )
    result = egress.admit(req)
    assert isinstance(result, egress.AdmittedRequest)
    assert result.sha256 == hashlib.sha256(result.body).hexdigest()
    assert egress.verify(result) is True


# ---------------------------------------------------------------------------
# test_loaded_key_literal
# ---------------------------------------------------------------------------


def test_loaded_key_literal():
    key = _cat("loaded-key-literal-", _mixed_alnum(16, "loadedkey"))
    req = make_request(context=_cat("some context mentioning ", key, " inline"))
    result = egress.admit(req, key_literal=key)
    assert isinstance(result, egress.Refusal)
    assert result.rule_ids == ("cred.loaded_key",)

    clean_req = make_request(context="context with nothing sensitive")
    clean_result = egress.admit(clean_req, key_literal=key)
    assert isinstance(clean_result, egress.AdmittedRequest)


# ---------------------------------------------------------------------------
# test_denylisted_and_outside_sources
# ---------------------------------------------------------------------------


def test_denylisted_and_outside_sources(tmp_path, monkeypatch):
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    project = fake_home / "project"
    project.mkdir()

    ssh_key = fake_home / ".ssh" / "id_ed25519"
    ssh_key.parent.mkdir(parents=True)
    ssh_key.write_text("fake")

    secrets_env = fake_home / ".config" / "x" / "secrets.env"
    secrets_env.parent.mkdir(parents=True)
    secrets_env.write_text("fake")

    dotenv = project / ".env"
    dotenv.write_text("fake")

    outside = tmp_path / "outside" / "file.txt"
    outside.parent.mkdir(parents=True)
    outside.write_text("fake")

    for source in (ssh_key, secrets_env, dotenv):
        req = make_request(sources=(source,), project_root=project)
        result = egress.admit(req)
        assert isinstance(result, egress.Refusal)
        assert "src.denylisted_path" in result.rule_ids, f"{source}: {result.rule_ids}"

    req = make_request(sources=(outside,), project_root=project)
    result = egress.admit(req)
    assert isinstance(result, egress.Refusal)
    assert "src.outside_project" in result.rule_ids


# ---------------------------------------------------------------------------
# test_owner_allowlist
# ---------------------------------------------------------------------------


def _init_repo_with_origin(path: Path, origin: str | None) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    if origin is not None:
        subprocess.run(["git", "remote", "add", "origin", origin], cwd=path, check=True)


def test_owner_allowlist(tmp_path):
    mistakeknot_repo = tmp_path / "mk-repo"
    _init_repo_with_origin(mistakeknot_repo, "git@github.com:mistakeknot/x.git")
    req = make_request(project_root=mistakeknot_repo)
    assert isinstance(egress.admit(req), egress.AdmittedRequest)

    gensysven_repo = tmp_path / "gv-repo"
    _init_repo_with_origin(gensysven_repo, "https://github.com/gensysven/y")
    req = make_request(project_root=gensysven_repo)
    assert isinstance(egress.admit(req), egress.AdmittedRequest)

    someoneelse_repo = tmp_path / "other-repo"
    _init_repo_with_origin(someoneelse_repo, "git@github.com:someoneelse/z.git")
    req = make_request(project_root=someoneelse_repo)
    result = egress.admit(req)
    assert isinstance(result, egress.Refusal)
    assert result.rule_ids == ("proj.unowned",)

    no_origin_repo = tmp_path / "no-origin-repo"
    _init_repo_with_origin(no_origin_repo, None)
    req = make_request(project_root=no_origin_repo)
    result = egress.admit(req)
    assert isinstance(result, egress.Refusal)
    assert result.rule_ids == ("proj.unowned",)

    (mistakeknot_repo / "README.md").write_text("x")
    subprocess.run(["git", "add", "README.md"], cwd=mistakeknot_repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-q", "-m", "init"],
        cwd=mistakeknot_repo,
        check=True,
    )

    worktree_dir = tmp_path / "mk-repo-worktree"
    subprocess.run(
        ["git", "worktree", "add", "-q", "--detach", str(worktree_dir)],
        cwd=mistakeknot_repo,
        check=True,
    )
    req = make_request(project_root=worktree_dir)
    assert isinstance(egress.admit(req), egress.AdmittedRequest)


# ---------------------------------------------------------------------------
# test_owner_lookup_no_subprocess
# ---------------------------------------------------------------------------


def test_owner_lookup_no_subprocess(tmp_path, monkeypatch):
    repo = tmp_path / "no-subprocess-repo"
    _init_repo_with_origin(repo, "git@github.com:mistakeknot/no-subprocess.git")

    state_dir = tmp_path / "state"
    monkeypatch.setenv("CLAVAIN_STATE_DIR", str(state_dir))

    def _raise(*args, **kwargs):
        raise AssertionError("project_owner must never invoke a subprocess")

    monkeypatch.setattr(subprocess, "run", _raise)
    monkeypatch.setattr(subprocess, "Popen", _raise)

    owner = egress.project_owner(repo)
    assert owner == "mistakeknot"

    cache_path = state_dir / "selector" / "owner-cache.json"
    assert cache_path.is_file()

    import time

    start = time.monotonic()
    owner_again = egress.project_owner(repo)
    elapsed = time.monotonic() - start
    assert owner_again == "mistakeknot"
    assert elapsed < 0.2

    config_path = repo / ".git" / "config"
    text = config_path.read_text(encoding="utf-8")
    text = text.replace("mistakeknot/no-subprocess", "mistakeknot/no-subprocess-renamed")
    config_path.write_text(text, encoding="utf-8")

    owner_after_edit = egress.project_owner(repo)
    assert owner_after_edit == "mistakeknot"

    unreadable_repo = tmp_path / "unreadable-repo"
    unreadable_repo.mkdir()
    (unreadable_repo / ".git").mkdir()
    owner_missing_config = egress.project_owner(unreadable_repo)
    assert owner_missing_config is None


# ---------------------------------------------------------------------------
# test_over_limit
# ---------------------------------------------------------------------------


def test_over_limit():
    req = make_request(context="y" * 90_001)
    result = egress.admit(req)
    assert isinstance(result, egress.Refusal)
    assert result.rule_ids == ("size.over_limit",)


# ---------------------------------------------------------------------------
# test_admitted_is_immutable
# ---------------------------------------------------------------------------


def test_admitted_is_immutable():
    req = make_request(task="clean task, nothing sensitive")
    result = egress.admit(req)
    assert isinstance(result, egress.AdmittedRequest)

    with pytest.raises(Exception):
        result.body = b"tampered"

    other_req = make_request(task="a different clean task")
    other_result = egress.admit(other_req)
    assert isinstance(other_result, egress.AdmittedRequest)

    swapped = egress.AdmittedRequest(body=other_result.body, sha256=result.sha256, tag=result.tag)
    assert egress.verify(swapped) is False


# ---------------------------------------------------------------------------
# test_forged_admission_rejected
# ---------------------------------------------------------------------------


def test_forged_admission_rejected():
    body = b"forged body, never went through admit()"
    sha = hashlib.sha256(body).hexdigest()
    forged = egress.AdmittedRequest(body=body, sha256=sha, tag=b"\0" * 32)
    assert egress.verify(forged) is False

    req_a = make_request(task="task A, ordinary")
    req_b = make_request(task="task B, also ordinary")
    admitted_a = egress.admit(req_a)
    admitted_b = egress.admit(req_b)
    assert isinstance(admitted_a, egress.AdmittedRequest)
    assert isinstance(admitted_b, egress.AdmittedRequest)

    copied_tag = egress.AdmittedRequest(body=admitted_b.body, sha256=admitted_b.sha256, tag=admitted_a.tag)
    assert egress.verify(copied_tag) is False
