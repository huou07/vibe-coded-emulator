import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {cp, mkdir, readFile, readdir, writeFile, access} from 'node:fs/promises';
import {join, basename} from 'node:path';
import {fileURLToPath} from 'node:url';
if (process.platform !== 'win32' || process.arch !== 'x64') throw new Error('Windows x64 bundler only');
const root = fileURLToPath(new URL('..', import.meta.url));
const msys = process.argv[2];
const bin = join(msys, 'ucrt64/bin');
const destination = join(root, 'vendor/runtime/windows-x64');
const exists = async path => { try { await access(path); return true; } catch { return false; } };
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
await mkdir(destination, {recursive:true});
const queue = [join(root, 'work/windows-runtime/an3-native-runtime.exe')];
const visited = new Set(), files = [], runtimePackages = new Set(), licensePackages = new Set();
for (let i = 0; i < queue.length; ++i) {
  const file = queue[i], name = basename(file);
  if (visited.has(name.toLowerCase())) continue;
  visited.add(name.toLowerCase());
  const bytes = await readFile(file), offset = bytes.readUInt32LE(0x3c);
  if (bytes.readUInt32LE(offset) !== 0x4550 || bytes.readUInt16LE(offset + 4) !== 0x8664) throw new Error(`Non-x64 native dependency: ${name}`);
  const imports = execFileSync(join(bin, 'objdump.exe'), ['-p', file], {encoding:'utf8', maxBuffer:32*1024*1024});
  for (const match of imports.matchAll(/DLL Name:\s*(\S+)/g)) {
    const dependency = match[1];
    if (await exists(join(bin, dependency))) queue.push(join(bin, dependency));
    else if (!/^api-ms-win-|^ext-ms-win-/i.test(dependency) && !await exists(join(process.env.SystemRoot, 'System32', dependency))) {
      throw new Error(`Unresolved native dependency: ${name} -> ${dependency}`);
    }
  }
  await cp(file, join(destination, name));
  if (file !== queue[0]) {
    const relative = `/${file.slice(msys.length).replaceAll('\\', '/')}`;
    const owner = execFileSync(join(msys, 'usr/bin/pacman.exe'), ['-Qqo', relative], {encoding:'utf8'}).trim();
    if (!owner.startsWith('mingw-w64-ucrt-x86_64-')) throw new Error(`Cannot identify UCRT64 package owner for ${name}: ${owner}`);
    runtimePackages.add(owner);
  }
  files.push({name, size:bytes.length, sha256:sha256(bytes)});
}
// Carry the license directories for the exact MSYS2 packages that own the
// copied runtime DLLs. Build tools and unrelated packages stay out of the app.
const licenseRoot = join(msys, 'ucrt64/share/licenses');
const bundledLicenses = join(destination, 'share/licenses');
await mkdir(bundledLicenses, {recursive:true});
for (const owner of [...runtimePackages].sort()) {
  const shortName = owner.replace(/^mingw-w64-ucrt-x86_64-/, '');
  let licenseName;
  for (const candidate of [owner, shortName]) {
    if (await exists(join(licenseRoot, candidate))) { licenseName = candidate; break; }
  }
  if (!licenseName) throw new Error(`Missing runtime dependency license: ${owner}`);
  licensePackages.add(licenseName);
}
for (const packageName of [...licensePackages].sort()) {
  const source = join(licenseRoot, packageName);
  await cp(source, join(bundledLicenses, packageName), {recursive:true});
}
await cp(join(root, 'work/windows-runtime/toolchain-packages.txt'), join(destination, 'toolchain-packages.txt'));
const cores = join(root, 'vendor/libretro/windows-x64');
const coreManifest = JSON.parse((await readFile(join(cores, 'manifest.json'), 'utf8')).replace(/^\uFEFF/, ''));
if (coreManifest.platform !== 'Windows x64') throw new Error('Windows-only cores required');
for (const system of ['gba','nds','3ds']) {
  const matches = coreManifest.cores.filter(core => core.system === system);
  if (matches.length !== 1) throw new Error(`Missing unique ${system} core`);
  const core = matches[0], bytes = await readFile(join(cores, core.coreName));
  if (bytes.length !== core.size || sha256(bytes) !== core.coreSha256) throw new Error(`Core integrity failed: ${system}`);
}
await cp(cores, join(destination, 'libretro'), {recursive:true});
const sources = [];
async function sourceTree(relative) {
  for (const item of (await readdir(join(root, relative), {withFileTypes:true})).sort((a,b) => a.name.localeCompare(b.name))) {
    const path = `${relative}/${item.name}`;
    if (item.isDirectory()) await sourceTree(path);
    else if (/\.(h|cpp|json)$/.test(item.name)) sources.push({path, sha256:sha256(await readFile(join(root, path)))});
  }
}
for (const relative of ['native-runtime/core','native-runtime/video','native-runtime/platform/linux','shared/generated']) await sourceTree(relative);
await writeFile(join(destination, 'manifest.json'), JSON.stringify({platform:'Windows x64', entry:'an3-native-runtime.exe', files, runtimePackages:[...runtimePackages].sort(), runtimeLicensePackages:[...licensePackages].sort(), sources}, null, 2)+'\n');
console.log(`WINDOWS_NATIVE_RUNTIME=VERIFIED ${files.length} PE files; portable SDL/Vulkan/OpenGL sources`);
