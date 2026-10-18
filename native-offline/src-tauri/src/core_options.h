// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

// Compatibility include for the original macOS host. The libretro option ABI
// and registry live with the portable host so Android, Linux and Windows use
// the same definitions rather than a desktop-private copy.
#include "../../native-runtime/core/core_options.h"
