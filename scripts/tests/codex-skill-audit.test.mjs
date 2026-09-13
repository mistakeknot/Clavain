import assert from 'node:assert/strict';
import { test } from 'node:test';
import { querySkills, summarize } from '../codex-skill-audit.mjs';
import { mkdtempSync, readFileSync, realpathSync, rmSync, existsSync, symlinkSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const skill = (name, path, enabled = true) => ({ name, path, enabled, description: 'Use for fixtures.' });

test('disabled skills do not consume enabled catalog accounting', () => {
  const report = summarize({ cwd: '/work', skills: [skill('a', '/a'), skill('b', '/b', false)], errors: [] });
  assert.equal(report.enabled_count, 1);
  assert.equal(report.unique_enabled_names, 1);
  assert.equal(report.disabled_count, 1);
  assert.equal(report.metadata_characters, 'aUse for fixtures./a'.length);
});

test('duplicates are exact names, not overlapping descriptions or leaf names', () => {
  const report = summarize({ cwd: '/work', skills: [skill('a', '/one'), skill('a', '/two'), skill('other:a', '/three')], errors: [] });
  assert.deepEqual(report.duplicate_names, [{ name: 'a', paths: ['/one', '/two'] }]);
  assert.equal(report.unique_enabled_names, 2);
});

test('preserves loader errors rather than presenting an incomplete inventory as healthy', () => {
  const errors = [{ path: '/bad/SKILL.md', message: 'bad frontmatter' }];
  const report = summarize({ cwd: '/work', skills: [], errors });
  assert.deepEqual(report.errors, errors);
  assert.equal(report.enabled_count, 0);
});

test('measures Unicode characters, and groups namespace totals without dropping standalone skills', () => {
  const report = summarize({ cwd: '/work', skills: [skill('clavain:a', '/a'), { ...skill('solo', '/s'), description: '🦉' }], errors: [] });
  assert.equal(report.metadata_characters, [...'clavain:aUse for fixtures./asolo🦉/s'].length);
  assert.deepEqual(report.groups.map(x => x.namespace).sort(), ['clavain', '(standalone)'].sort());
  assert.equal(report.groups.reduce((n, x) => n + x.metadata_characters, 0), report.metadata_characters);
});

// A real stdio process exercises framing, protocol order and OS cleanup. No
// Codex auth, network, user config or production app-server is used here.
const fixture = String.raw`
const fs = require('node:fs');
fs.writeFileSync(process.env.AUDIT_PID_FILE, String(process.pid));
process.on('SIGTERM', () => {});
const send = obj => process.stdout.write(JSON.stringify(obj) + '\n');
const mode = process.env.AUDIT_CASE;
require('node:readline').createInterface({input:process.stdin}).on('line', line => {
 const m = JSON.parse(line);
 if (mode === 'exit') { process.stderr.write('fixture startup diagnostic\n'); process.exit(7); }
 if (mode === 'timeout') return;
 if (mode === 'json') { process.stdout.write('invalid\n'); return; }
 if (mode === 'huge') { process.stdout.write('x'.repeat(3000)); return; }
 if (mode === 'error') { send({id:m.id, error:{code:-1, message:'denied'}}); return; }
 if (m.id === 1) {
  if (mode === 'request') send({id:1,method:'server/request',params:{}});
  if (mode === 'bad-init') { send({id:1}); return; }
  send({method:'notice',params:{ready:true}});
  const text = JSON.stringify({id:1,result:{serverInfo:{name:'fixture'}}})+'\n';
  process.stdout.write(text.slice(0,5)); setTimeout(()=>process.stdout.write(text.slice(5)), 5);
 } else if (m.id === 2) {
  if (mode === 'bad-data') { send({id:2,result:{data:{}}}); return; }
  const entry = {cwd:process.env.AUDIT_CWD,skills:[{name:'ok',path:'/skill',enabled:true,description:'fixture'}],errors:[]};
  if (mode === 'bad-skill') entry.skills[0].description = null;
  if (mode === 'wrong-cwd') entry.cwd = '/wrong';
  if (mode === 'duplicate-cwd') { send({id:2,result:{data:[entry,entry]}}); return; }
  send({id:2,result:{data:[entry]}});
 }
});
setInterval(()=>{}, 1000);
`;

for (const mode of ['ok', 'request', 'exit', 'timeout', 'json', 'huge', 'error', 'bad-init', 'bad-data', 'bad-skill', 'wrong-cwd', 'duplicate-cwd']) {
  test(`stdio ${mode}: validates response and reaps process before settling`, async () => {
    const dir = mkdtempSync(join(tmpdir(), 'skill-audit-test-'));
    const pidFile = join(dir, 'pid');
    try {
      const result = querySkills('/work', {
        command: process.execPath, args: ['-e', fixture],
        env: {...process.env, AUDIT_PID_FILE:pidFile, AUDIT_CASE:mode, AUDIT_CWD:'/work'},
        timeoutMs:500, killGraceMs:30, maxResponseBytes:2000,
      });
      if (['ok', 'request'].includes(mode)) assert.equal((await result).skills[0].name, 'ok');
      else if (mode === 'exit') await assert.rejects(result, /fixture startup diagnostic/);
      else await assert.rejects(result, /exited|timed out|JSON|response|denied|protocol/i);
      assert.ok(existsSync(pidFile), 'fixture process was actually started');
      const pid = Number(readFileSync(pidFile, 'utf8'));
      assert.throws(() => process.kill(pid, 0), {code:'ESRCH'}, 'child must be gone when query settles');
    } finally { rmSync(dir, {recursive:true, force:true}); }
  });
}

test('missing executable rejects promptly', async () => {
  await assert.rejects(querySkills('/work', {command:'/nonexistent/skill-audit-fixture'}), /ENOENT/);
});

test('symlink entry point runs the CLI and a canonicalized cwd matches', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'skill-audit-links-'));
  try {
    const script = join(dir, 'audit.mjs');
    symlinkSync(fileURLToPath(new URL('../codex-skill-audit.mjs', import.meta.url)), script);
    assert.match(execFileSync(process.execPath, [script, '--help'], {encoding:'utf8'}), /Usage:/);
    const alias = join(dir, 'alias');
    symlinkSync(dir, alias);
    const entry = await querySkills(alias, {
      command:process.execPath, args:['-e', fixture],
      env:{...process.env, AUDIT_PID_FILE:join(dir,'pid'), AUDIT_CASE:'ok', AUDIT_CWD:realpathSync(dir)},
      timeoutMs:500, killGraceMs:30,
    });
    assert.equal(entry.cwd, realpathSync(dir));
  } finally { rmSync(dir, {recursive:true, force:true}); }
});
