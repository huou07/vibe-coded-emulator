#!/usr/bin/env bash
# Convenience environment for the AN3 staging control path, usable from any
# worktree so a build/deploy does not depend on the original checkout:
#
#   source tools/ssh/staging-env.sh
#   tools/ssh/check-staging-key.sh
#   ./deploy-stage.sh
#
# Only paths are defined here. The private key itself never enters this
# repository; it stays in the owner's ~/.ssh and must already be authorized on
# the staging host.
export AN3_STAGING_SSH_IDENTITY_FILE="${AN3_STAGING_SSH_IDENTITY_FILE:-$HOME/.ssh/an3_codex_ed25519}"
export AN3_STAGING_SSH_KNOWN_HOSTS="${AN3_STAGING_SSH_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"
