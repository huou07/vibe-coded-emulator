// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');

const code = fs.readFileSync('static/bug-report.js', 'utf8');
const load = () => { const context = {}; vm.runInNewContext(code, context); return context.AN3BugReport; };
const FAKE_TOKEN = 'ghp_' + 'A'.repeat(36);

test('client sanitizer removes credentials, identities, and personal paths', () => {
  const api = load();
  const text = api.sanitizeText(
    'token=' + FAKE_TOKEN + ' mac de:ad:be:ef:00:11 ip 10.1.2.3 ~/<REDACTED_PATH> a@b.invalid'
  );
  assert.doesNotMatch(text, /ghp_/);
  assert.doesNotMatch(text, /de:ad:be:ef:00:11/);
  assert.doesNotMatch(text, /10\.1\.2\.3/);
  assert.doesNotMatch(text, /developer/);
  assert.doesNotMatch(text, /a@b\.invalid/);
  assert.doesNotMatch(text, /\.gba/);
});

test('client sanitizer drops forbidden keys before upload', () => {
  const api = load();
  const clean = api.sanitizeReport({
    description: 'crash',
    romPath: '~/<REDACTED_PATH>',
    accessToken: FAKE_TOKEN,
    saveState: 'AAECAwQ=',
    settings: {renderer: 'webgl2', refreshToken: 'nope'},
    logs: ['ok']
  });
  const serialized = JSON.stringify(clean);
  assert.doesNotMatch(serialized, /romPath|accessToken|saveState|refreshToken|developer|ghp_/);
  assert.equal(clean.settings.renderer, 'webgl2');
  assert.equal(clean.description, 'crash');
});

test('client forbidden-key detection is normalized', () => {
  const api = load();
  assert.equal(api.isForbiddenKey('rom_path'), true);
  assert.equal(api.isForbiddenKey('romPath'), true);
  assert.equal(api.isForbiddenKey('myAccessToken'), true);
  assert.equal(api.isForbiddenKey('renderer'), false);
});
