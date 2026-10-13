#!/usr/bin/env bash
# Inventory and safe-prune helper for VCE/an3 build scratch left in the operator home
# directory. Read-only by default; --apply-cache removes only regenerable build
# caches (Rust target/, Tauri gen/, node_modules/, cache dirs). Source trees and
# acceptance evidence are never removed by this script.
#
# No `set -e`: this is an inventory tool that must report on unreadable or
# partially removed trees instead of aborting on the first bad path.
set -uo pipefail

HOME_DIR="${HOME_DIR:-/home/huou07}"

APPLY_CACHE=0
INCLUDE_OTHER_PROJECTS=0
for arg in "$@"; do
  case "$arg" in
    --apply-cache) APPLY_CACHE=1 ;;
    --include-other-projects) INCLUDE_OTHER_PROJECTS=1 ;;
    -h|--help)
      sed -n '2,9p' "$0"
      exit 0
      ;;
  esac
done

# VCE/an3 scratch roots. Anything outside these globs is out of scope.
SCRATCH_PATTERNS=(
  'an3-*'
  'vce-*'
  'eden'
  'huou07-release-*'
)

# Belongs to the separate OpenCut V2 / model-orchestrator project. Opt-in only,
# because VCE must not delete another project's scratch.
if [ "$INCLUDE_OTHER_PROJECTS" -eq 1 ]; then
  SCRATCH_PATTERNS+=( 'opencut-v2-*' 'or-*' )
fi

# Regenerable build output, matched on a whole directory component.
# Deliberately NOT listed: `gen` — VCE tracks source under
# native-offline/src-tauri/gen/{android,schemas}, so that name is not safe to
# prune blindly. Gradle output inside it is reached through `build` instead.
CACHE_COMPONENTS=(
  'target'
  'node_modules'
  'build'
  '.cache'
  '.gradle'
  '.cxx'
  '.externalNativeBuild'
  'flatpak-checkout-*'
)

human() {
  local kib=$1
  if [ "$kib" -ge 1048576 ]; then
    awk -v k="$kib" 'BEGIN{printf "%.1fG", k/1048576}'
  elif [ "$kib" -ge 1024 ]; then
    awk -v k="$kib" 'BEGIN{printf "%.1fM", k/1024}'
  else
    printf '%dK' "$kib"
  fi
}

roots=()
while IFS= read -r line; do
  [ -n "$line" ] && roots+=("$line")
done < <(
  for p in "${SCRATCH_PATTERNS[@]}"; do
    find "$HOME_DIR" -maxdepth 1 -mindepth 1 -type d -name "$p" -print 2>/dev/null
  done | sort -u
)

if [ "${#roots[@]}" -eq 0 ]; then
  echo "No scratch roots matched under $HOME_DIR."
  exit 0
fi

printf '%-44s %-9s %-8s %-6s %-12s %s\n' ROOT SIZE FILES GIT NEWEST CACHE_KIB
printf '%.0s-' {1..110}
printf '\n'

total_cache=0

for root in "${roots[@]}"; do
  if [ ! -r "$root" ]; then
    printf '%-44s %-9s %-8s %-6s %-12s %s\n' \
      "$(basename "$root")" "?" "?" "?" "?" "unreadable by $(id -un)"
    continue
  fi

  size_kib=$(du -sk "$root" 2>/dev/null | cut -f1)
  files=$(find "$root" -type f 2>/dev/null | wc -l)
  if [ -e "$root/.git" ]; then git_state=git; else git_state=-; fi
  newest=$(find "$root" -type f -printf '%TY-%Tm-%Td\n' 2>/dev/null | sort -r | head -1)
  [ -n "$newest" ] || newest=-

  cache_kib=0
  for c in "${CACHE_COMPONENTS[@]}"; do
    while IFS= read -r d; do
      [ -n "$d" ] || continue
      k=$(du -sk "$d" 2>/dev/null | cut -f1)
      cache_kib=$((cache_kib + ${k:-0}))
    done < <(find "$root" -type d -name "$c" -prune -print 2>/dev/null)
  done

  printf '%-44s %-9s %-8s %-6s %-12s %s\n' \
    "$(basename "$root")" "$(human "$size_kib")" "$files" "$git_state" "$newest" "$cache_kib"
  total_cache=$((total_cache + cache_kib))
done

printf '%.0s-' {1..110}
printf '\n'
printf 'Total regenerable build cache under listed roots: %s\n' "$(human "$total_cache")"
printf 'Never touched by this tool: source trees, acceptance evidence, logs, packages.\n'

if [ "$APPLY_CACHE" -eq 1 ]; then
  echo
  echo "APPLY: removing regenerable build caches."
  for root in "${roots[@]}"; do
    [ -r "$root" ] && [ -w "$root" ] || continue
    for c in "${CACHE_COMPONENTS[@]}"; do
      find "$root" -type d -name "$c" -prune -print 2>/dev/null | while IFS= read -r d; do
        [ -n "$d" ] || continue
        rm -rf -- "$d" && echo "removed $d"
      done
    done
  done
else
  echo
  echo "Dry run only. Re-run with --apply-cache to delete the listed build caches."
fi
