// Stage the bundled Linux native player (SDL/GTK window, input and audio) and
// the pinned GBA/NDS/3DS libretro cores as Tauri bundle resources. The Tauri
// shell owns the local-ROM library/import UI; this runtime owns gameplay only.
import {createHash} from 'node:crypto';
import {cp, mkdir, readFile, readdir, rm, writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

if (process.platform !== 'linux' || process.arch !== 'x64') throw new Error('Linux x86_64 bundler only');
const root = fileURLToPath(new URL('..', import.meta.url));
const binary = join(root, 'work/linux-build/an3-offline-native');
const cores = join(root, 'vendor/libretro/linux-x86_64');
const destination = join(root, 'vendor/runtime/linux-x86_64');
const entry = 'an3-offline-native';
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

const bytes = await readFile(binary);
if (bytes.length < 4096) throw new Error('Linux native runtime is unexpectedly small.');
if (bytes[0] !== 0x7f || bytes[1] !== 0x45 || bytes[2] !== 0x4c || bytes[3] !== 0x46) {
  throw new Error('Linux native runtime is not an ELF executable.');
}
const coreManifest = JSON.parse(await readFile(join(cores, 'manifest.json'), 'utf8'));
if (coreManifest.platform !== 'Linux x86_64') throw new Error('Linux-only cores required.');
for (const system of ['gba', 'nds', '3ds']) {
  const matches = coreManifest.cores.filter(core => core.system === system);
  if (matches.length !== 1) throw new Error(`Missing unique ${system} core.`);
  const core = matches[0];
  if (sha256(await readFile(join(cores, core.coreName))) !== core.coreSha256) {
    throw new Error(`Core integrity failed: ${system}`);
  }
}

await rm(destination, {recursive: true, force: true});
await mkdir(destination, {recursive: true});
await cp(binary, join(destination, entry));
await cp(cores, join(destination, 'libretro'), {recursive: true});
// GTK's fallback theme is embedded, but its compiled defaults need schemas for
// the native file picker and settings. The host provides a compatible set.
for (const relative of ['share/glib-2.0/schemas']) {
  try {
    await cp(join('/usr', relative), join(destination, relative), {recursive: true});
  } catch {
    // A minimal builder may not ship the schemas; GTK falls back to defaults.
  }
}

const sources = [];
async function sourceTree(relative) {
  for (const item of (await readdir(join(root, relative), {withFileTypes: true})).sort((a, b) => a.name.localeCompare(b.name))) {
    const path = `${relative}/${item.name}`;
    if (item.isDirectory()) await sourceTree(path);
    else if (/\.(h|cpp|json)$/.test(item.name)) sources.push({path, sha256: sha256(await readFile(join(root, path)))});
  }
}
for (const relative of ['native-runtime/core', 'native-runtime/video', 'native-runtime/platform/linux', 'shared/generated']) {
  await sourceTree(relative);
}
await writeFile(join(destination, 'manifest.json'), JSON.stringify({
  platform: 'Linux x86_64',
  entry,
  files: [{name: entry, size: bytes.length, sha256: sha256(bytes)}],
  cores: coreManifest.cores,
  sources,
}, null, 2) + '\n');
console.log(`LINUX_NATIVE_RUNTIME=VERIFIED ${entry} ${sha256(bytes)}`);
