// Generated from native-offline/shared/player-ui.json; edit the shared model.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <string_view>
namespace an3::player_ui {
inline constexpr std::array<std::string_view, 9> tabs = {"General", "Graphics", "Audio", "Keyboard", "Controller", "Emulation", "Save States", "Diagnostics", "About"};
inline constexpr std::string_view toolbar_menu = "Menu", toolbar_pad = "Pad", toolbar_layout = "Layout", toolbar_save = "Save", toolbar_quick_save = "Quick Save", toolbar_quick_load = "Quick Load", toolbar_cursor_lock = "Lock cursor";
inline constexpr std::array<std::string_view, 3> toolbar_speed = {"0.5x", "1x", "x2"};
inline constexpr std::string_view auto_save_label = "Auto Save";
inline constexpr std::array<std::string_view, 5> auto_save_titles = {"Off", "On game exit", "Every 30 seconds", "Every 10 seconds", "Every 5 seconds"};
inline constexpr std::array<std::string_view, 5> auto_save_tokens = {"off", "exit", "30", "10", "5"};
inline constexpr double stick_diameter = 108.0, thumb_radius_ratio = 0.3, travel_ratio = 0.6111111111111112, deadzone = 0.15;
inline constexpr double panel_width = 820.0, panel_height = 620.0, panel_edge = 12.0;
struct Axis { double x = 0, y = 0; };
inline Axis normalize(double x, double y) {
    if (!std::isfinite(x) || !std::isfinite(y)) return {};
    const double length = std::hypot(x, y);
    if (length < deadzone) return {};
    const double scale = std::max(1.0, length);
    return {x / scale, y / scale};
}
}
