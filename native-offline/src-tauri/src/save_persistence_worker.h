// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

// Compatibility include for the accepted macOS host. The implementation is
// shared with the portable Android/Linux/Windows runtime so the two paths do
// not grow divergent save durability or queue semantics.
#include "../../native-runtime/core/save_persistence_worker.h"
