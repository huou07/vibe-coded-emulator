# AN3 staging SSH control path

This is the only Codex-operable SSH path for staging. It uses an owner-installed public key or an already-unlocked SSH agent, requires a verified host key, and disables password and keyboard-interactive authentication. It has no password, token, serial, or copied credential artifact.

## One-time owner bootstrap

Perform these steps manually in a trusted local Terminal; type any password only into that Terminal prompt, never into a Codex message, command, report, script, or file.

1. Create a dedicated Ed25519 key protected by the owner-controlled macOS SSH agent/keychain, for example at `~/an3-codex-staging`.
2. Verify the staging host's SSH fingerprint out of band, then add that verified key to `~/known_hosts`. Do not use `StrictHostKeyChecking=no` or an ephemeral known-hosts file.
3. Add only the public half of the dedicated key to the authorized staging account's `~/.ssh/authorized_keys`, with `700` permissions on `~/.ssh` and `600` on `authorized_keys`.
4. Load the private key into the owner-controlled SSH agent/keychain. Do not give Codex the key passphrase.

The owner may instead configure an existing verified staging key. Codex only needs the key to be available through the SSH agent or an owner-approved `AN3_STAGING_SSH_IDENTITY_FILE` path.

## Preflight

```bash
export AN3_STAGING_SSH_IDENTITY_FILE=~/an3-codex-staging
export AN3_STAGING_SSH_KNOWN_HOSTS=~/known_hosts
<legacy-checkout>/tools/ssh/check-staging-key.sh
```

Only `STAGING_SSH_KEY_AUTH=PASS` authorizes staging deployment work. Authentication failure changes nothing and must be recorded as a blocker.

## Private PWA tunnel

In one foreground terminal/session, run:

```bash
export AN3_STAGING_SSH_IDENTITY_FILE=~/an3-codex-staging
export AN3_STAGING_SSH_KNOWN_HOSTS=~/known_hosts
<legacy-checkout>/tools/ssh/open-staging-pwa-tunnel.sh 18092
```

The tunnel listens only on `127.0.0.1:18092`; it has no WAN listener and exits cleanly with Ctrl-C. With it running, execute `<legacy-checkout>/tools/android/smoke-pwa.sh 18092`. That tool removes only its own `adb reverse` mapping.

This control path is staging-only. It does not deploy, restart a service, alter Cloudflare, or access production.
