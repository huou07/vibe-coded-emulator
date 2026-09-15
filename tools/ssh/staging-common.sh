#!/usr/bin/env bash
# Shared key-only SSH settings for AN3's isolated staging host.
set -euo pipefail

ssh_die() { printf '%s\n' "ERROR: $*" >&2; exit 1; }

AN3_STAGING_SSH_HOST="${AN3_STAGING_SSH_HOST:-192.168.1.8}"
AN3_STAGING_SSH_USER="${AN3_STAGING_SSH_USER:-huou07}"
AN3_STAGING_SSH_KNOWN_HOSTS="${AN3_STAGING_SSH_KNOWN_HOSTS:-${HOME}/.ssh/known_hosts}"
AN3_STAGING_SSH_TARGET="${AN3_STAGING_SSH_USER}@${AN3_STAGING_SSH_HOST}"

[[ -r "$AN3_STAGING_SSH_KNOWN_HOSTS" ]] || ssh_die "Known-hosts file is unavailable. Verify and add the staging host key before using this control path."

AN3_STAGING_SSH_ARGS=(
  -o BatchMode=yes
  -o PasswordAuthentication=no
  -o KbdInteractiveAuthentication=no
  -o PreferredAuthentications=publickey
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=$AN3_STAGING_SSH_KNOWN_HOSTS"
  -o ConnectTimeout=10
)

if [[ -n "${AN3_STAGING_SSH_IDENTITY_FILE:-}" ]]; then
  [[ -r "$AN3_STAGING_SSH_IDENTITY_FILE" ]] || ssh_die "Configured staging identity file is unavailable."
  AN3_STAGING_SSH_ARGS+=( -i "$AN3_STAGING_SSH_IDENTITY_FILE" -o IdentitiesOnly=yes )
fi

staging_ssh() {
  command ssh "${AN3_STAGING_SSH_ARGS[@]}" "$AN3_STAGING_SSH_TARGET" "$@"
}
