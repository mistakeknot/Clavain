-- Mock interstat agent_runs for fleet enrichment tests
-- Schema matches interverse/interstat/scripts/init-db.sh (version 2)

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    invocation_id TEXT,
    subagent_type TEXT,
    description TEXT,
    wall_clock_ms INTEGER,
    result_length INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_creation_tokens INTEGER,
    total_tokens INTEGER,
    model TEXT,
    parsed_at TEXT,
    bead_id TEXT DEFAULT '',
    phase TEXT DEFAULT ''
);

-- test-reviewer-a: 5 runs on sonnet (sorted total_tokens: 30000, 35000, 38000, 40000, 50000)
-- mean=38600, p50=38000 (index 2), p90=50000 (index 4)
INSERT INTO agent_runs (timestamp, session_id, agent_name, subagent_type, input_tokens, output_tokens, total_tokens, model)
VALUES
  ('2026-02-01T10:00:00Z', 's1', 'test-reviewer-a', 'test-plugin:review:test-reviewer-a', 10000, 20000, 30000, 'claude-sonnet-4-6'),
  ('2026-02-02T10:00:00Z', 's2', 'test-reviewer-a', 'test-plugin:review:test-reviewer-a', 12000, 23000, 35000, 'claude-sonnet-4-6'),
  ('2026-02-03T10:00:00Z', 's3', 'test-reviewer-a', 'test-plugin:review:test-reviewer-a', 13000, 25000, 38000, 'claude-sonnet-4-6'),
  ('2026-02-04T10:00:00Z', 's4', 'test-reviewer-a', 'test-plugin:review:test-reviewer-a', 15000, 25000, 40000, 'claude-sonnet-4-6'),
  ('2026-02-05T10:00:00Z', 's5', 'test-reviewer-a', 'test-plugin:review:test-reviewer-a', 20000, 30000, 50000, 'claude-sonnet-4-6');

-- test-reviewer-a: 3 runs on opus (sorted: 60000, 70000, 70000)
-- mean=66667, p50=70000 (index 1), p90=70000 (index 2)
INSERT INTO agent_runs (timestamp, session_id, agent_name, subagent_type, input_tokens, output_tokens, total_tokens, model)
VALUES
  ('2026-02-01T11:00:00Z', 's1', 'test-reviewer-a', 'test-plugin:review:test-reviewer-a', 20000, 40000, 60000, 'claude-opus-4-6'),
  ('2026-02-02T11:00:00Z', 's2', 'test-reviewer-a', 'test-plugin:review:test-reviewer-a', 25000, 45000, 70000, 'claude-opus-4-6'),
  ('2026-02-03T11:00:00Z', 's3', 'test-reviewer-a', 'test-plugin:review:test-reviewer-a', 22000, 48000, 70000, 'claude-opus-4-6');

-- test-reviewer-b: 2 runs on sonnet (< 3, should get preliminary: true)
-- mean=22500
INSERT INTO agent_runs (timestamp, session_id, agent_name, subagent_type, input_tokens, output_tokens, total_tokens, model)
VALUES
  ('2026-02-01T12:00:00Z', 's1', 'test-reviewer-b', 'test-plugin:review:test-reviewer-b', 8000, 12000, 20000, 'claude-sonnet-4-6'),
  ('2026-02-02T12:00:00Z', 's2', 'test-reviewer-b', 'test-plugin:review:test-reviewer-b', 10000, 15000, 25000, 'claude-sonnet-4-6');

-- test-researcher: 4 runs on haiku (sorted: 10000, 12000, 14000, 16000)
-- mean=13000, p50=14000 (index 2), p90=16000 (index 3)
INSERT INTO agent_runs (timestamp, session_id, agent_name, subagent_type, input_tokens, output_tokens, total_tokens, model)
VALUES
  ('2026-02-01T13:00:00Z', 's1', 'test-researcher', 'other-plugin:research:test-researcher', 5000, 5000, 10000, 'claude-haiku-4-5'),
  ('2026-02-02T13:00:00Z', 's2', 'test-researcher', 'other-plugin:research:test-researcher', 6000, 6000, 12000, 'claude-haiku-4-5'),
  ('2026-02-03T13:00:00Z', 's3', 'test-researcher', 'other-plugin:research:test-researcher', 7000, 7000, 14000, 'claude-haiku-4-5'),
  ('2026-02-04T13:00:00Z', 's4', 'test-researcher', 'other-plugin:research:test-researcher', 8000, 8000, 16000, 'claude-haiku-4-5');

-- NOTE: Post-enrichment runs for delta tests should be inserted by
-- individual tests (not this fixture) so enrichment baseline is clean.
-- Example: INSERT INTO agent_runs (...) VALUES ('2026-03-01T10:00:00Z', ...)
