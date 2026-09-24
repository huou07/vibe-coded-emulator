# Security policy

## Reporting a vulnerability

Please report security issues **privately**. Use GitHub's private vulnerability
reporting on this repository (Security tab → "Report a vulnerability") if it is
available. If it is not, open a minimal issue asking for a private contact
channel **without including any details of the vulnerability**.

Do not paste secrets, tokens, or exploit details into a public issue.

Please include, where possible:

- Affected component and version.
- Steps to reproduce.
- Impact and attack surface.
- Any suggested fix.

We aim to acknowledge reports promptly and will credit reporters who want to be
credited.

## Scope

The security-relevant surfaces are:

- The Python web app (`app.py` and the shared modules) and its HTTP routes.
- The web player (`static/`) and its Content-Security-Policy handling.
- The native shells (`native-offline/`) and the Eden bridge (`native/eden-bridge/`).
- The Google Drive synchronisation and LAN transfer code paths.

## Secrets and personal data

This repository must never contain real credentials, ROMs, firmware, encryption
keys, or personal data. If you find any of those committed, report it privately
and immediately.

## Supported versions

Security fixes are applied to the latest release and the default branch.
