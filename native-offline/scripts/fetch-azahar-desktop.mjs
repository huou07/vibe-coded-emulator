import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { inflateRawSync } from 'node:zlib';

const root = fileURLToPath(new URL('..', import.meta.url));
const lock = JSON.parse(await readFile(join(root, 'shared/azahar-desktop-lock.json'), 'utf8'));
const target = process.argv[2] || (process.platform === 'win32' ? 'windows-x64' : process.platform === 'linux' ? 'linux-x86_64' : '');
const entry = lock.targets[target];
if (!entry) throw new Error('Usage: fetch-azahar-desktop.mjs <linux-x86_64|windows-x64>');
const destination = join(root, 'vendor/libretro', target);
const cache = resolve(process.env.AN3_DEPENDENCY_CACHE || join(root, 'work/dependency-cache'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const checked = async (path, sha) => {
  try { const bytes = await readFile(path); return hash(bytes) === sha ? bytes : null; } catch { return null; }
};
await mkdir(destination, {recursive:true});
await mkdir(cache, {recursive:true});
async function download(url, sha) {
  const cached = join(cache, sha);
  let bytes = await checked(cached, sha);
  if (!bytes) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Official Azahar download: HTTP ${response.status}`);
    bytes = Buffer.from(await response.arrayBuffer());
    if (hash(bytes) !== sha) throw new Error('Official Azahar SHA-256 mismatch; refusing changed dependency');
    await writeFile(cached, bytes);
  }
  return bytes;
}
// Extract only the pinned member into memory. No archive paths reach the file
// system. Use the central directory because ZIP local headers may omit sizes.
function coreFromZip(zip) {
  let eocd = zip.length - 22;
  while (eocd >= Math.max(0, zip.length - 65557) && zip.readUInt32LE(eocd) !== 0x06054b50) --eocd;
  if (eocd < 0 || zip.readUInt32LE(eocd) !== 0x06054b50) throw new Error('Missing ZIP directory');
  let offset = zip.readUInt32LE(eocd + 16), found;
  for (let index = 0; index < zip.readUInt16LE(eocd + 10); ++index) {
    if (zip.readUInt32LE(offset) !== 0x02014b50) throw new Error('Invalid ZIP entry');
    const nameLength = zip.readUInt16LE(offset + 28);
    const name = zip.subarray(offset + 46, offset + 46 + nameLength).toString('utf8');
    if (name === entry.coreName) {
      if (found || zip.readUInt32LE(offset + 24) !== entry.size) throw new Error('Ambiguous/incorrect core member');
      const local = zip.readUInt32LE(offset + 42);
      if (zip.readUInt32LE(local) !== 0x04034b50) throw new Error('Invalid ZIP local header');
      const start = local + 30 + zip.readUInt16LE(local + 26) + zip.readUInt16LE(local + 28);
      const compressed = zip.subarray(start, start + zip.readUInt32LE(offset + 20));
      const method = zip.readUInt16LE(offset + 10);
      found = method === 0 ? compressed : method === 8 ? inflateRawSync(compressed, {maxOutputLength:entry.size}) : null;
      if (!found) throw new Error('Unsupported ZIP compression');
    }
    offset += 46 + nameLength + zip.readUInt16LE(offset + 30) + zip.readUInt16LE(offset + 32);
  }
  if (!found || found.length !== entry.size || hash(found) !== entry.coreSha256) throw new Error('Extracted core integrity failed');
  return found;
}
const archiveUrl = `https://github.com/azahar-emu/azahar/releases/download/${lock.version}/${entry.archiveName}`;
if (!await checked(join(destination, entry.coreName), entry.coreSha256)) {
  await writeFile(join(destination, entry.coreName), coreFromZip(await download(archiveUrl, entry.archiveSha256)));
}
const licenseName = 'Azahar-GPL-2.0-or-later.txt';
if (!await checked(join(destination, licenseName), lock.licenseSha256)) {
  await writeFile(join(destination, licenseName), await download(lock.licenseUrl, lock.licenseSha256));
}
let manifest = {platform:entry.platform, cores:[]};
try { manifest = JSON.parse((await readFile(join(destination, 'manifest.json'), 'utf8')).replace(/^\uFEFF/, '')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
if (manifest.platform !== entry.platform) throw new Error('Native core manifest platform mismatch');
manifest.cores = [...manifest.cores.filter(core => core.system !== '3ds'), {
  system:'3ds', engine:'Azahar libretro', version:lock.version, ...entry, archiveUrl,
  sourceUrl:lock.sourceUrl, sourceSha256:lock.sourceSha256,
  license:'GPL-2.0-or-later', licenseName, licenseSha256:lock.licenseSha256
}];
await writeFile(join(destination, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`AZAHAR_DESKTOP=VERIFIED ${target} ${entry.coreSha256}`);
