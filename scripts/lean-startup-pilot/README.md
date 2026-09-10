# Separate startup correctness cohort

`prepare.py` creates a new twelve-subject manifest from full committed source
SHAs and an existing authoritative Intercore database. It preserves the stopped
comparison. The six scenarios use Astra high in Codex on the Mac and Fable high
in Claude on zklw, with the existing isolated profiles and specialist catalog.

Run subjects in manifest order. Use `runner.py case --base BASE --number N` for
Codex. For Claude, first use `transport.py bootstrap --base BASE --remote-base
REMOTE`, then `transport.py case --base BASE --remote-base REMOTE --number N`.
Both transport operations run on the Mac. Candidate source reaches zklw through
Git; the frozen catalog is a captured test fixture. Remote preparation observes
executable and configuration hashes without launching a subject. The Mac records
prospective enrollment in its authoritative database, then returns that receipt
before the remote worker can execute. Native evidence bytes return with hashes
and an explicit path map; transcript identities are never rewritten.

Call `delivery.accept` only with an independent reviewer's native binding and
verdict records. Canonical `task-delivery.py` verifies reviewer native identity
before acceptance can admit the next subject. A failed subject remains immutable;
test corrections in another cohort. Completion of compaction requires the native
boundary, not a command acknowledgment. This harness does not publish or install
packages and makes no efficiency claim.

Run `python3 -m pytest -q scripts/lean-startup-pilot/test_support.py` from Clavain
for helper tests. The enrollment test creates only a temporary test database;
production cohort preparation requires an explicitly supplied existing database.
