#!/usr/bin/env node
// Read-only Codex discovery audit. No model turn, config write, or plugin install.
import { spawn } from 'node:child_process';
import { realpathSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const characters = value => [...value].length;
const canonicalPath = value => {
  try { return realpathSync(value); }
  catch (error) { if (error.code === 'ENOENT') return resolve(value); throw error; }
};

export function summarize({ cwd, skills, errors }) {
  const enabled = skills.filter(skill => skill.enabled);
  const names = new Map();
  const groups = new Map();
  const entries = enabled.map(skill => {
    const { name, path, description } = skill;
    const count = characters(name + description + path);
    const namespace = name.includes(':') ? name.split(':')[0] : '(standalone)';
    const group = groups.get(namespace) ?? { namespace, count: 0, metadata_characters: 0 };
    group.count++;
    group.metadata_characters += count;
    groups.set(namespace, group);
    names.set(name, [...(names.get(name) ?? []), path]);
    return { name, path, description_characters: characters(description), metadata_characters: count };
  });
  return {
    cwd,
    enabled_count: enabled.length,
    disabled_count: skills.length - enabled.length,
    unique_enabled_names: names.size,
    metadata_characters: entries.reduce((sum, entry) => sum + entry.metadata_characters, 0),
    measurement: 'Unicode characters in enabled names + full descriptions + paths; not rendered prompt tokens. Explicit-only skills may still appear in skills/list, and a running host may add plugin skills after MCP startup.',
    duplicate_names: [...names].filter(([, paths]) => paths.length > 1).map(([name, paths]) => ({ name, paths })),
    groups: [...groups.values()].sort((a, b) => b.metadata_characters - a.metadata_characters),
    entries: entries.sort((a, b) => b.metadata_characters - a.metadata_characters),
    errors,
  };
}

export function querySkills(cwd, {
  command = 'codex', args = ['app-server', '--stdio'], env = process.env,
  timeoutMs = 30000, killGraceMs = 1000, maxResponseBytes = 8 * 1024 * 1024,
} = {}) {
  return new Promise((resolveResult, reject) => {
    const child = spawn(command, args, { env, stdio: ['pipe', 'pipe', 'pipe'], detached: process.platform !== 'win32' });
    let buffer = '';
    let stderr = Buffer.alloc(0);
    let bytes = 0;
    let finishing = false;
    let initialized = false;
    let outcome;
    let failure;
    let forceKill;
    const kill = signal => {
      if (!child.pid) return;
      try {
        if (process.platform === 'win32') child.kill(signal);
        else process.kill(-child.pid, signal);
      } catch (error) { if (error.code !== 'ESRCH') failure ??= error; }
    };
    const finish = (error, result) => {
      if (finishing) return;
      finishing = true;
      failure = error;
      outcome = result;
      clearTimeout(timer);
      child.stdin.end();
      kill('SIGTERM');
      forceKill = setTimeout(() => kill('SIGKILL'), killGraceMs);
    };
    const timer = setTimeout(() => finish(new Error(`Codex skills/list timed out after ${timeoutMs}ms; check local permissions before changing config.`)), timeoutMs);
    const send = message => child.stdin.write(JSON.stringify(message) + '\n');
    child.on('error', error => finish(error));
    child.stdin.on('error', error => finish(error));
    child.stderr.on('data', data => { stderr = Buffer.concat([stderr, data]).subarray(-4096); });
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      clearTimeout(forceKill);
      // Also clean up descendants that inherited pipes from the app server.
      kill('SIGKILL');
      if (!finishing) failure = new Error(`Codex exited before skills/list completed (${code ?? signal}).`);
      if (failure) {
        const diagnostic = stderr.toString('utf8').trim();
        if (diagnostic) failure.message += `\nCodex stderr (last 4096 bytes): ${diagnostic}`;
        reject(failure);
      } else resolveResult(outcome);
    });
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', data => {
      if (finishing) return;
      bytes += Buffer.byteLength(data);
      if (bytes > maxResponseBytes) { finish(new Error('Codex response exceeds audit size limit.')); return; }
      buffer += data;
      let end;
      while (!finishing && (end = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, end);
        buffer = buffer.slice(end + 1);
        try {
          const message = JSON.parse(line);
          if (!message || typeof message !== 'object' || Array.isArray(message)) throw new Error('Invalid protocol response.');
          // Server requests have their own ID namespace, even when it overlaps ours.
          if ('method' in message || (message.id !== 1 && message.id !== 2)) continue;
          if (message.error) throw new Error(`Codex protocol error: ${JSON.stringify(message.error)}`);
          if (message.id === 1) {
            if (initialized || !message.result || typeof message.result !== 'object' || Array.isArray(message.result)) throw new Error('Invalid initialize response.');
            initialized = true;
            send({ method: 'initialized' });
            send({ id: 2, method: 'skills/list', params: { cwds: [cwd], forceReload: true } });
          } else {
            if (!initialized || !Array.isArray(message.result?.data)) throw new Error('Invalid skills/list response.');
            const matches = message.result.data.filter(item => typeof item?.cwd === 'string' && canonicalPath(item.cwd) === canonicalPath(cwd));
            if (matches.length !== 1) throw new Error(`Invalid skills/list cwd response: requested ${cwd}; returned ${JSON.stringify(message.result.data.map(item => item?.cwd))}`);
            const entry = matches[0];
            if (!Array.isArray(entry.skills) || !Array.isArray(entry.errors)
                || !entry.skills.every(skill => skill && typeof skill.enabled === 'boolean'
                  && ['name', 'path', 'description'].every(key => typeof skill[key] === 'string'))) {
              throw new Error('Invalid skills/list response.');
            }
            finish(null, entry);
          }
        } catch (error) { finish(error); return; }
      }
    });
    send({ id: 1, method: 'initialize', params: { clientInfo: { name: 'clavain_skill_audit', version: '1' }, capabilities: { experimentalApi: true } } });
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(canonicalPath(process.argv[1])).href) {
  try {
    let cwd = process.cwd();
    let output;
    for (let index = 2; index < process.argv.length; index++) {
      const flag = process.argv[index];
      if (flag === '--help') {
        console.log('Usage: node scripts/codex-skill-audit.mjs [--cwd PATH] [--output NEW_JSON_PATH]\nRequires Node 18+ and Codex app-server skills/list. Never changes config or submits a model turn.');
        process.exit(0);
      }
      if (!['--cwd', '--output'].includes(flag) || !process.argv[index + 1] || process.argv[index + 1].startsWith('--')) throw new Error(`Invalid argument: ${flag}`);
      const value = resolve(process.argv[++index]);
      if (flag === '--cwd') cwd = value; else output = value;
    }
    const report = { schema_version: 1, observed_at: new Date().toISOString(), ...summarize(await querySkills(cwd)) };
    const json = JSON.stringify(report, null, 2) + '\n';
    // Evidence files are create-only; never silently replace a previous snapshot.
    if (output) writeFileSync(output, json, { flag: 'wx', mode: 0o600 });
    console.log(json);
    if (report.errors.length) process.exitCode = 1;
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
