#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This script is retired. It packaged only app.py/static and would install an
# app.py that imports netcode/sync_engine/qrcodegen without those modules,
# taking production down.
#
# Use the reviewed production release path instead:
#
#   AN3_PRODUCTION_APPROVED=1 ./deploy-production.sh
#
set -euo pipefail
printf 'deploy.sh is retired. Use: AN3_PRODUCTION_APPROVED=1 ./deploy-production.sh\n' >&2
exit 2
