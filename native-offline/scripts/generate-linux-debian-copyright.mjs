// SPDX-License-Identifier: GPL-3.0-or-later
// Generate the Debian DEP-5 copyright file from the exact package license texts.
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const output = resolve(process.argv[2] ?? join(root, 'work/linux-build/debian-copyright'));

const entries = [
  {
    files: '*',
    copyright: '2026 Vibe Coded Emulator contributors',
    license: 'GPL-3.0-or-later',
    path: join(root, '../LICENSE'),
  },
  {
    files: 'usr/lib/VibeCodedEmulator/runtime/linux-x86_64/libretro/azahar_libretro.so',
    copyright: 'Azahar Emulator Project',
    license: 'GPL-2.0-or-later',
    path: join(root, 'vendor/libretro/linux-x86_64/Azahar-GPL-2.0-or-later.txt'),
  },
  {
    files: 'usr/lib/VibeCodedEmulator/runtime/linux-x86_64/libretro/mgba_libretro.so',
    copyright: 'mGBA contributors',
    license: 'MPL-2.0',
    path: join(root, 'vendor/libretro/linux-x86_64/mGBA-MPL-2.0.txt'),
  },
  {
    files: 'usr/lib/VibeCodedEmulator/runtime/linux-x86_64/libretro/melondsds_libretro.so',
    copyright: 'melonDS DS contributors',
    license: 'GPL-3.0-or-later',
    path: join(root, 'vendor/libretro/linux-x86_64/melonDS-DS-GPL-3.0-or-later.txt'),
  },
  {
    files: 'usr/lib/VibeCodedEmulator/switch/linux-x86_64/an3_switch_companion',
    copyright: 'Eden Emulator Project and Vibe Coded Emulator contributors',
    license: 'GPL-3.0-or-later',
    path: join(root, 'vendor/switch/linux-x86_64/EDEN-GPL-3.0-or-later.txt'),
  },
  {
    files: 'usr/lib/VibeCodedEmulator/an3-offline-native',
    copyright: 'RetroArch team',
    license: 'MIT',
    path: join(root, 'native-runtime/core/vendor/libretro.h.LICENSE.txt'),
  },
  {
    files: 'usr/lib/VibeCodedEmulator/an3-offline-native',
    copyright: 'Lucide Icons and Contributors; Cole Bemis',
    license: 'ISC and MIT',
    path: join(root, '../static/LUCIDE-LICENSE.txt'),
  },
  {
    files: 'usr/lib/VibeCodedEmulator/an3-offline-native',
    copyright: 'Pixelify Sans authors',
    license: 'SIL Open Font License 1.1',
    path: join(root, '../static/fonts/OFL-PixelifySans.txt'),
  },
  {
    files: 'usr/lib/VibeCodedEmulator/an3-offline-native',
    copyright: 'Roboto Condensed authors',
    license: 'SIL Open Font License 1.1',
    path: join(root, '../static/fonts/OFL-RobotoCondensed.txt'),
  },
];

const indent = (text) => text.replace(/\r\n/g, '\n').trimEnd().split('\n').map((line) => ` ${line}`).join('\n');
const noticePaths = [join(root, '../THIRD_PARTY_NOTICES.md'), join(root, 'THIRD_PARTY_NOTICES.md')];
const notices = (await Promise.all(noticePaths.map((path) => readFile(path, 'utf8')))).join('\n\n---\n\n');

const sections = [];
for (const entry of entries) {
  let licenseText;
  try {
    licenseText = await readFile(entry.path, 'utf8');
  } catch (error) {
    throw new Error(`Required Debian license text is missing: ${entry.path}`, {cause: error});
  }
  sections.push([
    `Files: ${entry.files}`,
    `Copyright: ${entry.copyright}`,
    `License: ${entry.license}`,
    indent(licenseText),
  ].join('\n'));
}

const document = [
  'Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/',
  'Upstream-Name: Vibe Coded Emulator',
  '',
  ...sections,
  'Comment: The following project and third-party notices are included for convenient attribution.',
  indent(notices),
  '',
].join('\n\n');

await mkdir(dirname(output), {recursive: true});
await writeFile(output, document, 'utf8');
console.log(`DEBIAN_COPYRIGHT=PASS ${output}`);
