// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace an3::input_contract {

// Libretro's relative mouse contract is screen-facing: right/down are
// positive. AppKit's NSEvent delta values are passed through this boundary
// exactly once; no core, layout, renderer, or cursor overlay is allowed to
// apply another sign change.
inline int16_t relative_axis(float physical_delta, float scale = 1.0f) {
    const int value = static_cast<int>(std::lround(physical_delta * scale));
    return static_cast<int16_t>(std::clamp(value, -32767, 32767));
}

inline int16_t absolute_axis(float coordinate, float extent) {
    if (extent <= 0.0f) return 0;
    const float normalized = std::clamp(coordinate / extent, 0.0f, 1.0f);
    return static_cast<int16_t>(std::lround(normalized * 65534.0f) - 32767);
}

} // namespace an3::input_contract
