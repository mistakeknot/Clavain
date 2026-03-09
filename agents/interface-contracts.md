# Interface Contract Convention

Agents can publish interface contracts during sprint execution to enable parallel work against shared interfaces. This is Pattern 1 from the WCM (When Claudes Meet) analysis.

## Contract Artifact Schema

Contract files are JSON stored as run_artifacts with `type=contract`:

```json
{
  "name": "ast-interface",
  "version": 1,
  "owner": "agent-session-id",
  "patterns": ["src/ast/*.py", "src/ast/types.ts"],
  "schema": {
    "Node": { "type": "string", "line": "number", "children": "Node[]" },
    "Expression": { "extends": "Node", "value": "any" }
  },
  "dependencies": ["parser-output-contract"],
  "description": "AST node types for parser/interpreter interface"
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Stable identifier for this contract (used in dependencies) |
| `version` | integer | Monotonically increasing; bump on revision |
| `owner` | string | Session ID or agent name of the publisher |
| `patterns` | string[] | Glob patterns for files this contract covers |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema` | object | Typed interface declaration (language-agnostic) |
| `dependencies` | string[] | Names of contracts this one depends on |
| `description` | string | Human-readable purpose |

## Publishing a Contract

From lib-sprint.sh:

```bash
# Write the contract file
cat > /tmp/my-contract.json <<'EOF'
{
  "name": "api-surface",
  "version": 1,
  "owner": "session-abc",
  "patterns": ["src/api/*.go"],
  "description": "REST API handler signatures"
}
EOF

# Publish it (records artifact + reserves write_set)
sprint_publish_contract "$CLAVAIN_BEAD_ID" "/tmp/my-contract.json"
```

`sprint_publish_contract()` does two things:
1. Records the contract file as a `type=contract` run_artifact via `sprint_set_artifact()`
2. Creates non-exclusive `write_set` coordination locks for each pattern in the contract

## Contract Revision Protocol

When revising a published contract:

1. **Bump the version** in the contract JSON
2. **Re-publish** with `sprint_publish_contract()` — the new artifact supersedes the old one
3. **Notify dependents** via Intermute (if other agents are online):
   ```bash
   # Agents building against this contract should re-read it
   curl -sf -X POST "${INTERMUTE_URL}/api/messages" \
     -H 'Content-Type: application/json' \
     -d '{
       "id": "contract-revised:<name>:v<version>",
       "project": "<project>",
       "from": "<owner>",
       "to": ["<dependent-agents>"],
       "subject": "[contract-revised] <name> v<version>",
       "topic": "contract-revised",
       "body": "Contract <name> revised to v<version>. Re-read and adjust."
     }'
   ```

### TOCTOU Safety

The `write_set` coordination lock prevents concurrent modification of files covered by the contract. Dependents can `ic coordination check` before building to verify no conflicting write_set exists. The non-exclusive lock means multiple agents can read the contract, but exclusive reservations on the same patterns will surface as conflicts.

## Querying Contracts

```bash
# List all contract artifacts for a run
ic run artifact list <run_id> --phase=<phase> | jq 'select(.Type == "contract")'

# Check if patterns conflict with existing contracts
ic coordination list --scope=<project> --type=write_set --active
```

## Relationship to Other Primitives

- **coordination_locks (write_set)**: The enforcement mechanism — contracts declare patterns, write_sets protect them
- **run_artifacts**: The storage mechanism — contracts are versioned artifacts attached to sprint phases
- **Intermute messages**: The notification mechanism — contract revisions trigger messages to dependents
- **Intent system**: Governs policy mutations (sprint.create, gate.enforce); contracts govern data interfaces
