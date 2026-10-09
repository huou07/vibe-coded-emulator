// Generated from native-offline/shared/native-layout-schema.json; edit the shared schema.
#pragma once
#include <array>
#include <string_view>
namespace an3::native_layouts {
struct Layout { std::string_view id; std::string_view label; std::string_view core_value; };
inline constexpr std::array<Layout, 12> nds = {{ {"left-right", "Left / Right", "left-right"}, {"right-left", "Right / Left", "right-left"}, {"top-bottom", "Top / Bottom", "top-bottom"}, {"bottom-top", "Bottom / Top", "bottom-top"}, {"hybrid-top", "Hybrid (focus top)", "hybrid-top"}, {"hybrid-bottom", "Hybrid (focus bottom)", "hybrid-bottom"}, {"flipped-hybrid-top", "Flipped hybrid (focus top)", "flipped-hybrid-top"}, {"flipped-hybrid-bottom", "Flipped hybrid (focus bottom)", "flipped-hybrid-bottom"}, {"largescreen-top", "Large screen (top)", "largescreen-top"}, {"largescreen-bottom", "Large screen (bottom)", "largescreen-bottom"}, {"flipped-largescreen-top", "Flipped large screen (top)", "flipped-largescreen-top"}, {"flipped-largescreen-bottom", "Flipped large screen (bottom)", "flipped-largescreen-bottom"} }};
inline constexpr std::array<Layout, 4> three_ds = {{ {"left-right", "Side by Side", "side_by_side"}, {"top-bottom", "Top / Bottom", "default"}, {"single-screen", "Single Screen", "single_screen"}, {"large-screen", "Large Screen", "large_screen"} }};
}
