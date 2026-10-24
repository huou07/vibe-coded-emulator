// Route desktop entrypoints without preparing artifacts for another OS.
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const mode = process.argv[2];
const root = fileURLToPath(new URL('../', import.meta.url));
const build = { darwin: 'build:macos:app', linux: 'build:deb', win32: 'build:windows' };
const dev = { darwin: 'dev:macos', linux: 'dev:prepared', win32: 'dev:prepared' };
const script = (mode === 'build' ? build : mode === 'dev' ? dev : {})[process.platform];
if (!script) {
  console.error('Unsupported desktop command or host; use build or dev on macOS, Linux or Windows.');
  process.exit(2);
}
if (process.argv.includes('--print-plan')) {
  console.log(JSON.stringify({ platform: process.platform, mode, script }));
  process.exit(0);
}
if (mode === 'dev' && process.platform !== 'darwin') {
  const runtime = process.platform === 'linux'
    ? 'vendor/runtime/linux-x86_64/an3-offline-native'
    : 'vendor/runtime/windows-x64/an3-native-runtime.exe';
  if (!existsSync(new URL('../' + runtime, import.meta.url))) {
    console.error('Missing prepared native player: ' + runtime +
      '. Prepare it on the matching authorized platform builder first; see docs/development-workflows.md.');
    process.exit(3);
  }
}
// npm supplies its CLI path; use Node directly to avoid platform shell quoting.
if (!process.env.npm_execpath) {
  console.error('Run this entrypoint through npm run ' + mode + '.');
  process.exit(2);
}
const result = spawnSync(process.execPath, [process.env.npm_execpath, 'run', script], {
  cwd: root, stdio: 'inherit',
});
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
