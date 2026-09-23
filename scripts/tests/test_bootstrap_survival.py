"""Textual survival checks for the mandatory bootstrap contract.

These guard source and rendering regressions; native session canaries still decide
whether an agent loads and follows the contract.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOSTS = ("codex", "claude", "hermes", "gemini", "kimi", "opencode", "cursor", "vscode")


def normalized(body):
    return " ".join(body.split()).casefold()


# Exact obligation fragments, grouped by the source that must remain immediately
# available. Avoid wildcard matches that can span unrelated or inverted clauses.
CLAUSES = {
    "config/agent-instructions.md": {
        "selected_router_and_canon": "read the selected `clavain:using-clavain` router and selected `docs/canon/reasoning-routing.md`",
        "skill_bodies": "read applicable installed skill bodies before use; all unique specialists remain eligible",
        "small_edits": "One-line behavior edits and plan execution are substantive",
        "oodarcs": "Observe → Orient → Decide → Act → Reflect → Compound → Synthesize",
        "routine_context": "settled routine work records `reasons: []`",
        "frontier_new_capabilities": "Substantial new game, agent, AI/ML, graph, or product-strategy capabilities need frontier planning",
        "role_resolution": "ic --json route dispatch --policy={{POLICY_PATH}} --role=<role> --context-file=<json>",
        "governed_execution": "scripts/dispatch.sh --role <role>` with the same `CLAVAIN_ROUTING_POLICY` and `CLAVAIN_DECISION_CONTEXT",
        "unsupported_role": "Unsupported `--role` resolution remains an open gate; legacy `--type` or `--tier` output cannot satisfy it",
        "overlay_scope": "`CLAVAIN_POLICY_PROFILE=ci-campaign-pilot` requires `scope: mk-ag2s` and applies only there",
        "independent_review": "Foundational or especially consequential plans need an independent other-frontier reviewer; pass `--producer-identity` from the actual producer receipt",
        "no_downgrade": "Never self-review, downgrade frontier work, or evade blocked review",
        "escalation": "Two demonstrated capability failures request escalation; a disproven premise escalates immediately",
        "operational_failures": "Authentication, quota, permissions, timeout and infrastructure failures are operational",
        "attribution": "policy hash, classifications, exclusions, profile, actual model/effort, retries, usage, outcomes and defects in attribution",
        "calibration": "Calibration cannot relax frontier requirements, reviewer independence, quality floors, or authority gates",
        "restricted_dispatch": "Restrictions on dispatch do not remove authorized local guidance reads or decision recording",
        "publication": "A push does not authorize publication",
        "no_install": "Missing companions do not authorize installation. No broad installer or automatic refresh",
        "blank_identity": "blank identity or policy hash makes conformance unknown and acceptance false",
        "parent_model": "Configuration does not change a running parent's model",
        "fresh_evidence": "Never substitute cached green results for fresh evidence",
        "handoff": "Handoff states decisions, constraints, verification, escalation",
    },
    "skills/using-clavain/SKILL.md": {
        "first_router": "Load this router once at the first substantive task",
        "synthesis": "State material changes when synthesizing",
        "selected_canon": "Read the selected `docs/canon/reasoning-routing.md` before substantive planning or execution",
        "all_specialists": "Every installed unique capability remains eligible beyond this table",
        "codex_body": "In Codex, read the selected skill's full `SKILL.md`",
        "claude_skill": "In Claude Code, invoke the corresponding Skill tool",
        "debug_dependency": "Fixing a bug requires `intertest:systematic-debugging` for reproduction and diagnosis, then `intertest:test-driven-development`",
        "plan_dependency": "Executing an existing plan requires `clavain:executing-plans`",
        "interflux": "Interflux deeper-review engine",
        "authorized_release": "Prepare an authorized release",
        "on_demand": "Read [routing-tables.md](references/routing-tables.md) for specialty and host detail when needed",
        "tracker": "do not create a second task system. Outside a project use lightweight in-session state",
        "writing": "Apply its inline explanatory-writing guidance",
        "no_doc_audit": "without forcing a repository-documentation audit",
    },
    "docs/canon/reasoning-routing.md": {
        "required_read": "Required selected-source read for substantive work",
        "routine_context": "Settled routine work records `reasons: []` with rationale. An empty reasons array does not waive recording or existing gates",
        "reason_success": "`unresolved-success-criteria` | Outcomes need playtests or user evidence",
        "reason_foundational": "`foundational-invariants` | Authority or identity/consistency semantics change",
        "reason_broad": "`broad-consequences` | A shared protocol affects many consumers",
        "reason_verification": "`difficult-verification` | Experiments or production canaries decide correctness",
        "reason_capability": "`capability-failure` | Execution or review demonstrates an unsolved capability gap",
        "domain": "Domain names alone do not elevate",
        "frontier_planning": "Substantial new game, agent, AI/ML, graph, or product-strategy capabilities require frontier planning",
        "resolution": "ic --json route dispatch --policy=<selected-policy> --role=planning --context-file=<decision.json>",
        "packaged_dispatch": "Execute through packaged `scripts/dispatch.sh --role <role>`",
        "unsupported_role": "Unsupported `--role` stays open; `--type` or `--tier` cannot satisfy it",
        "source_order": "Source order: `--policy`, `CLAVAIN_ROUTING_POLICY`, `CLAVAIN_ROOT`, selected Claude plugin root, managed Clavain skill link",
        "packaged_policy": "The dispatch wrapper selects its packaged policy unless explicitly overridden",
        "cache_hazard": "Never select the newest cache directory by accident",
        "frontier_review": "Foundational or especially consequential plans require independent other-frontier plan review",
        "review_identity": "Aliases and dated/provider-decorated identities cannot evade reviewer separation",
        "no_frontier_downgrade": "No fallback may review its producer, route frontier-required work to a non-frontier seat",
        "campaign_scope": "`ci-campaign-pilot` requires `scope: mk-ag2s`",
        "operational": "Quota, authentication, permission, timeout, and infrastructure failures are operational, not capability strikes",
        "capacity_roles": "`main-integrator` and `release-authority` have no capacity substitute",
        "headroom_scope": "planning, plan-review, validation, escalation and cross-lab-review receive no headroom input",
        "escalation": "Two demonstrated capability, verdict, or criteria failures request escalation; a disproven premise escalates immediately",
        "handoff": "Handoff carries decisions, constraints, verification, and escalation conditions",
        "empirical": "Retain relevant playtests, experiments, user evidence, and production canaries",
        "authority": "User authority, sandboxing, independent review, fresh verification, release and publication approval remain binding",
        "no_broad_refresh": "narrow synchronization only: no broad installer or automatic refresh",
        "attribution": "retries, usage, outcomes and defects in existing attribution evidence",
        "unknown_identity": "Missing or blank identity/hash makes conformance unknown and acceptance false",
        "calibration_floor": "Calibration cannot relax frontier requirements, reviewer independence, quality floors, or authority gates",
    },
}


class BootstrapSurvivalTests(unittest.TestCase):
    def test_enumerated_clauses_survive_at_required_sources(self):
        for relative, clauses in CLAUSES.items():
            body = normalized((ROOT / relative).read_text())
            for name, sentence in clauses.items():
                with self.subTest(source=relative, clause=name):
                    self.assertIn(normalized(sentence), body)

    def test_all_eight_rendered_hosts_keep_shared_binding_clauses(self):
        spec = importlib.util.spec_from_file_location("instruction_renderer", ROOT / "scripts/sync-agent-instructions.py")
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        for host in HOSTS:
            body, _ = renderer.render(ROOT, host)
            body = normalized(body)
            for name, sentence in CLAUSES["config/agent-instructions.md"].items():
                if name == "role_resolution":
                    continue  # {{POLICY_PATH}} is replaced by the selected policy.
                with self.subTest(host=host, clause=name):
                    self.assertIn(normalized(sentence), body)
            self.assertIn("--role=<role> --context-file=<json>", body)
            self.assertNotIn("{{POLICY_PATH}}", body)

    def test_entry_points_and_optional_reference(self):
        template = (ROOT / "config/agent-instructions.md").read_text()
        self.assertEqual(template.count("<!-- BEGIN CLAVAIN CODEX TOOL MAP -->"), 1)
        self.assertEqual(template.count("<!-- END CLAVAIN CODEX TOOL MAP -->"), 1)
        for placeholder in ("{{INSTALLATION_RECEIPT}}", "{{HOST_ADAPTER}}", "{{POLICY_PATH}}"):
            self.assertIn(placeholder, template)
        router = (ROOT / "skills/using-clavain/SKILL.md").read_text()
        self.assertTrue(router.startswith("---\nname: using-clavain\n"))
        canon = (ROOT / "docs/canon/reasoning-routing.md").read_text()
        operations = (ROOT / "docs/canon/reasoning-routing-operations.md").read_text()
        self.assertIn("reasoning-routing-operations.md", canon)
        for heading in ("## Capacity failure and fallback", "## Host delivery and evidence", "## Calibration and rollout"):
            self.assertIn(heading, operations)

    def test_probe_requires_current_render_instead_of_frozen_contract(self):
        probe = (ROOT / "docs/canon/reasoning-routing-probe.md").read_text()
        self.assertIn("sync-agent-instructions.py", probe)
        self.assertIn("fresh", normalized(probe))
        self.assertNotIn("package: 0.6.314", probe)


if __name__ == "__main__":
    unittest.main()
