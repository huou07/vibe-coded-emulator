import { readFile, mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const model = JSON.parse(await readFile(resolve(root, "shared/player-ui.json"), "utf8"));
const j = model.joystick, p = model.panel, t = model.toolbar, a = model.autoSave;
if (!(j.deadzone >= 0 && j.deadzone < 1 && j.travelRatio > 0 && j.travelRatio + j.thumbRadiusRatio < 1)) throw new Error("Invalid joystick geometry");
if (!t || ![t.menu, t.pad, t.layout, t.save, t.quickSave, t.quickLoad, t.cursorLock].every(value => typeof value === "string" && value) || !Array.isArray(t.speed) || t.speed.length !== 3 || !t.speed.every(value => typeof value === "string" && value)) throw new Error("Invalid shared toolbar model");
if (!a || typeof a.label !== "string" || !a.label || !Array.isArray(a.titles) || !Array.isArray(a.tokens) || a.titles.length === 0 || a.titles.length !== a.tokens.length || !a.titles.every(value => typeof value === "string" && value) || !a.tokens.every(value => typeof value === "string" && value)) throw new Error("Invalid shared auto-save model");
const signedColor = value => {
  const numeric = Number.parseInt(value.replace(/^#/, ""), 16);
  if (!Number.isInteger(numeric)) throw new Error(`Invalid player UI color: ${value}`);
  return numeric > 0x7fffffff ? numeric - 0x100000000 : numeric;
};
const banner = "// Generated from native-offline/shared/player-ui.json; edit the shared model.\n";
const outputs = new Map([
  [resolve(root, "shared/generated/player_ui.h"), `${banner}#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <string_view>
namespace an3::player_ui {
inline constexpr std::array<std::string_view, ${model.tabs.length}> tabs = {${model.tabs.map(JSON.stringify).join(", ")}};
inline constexpr std::string_view toolbar_menu = ${JSON.stringify(t.menu)}, toolbar_pad = ${JSON.stringify(t.pad)}, toolbar_layout = ${JSON.stringify(t.layout)}, toolbar_save = ${JSON.stringify(t.save)}, toolbar_quick_save = ${JSON.stringify(t.quickSave)}, toolbar_quick_load = ${JSON.stringify(t.quickLoad)}, toolbar_cursor_lock = ${JSON.stringify(t.cursorLock)};
inline constexpr std::array<std::string_view, ${t.speed.length}> toolbar_speed = {${t.speed.map(JSON.stringify).join(", ")}};
inline constexpr std::string_view auto_save_label = ${JSON.stringify(a.label)};
inline constexpr std::array<std::string_view, ${a.titles.length}> auto_save_titles = {${a.titles.map(JSON.stringify).join(", ")}};
inline constexpr std::array<std::string_view, ${a.tokens.length}> auto_save_tokens = {${a.tokens.map(JSON.stringify).join(", ")}};
inline constexpr double stick_diameter = ${j.diameter}.0, thumb_radius_ratio = ${j.thumbRadiusRatio}, travel_ratio = ${j.travelRatio}, deadzone = ${j.deadzone};
inline constexpr double panel_width = ${p.maxWidth}.0, panel_height = ${p.maxHeight}.0, panel_edge = ${p.edge}.0;
struct Axis { double x = 0, y = 0; };
inline Axis normalize(double x, double y) {
    if (!std::isfinite(x) || !std::isfinite(y)) return {};
    const double length = std::hypot(x, y);
    if (length < deadzone) return {};
    const double scale = std::max(1.0, length);
    return {x / scale, y / scale};
}
}
`],
  [resolve(root, "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativePlayerUi.kt"), `${banner}package space.an3tocom.offline
import kotlin.math.hypot
import kotlin.math.max
object NativePlayerUi {
    val tabs = listOf(${model.tabs.map(JSON.stringify).join(", ")})
    const val MENU_LABEL = ${JSON.stringify(t.menu)}
    const val PAD_LABEL = ${JSON.stringify(t.pad)}
    const val LAYOUT_LABEL = ${JSON.stringify(t.layout)}
    const val SAVE_LABEL = ${JSON.stringify(t.save)}
    const val QUICK_SAVE_LABEL = ${JSON.stringify(t.quickSave)}
    const val QUICK_LOAD_LABEL = ${JSON.stringify(t.quickLoad)}
    const val CURSOR_LOCK_LABEL = ${JSON.stringify(t.cursorLock)}
    val speedLabels = listOf(${t.speed.map(JSON.stringify).join(", ")})
    const val AUTO_SAVE_LABEL = ${JSON.stringify(a.label)}
    val autoSaveTitles = listOf(${a.titles.map(JSON.stringify).join(", ")})
    val autoSaveTokens = listOf(${a.tokens.map(JSON.stringify).join(", ")})
    const val CONTROL_COLOR = ${signedColor(model.colors.control)}
    const val BORDER_COLOR = ${signedColor(model.colors.border)}
    const val THUMB_COLOR = ${signedColor(model.colors.thumb)}
    const val TEXT_COLOR = ${signedColor(model.colors.text)}
    const val THUMB_RADIUS_RATIO = ${j.thumbRadiusRatio}f
    const val TRAVEL_RATIO = ${j.travelRatio}f
    const val DEADZONE = ${j.deadzone}f
    const val PANEL_WIDTH = ${p.maxWidth}
    const val PANEL_HEIGHT = ${p.maxHeight}
    data class Axis(val x: Float = 0f, val y: Float = 0f)
    fun normalize(x: Float, y: Float): Axis {
        if (!x.isFinite() || !y.isFinite()) return Axis()
        val length = hypot(x, y)
        if (length < DEADZONE) return Axis()
        val scale = max(1f, length)
        return Axis(x / scale, y / scale)
    }
}
`],
  [resolve(root, "../static/player-ui.js"), `${banner}(function(root) {
  const model = ${JSON.stringify(model)};
  function normalize(x, y) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return {x:0,y:0};
    const length = Math.hypot(x,y);
    if (length < model.joystick.deadzone) return {x:0,y:0};
    const scale = Math.max(1,length);
    return {x:x/scale,y:y/scale};
  }
  const api = Object.freeze({model, normalize});
  if (typeof module === "object" && module.exports) module.exports = api;
  root.AN3PlayerUI = api;
})(typeof globalThis === "object" ? globalThis : this);
`],
]);

// The multi-screen layout list is generated from its own schema so the macOS and
// Linux adapters share one source of truth with Android (which reads the JSON
// directly). `id` is the persisted preference; `core_value` is the exact token
// the libretro core accepts.
const layouts = JSON.parse(await readFile(resolve(root, "shared/native-layout-schema.json"), "utf8"));
if (layouts.version !== 2 || !layouts.systems?.nds?.length || !layouts.systems?.["3ds"]?.length) throw new Error("Invalid native layout schema");
const layoutEntries = list => list.map(item => {
  if (!item.id || !item.label || !item.coreOption || !item.coreValue) throw new Error(`Invalid native layout entry: ${JSON.stringify(item)}`);
  return `{"${item.id}", "${item.label}", "${item.coreValue}"}`;
});
const layoutArray = (name, list) => `inline constexpr std::array<Layout, ${list.length}> ${name} = {{ ${layoutEntries(list).join(", ")} }};`;
outputs.set(resolve(root, "shared/generated/native_layouts.h"), `// Generated from native-offline/shared/native-layout-schema.json; edit the shared schema.
#pragma once
#include <array>
#include <string_view>
namespace an3::native_layouts {
struct Layout { std::string_view id; std::string_view label; std::string_view core_value; };
${layoutArray("nds", layouts.systems.nds)}
${layoutArray("three_ds", layouts.systems["3ds"])}
}
`);
for (const [path, content] of outputs) {
  let existing; try { existing = await readFile(path, "utf8"); } catch {}
  if (existing === content) continue;
  if (process.argv.includes("--check")) throw new Error(`Generated player UI drift: ${path}`);
  await mkdir(dirname(path), {recursive: true});
  await writeFile(path, content);
}
