// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <optional>
#include <string>

namespace an3 {

// Auto Save is one unambiguous mode: off | exit | <seconds>. The shared player
// UI offers off/exit/30/10/5; any positive numeric token is still accepted so an
// install migrated from the earlier enabled+interval keys keeps its interval.
struct AutoSaveSettings {
    bool enabled = false;
    bool on_exit = false;
    unsigned interval = 60;
};

inline std::optional<AutoSaveSettings> parse_auto_save_mode(const std::string& value) {
    AutoSaveSettings settings;
    if (value.empty() || value == "off") return settings;
    if (value == "exit") { settings.on_exit = true; return settings; }
    if (value.size() > 6) return std::nullopt;
    unsigned seconds = 0;
    for (char c : value) {
        if (c < '0' || c > '9') return std::nullopt;
        seconds = seconds * 10 + unsigned(c - '0');
    }
    if (seconds < 1 || seconds > 3600) return std::nullopt;
    settings.enabled = true;
    settings.interval = seconds;
    return settings;
}

} // namespace an3
