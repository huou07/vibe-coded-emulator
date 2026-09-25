#!/usr/bin/env bash
# Fetch the pinned Eden source and apply AN3's single CMake integration hook.
set -euo pipefail

EDEN_ROOT="${AN3_EDEN_ROOT:?set AN3_EDEN_ROOT to an isolated checkout path}"
EDEN_COMMIT="${AN3_EDEN_COMMIT:-7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c}"
EDEN_REPOSITORY="${AN3_EDEN_REPOSITORY:-https://git.eden-emu.dev/eden-emu/eden.git}"
BRIDGE_ROOT="${AN3_EDEN_BRIDGE_ROOT:?set AN3_EDEN_BRIDGE_ROOT to native/eden-bridge}"

if [[ ! -d "$EDEN_ROOT/.git" ]]; then
  if [[ -n "$(find "$EDEN_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    echo "Eden checkout path is nonempty but has no Git metadata: $EDEN_ROOT" >&2
    exit 2
  fi
  mkdir -p "$(dirname "$EDEN_ROOT")"
  git init -q "$EDEN_ROOT"
  git -C "$EDEN_ROOT" remote add origin "$EDEN_REPOSITORY"
  git -C "$EDEN_ROOT" fetch --depth=1 origin "$EDEN_COMMIT"
  git -C "$EDEN_ROOT" checkout --detach FETCH_HEAD
fi

[[ "$(git -C "$EDEN_ROOT" rev-parse HEAD)" == "$EDEN_COMMIT" ]] || {
  echo "Eden checkout is not pinned to $EDEN_COMMIT" >&2
  exit 2
}
[[ -f "$EDEN_ROOT/CMakeLists.txt" && -d "$BRIDGE_ROOT/integration" ]] || {
  echo 'Pinned Eden source or AN3 bridge integration files are missing.' >&2
  exit 2
}

python3 - "$EDEN_ROOT/CMakeLists.txt" "$BRIDGE_ROOT" <<'PY'
from pathlib import Path
import sys

cmake = Path(sys.argv[1])
bridge = Path(sys.argv[2]).resolve().as_posix()
text = cmake.read_text()
assignment = f'set(AN3_EDEN_BRIDGE_DIR "{bridge}")\n'
insertion = (
    '\nif(DEFINED AN3_EDEN_BRIDGE_DIR)\n'
    '    add_subdirectory("${AN3_EDEN_BRIDGE_DIR}/integration" an3_eden_bridge)\n'
    'endif()\n'
)
if assignment not in text:
    text = assignment + text
if 'if(DEFINED AN3_EDEN_BRIDGE_DIR)' not in text:
    needle = '\nadd_subdirectory(src)\n'
    if needle not in text:
        raise SystemExit('Eden root CMakeLists.txt has no source insertion point')
    text = text.replace(needle, insertion + needle, 1)
cmake.write_text(text)
PY
