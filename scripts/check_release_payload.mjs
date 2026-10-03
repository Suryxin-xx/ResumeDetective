import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { DatabaseSync } from 'node:sqlite';

const [payloadArg, version] = process.argv.slice(2);
assert.match(version || '', /^\d+\.\d+\.\d+$/);
const root = path.resolve(payloadArg || '');
const repo = path.resolve(import.meta.dirname, '..');
const hash = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const exact = new Set(['ResumeDetective.exe', 'ResumeDetective.exe.sha256', 'README.md', 'PACKAGING.md', 'LICENSE', 'assets/app-icon-128.png', 'data/resume_detective.db', 'data.example/.env.example', 'data.example/README.md', 'data.example/sample-data.json']);
const files = [];
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    assert(!entry.isSymbolicLink(), `Release cannot contain a symbolic link: ${entry.name}`);
    if (entry.isDirectory()) walk(full);
    else {
      assert(entry.isFile(), 'Unexpected release entry');
      const relative = path.relative(root, full).replaceAll('\\', '/');
      assert(exact.has(relative) || /^screenshots\/v4-[\w-]+\.(png|jpg)$/.test(relative), `Unexpected or private release file: ${relative}`);
      files.push(relative);
      if (relative !== 'ResumeDetective.exe' && relative !== 'ResumeDetective.exe.sha256' && relative !== 'data/resume_detective.db') {
        assert.equal(hash(full), hash(path.join(repo, relative)), `Public source mismatch: ${relative}`);
        if (/\.(md|json|example)$/.test(relative) || relative === 'LICENSE') {
          const text = fs.readFileSync(full, 'utf8');
          assert(!/sk-[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/.test(text), `Possible secret in release file: ${relative}`);
          if (relative === 'data.example/.env.example') {
            for (const line of text.split(/\r?\n/)) {
              if (/^(DEEPSEEK|REASONIX)_API_KEY[ \t]*=/.test(line)) assert.equal(line.slice(line.indexOf('=') + 1).trim(), '', 'API example must not contain a key');
            }
          }
        }
      }
    }
  }
}
walk(root);
for (const expected of exact) assert(files.includes(expected), `Missing release file: ${expected}`);
assert(fs.readFileSync(path.join(root, 'ResumeDetective.exe.sha256'), 'utf8').startsWith(hash(path.join(root, 'ResumeDetective.exe')) + '  '), 'EXE checksum mismatch');
for (const name of ['README.md', 'PACKAGING.md']) assert(fs.readFileSync(path.join(root, name), 'utf8').includes(version), 'Version missing in documentation');
const sample = JSON.parse(fs.readFileSync(path.join(repo, 'data.example/sample-data.json'), 'utf8'));
// The whitelist above rejects WAL/SHM sidecars. Demo generation closes and
// checkpoints the DB; immutable mode prevents validation creating new sidecars.
const databaseURL = pathToFileURL(path.join(root, 'data/resume_detective.db'));
databaseURL.search = '?mode=ro&immutable=1';
const db = new DatabaseSync(databaseURL.href, { readOnly: true });
assert.equal(db.prepare('PRAGMA integrity_check').get().integrity_check, 'ok');
assert.equal(db.prepare('PRAGMA user_version').get().user_version, 13);
const count = table => db.prepare(`SELECT COUNT(*) AS total FROM ${table}`).get().total;
const expectedCounts = { applications: sample.applications.length, resumes: sample.applications.length, materials: sample.materials.length, profile: 1, job_targets: sample.targets.length, job_tasks: sample.tasks.length, interviews: sample.interviews.length, offers: sample.offers.length, income_plans: 0, application_attachments: 0 };
for (const [table, expected] of Object.entries(expectedCounts)) assert.equal(count(table), expected, `Demo count mismatch: ${table}`);
assert.deepEqual(db.prepare('SELECT r.company_name, r.position_name FROM applications a JOIN resumes r ON r.id=a.resume_id ORDER BY r.company_name, r.position_name').all().map(row => [row.company_name, row.position_name]), sample.applications.map(row => [row.companyName, row.positionName]).sort((a,b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0), 'Demo applications differ from the public sample');
assert.equal(count('demo_records'), Object.values(expectedCounts).reduce((sum, n) => sum + n, 0), 'Demo markers incomplete');
db.close();
console.log(`[release safety] Passed: ${files.length} public files; schema v13; ${sample.applications.length} synthetic applications; EXE checksum verified.`);
