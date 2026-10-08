// Stage the pinned Eden companion for Linux x86_64 packaging. Linux system
// libraries remain package/runtime dependencies; the manifest records the
// exact binary and upstream pin so an artifact cannot claim Switch support
// merely because an Eden source tree exists.
import {createHash} from 'node:crypto';
import {copyFile, mkdir, readFile, rm, writeFile, access} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const source = process.env.AN3_SWITCH_COMPANION_BUILD ?? '/tmp/eden-build/bin/an3_switch_companion';
const edenRoot = process.env.AN3_EDEN_ROOT ?? '/tmp/eden';
const commit = process.env.AN3_EDEN_COMMIT ?? '7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c';
const destination = join(root, 'vendor/switch/linux-x86_64');
const binary = join(destination, 'an3_switch_companion');
const exists = async path => { try { await access(path); return true; } catch { return false; } };
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

if (process.platform !== 'linux' || process.arch !== 'x64') throw new Error('Linux x86_64 staging only');
if (!await exists(source)) throw new Error(`Missing Linux Eden companion: ${source}`);
await rm(destination, {recursive: true, force: true});
await mkdir(destination, {recursive: true});
await copyFile(source, binary);
const bytes = await readFile(binary);
let license = 'EDEN-GPL-3.0-or-later.txt is supplied by the upstream source checkout.';
const licensePath = (await Promise.all(['LICENSE.txt', 'LICENSE'].map(async name => {
  const path = join(edenRoot, name);
  return await exists(path) ? path : null;
}))).find(Boolean);
if (licensePath) {
  await copyFile(licensePath, join(destination, 'EDEN-GPL-3.0-or-later.txt'));
  license = 'EDEN-GPL-3.0-or-later.txt';
}
const manifest = {
  name: 'an3_switch_companion',
  platform: 'Linux x86_64',
  bridgeAbi: 3,
  source: 'native/eden-bridge (compiled inside Eden build tree)',
  eden: {upstream: 'https://git.eden-emu.dev/eden-emu/eden', commit},
  license: 'GPL-3.0-or-later', licenseText: license,
  size: bytes.length, sha256: sha256(bytes),
  runtime: 'system Vulkan/SDL3/FFmpeg libraries declared by the DEB/Flatpak runtime',
};
await writeFile(join(destination, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`SWITCH_COMPANION_STAGED=${binary}`);
console.log(`SWITCH_COMPANION_SHA256=${manifest.sha256}`);
