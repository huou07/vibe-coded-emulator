#!/bin/sh
set -eu

# This root-owned helper accepts no input and emits one CPU-package power
# sample. It is the sole command granted to the unprivileged web service.
output="$(/usr/sbin/turbostat --quiet --show PkgWatt --interval 1 --num_iterations 1 2>/dev/null)"
printf '%s\n' "$output" | awk '
  NR > 1 {
    for (field = 1; field <= NF; field++) {
      if ($field ~ /^[0-9]+([.][0-9]+)?$/) value = $field
    }
  }
  END {
    if (value == "") exit 1
    print value
  }
'
