#!/usr/bin/env bash
# Read-only staging authentication preflight. It never prompts for a password.
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/staging-common.sh"

[[ "$#" -eq 0 ]] || ssh_die "Usage: $0"
staging_ssh 'printf "STAGING_SSH_KEY_AUTH=PASS\\n"'
