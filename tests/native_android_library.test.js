const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const web = path.resolve(__dirname, '../native-offline/web');
function library({ systems, android = true } = {}) {
  const handlers = new Map();
  const calls = [];
  const cards = [];
  const options = ['gba', 'nds', '3ds', 'psx'].map(value => ({ value, disabled: false, textContent: value }));
  const coreLabel = { textContent: '' };
  let observer;
  const context = {
    navigator: { userAgent: android ? 'Android' : 'Macintosh' },
    location: { search: '', pathname: '/index.html' },
    URLSearchParams,
    AN3AndroidNative: { launchNative: (...args) => { calls.push(args); return ''; } },
    addEventListener: (name, callback) => handlers.set(name, callback),
    document: {
      querySelector: selector => selector === '#offlineCoreState' ? { previousElementSibling: coreLabel } : null,
      querySelectorAll: () => options,
      getElementById: id => id === 'offlineGameGrid' ? { querySelectorAll: () => cards } : null,
    },
    MutationObserver: class {
      constructor(callback) { observer = callback; }
      observe() {}
    },
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(web, 'native-bootstrap.js'), 'utf8'), context);
  if (systems !== undefined) context.AN3NativeIntegratedSystems = systems;
  const addCard = (system, native = true) => {
    const play = { disabled: false, textContent: native ? `Play ${system} native` : 'Play now' };
    cards.push({ dataset: { system }, querySelector: () => play });
    return play;
  };
  vm.runInContext(fs.readFileSync(path.join(web, 'android-staging.js'), 'utf8'), context);
  return { context, calls, options, coreLabel, addCard,
    ready: () => handlers.get('DOMContentLoaded')?.(),
    refresh: () => observer?.() };
}

test('packaged Android capability keeps 3DS selectable and launchable after library observation', async () => {
  const page = library();
  const play = page.addCard('3ds');
  page.ready();
  page.refresh();
  assert.equal(play.disabled, false);
  assert.match(play.textContent, /native/);
  assert.equal(page.options.find(option => option.value === '3ds').disabled, false);
  assert.match(page.coreLabel.textContent, /3DS/);
  await page.context.AN3NativeLaunchGame('11111111-1111-4111-8111-111111111111', '3ds');
  assert.deepEqual(page.calls, [['11111111-1111-4111-8111-111111111111', '3ds']]);
});

test('asynchronously imported 3DS card remains playable', () => {
  const page = library();
  page.ready();
  const play = page.addCard('3ds');
  page.refresh();
  page.refresh();
  assert.equal(play.disabled, false);
});

test('GBA/NDS remain playable and unsupported systems remain blocked', () => {
  const page = library();
  const gba = page.addCard('gba');
  const nds = page.addCard('nds');
  const psx = page.addCard('psx');
  const legacy = page.addCard('nds', false);
  page.ready();
  assert.equal(gba.disabled, false);
  assert.equal(nds.disabled, false);
  assert.equal(psx.disabled, true);
  assert.equal(psx.textContent, 'Native core unavailable');
  // A supported system is never blocked, even when an older record carries a
  // non-native label: offline.js recovers its native ROM id from the stored
  // native path, so the guard must not disable it or demand a re-import.
  assert.equal(legacy.disabled, false);
  assert.equal(legacy.textContent, 'Play now');
});

test('capability-restricted Android bundles keep missing 3DS support blocked in the library', () => {
  const page = library({ systems: ['gba', 'nds'] });
  const play = page.addCard('3ds');
  page.ready();
  assert.equal(play.disabled, true);
  assert.equal(page.options.find(option => option.value === '3ds').disabled, true);
  assert.doesNotMatch(page.coreLabel.textContent, /3DS/);
});

test('missing capability declaration fails closed', () => {
  const page = library({ systems: null });
  const play = page.addCard('3ds');
  page.ready();
  assert.equal(play.disabled, true);
  assert.equal(page.options.find(option => option.value === '3ds').disabled, true);
});

test('Android-only guard does not modify desktop library controls', () => {
  const page = library({ android: false });
  const play = page.addCard('3ds');
  page.ready();
  assert.equal(play.disabled, false);
  assert.equal(page.options.find(option => option.value === '3ds').disabled, false);
});
