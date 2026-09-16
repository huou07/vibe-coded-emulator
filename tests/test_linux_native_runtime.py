# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression contracts for the real portable Linux native package.

The Debian release job compiles and runs these adapters.  These lightweight
checks ensure a later UI-only change cannot silently restore the former
"blocked" browser-package placeholder or put a GPU-frame core on a readback
path.
"""

from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "native-offline/native-runtime/platform/linux"
BUILD = (ROOT / "native-offline/scripts/build-linux-staging.sh").read_text(encoding="utf-8")
FLATPAK_INSTALL_VERIFY = (ROOT / "native-offline/scripts/verify-flatpak-install.sh").read_text(encoding="utf-8")
RUNTIME = (LINUX / "linux_runtime.cpp").read_text(encoding="utf-8")
CONTROLS = (LINUX / "linux_controls.cpp").read_text(encoding="utf-8")
GL = (LINUX / "sdl_gl_backend.cpp").read_text(encoding="utf-8")
AUDIO = (LINUX / "sdl_audio_backend.cpp").read_text(encoding="utf-8")
SURFACE = (LINUX / "sdl_window_surface.h").read_text(encoding="utf-8")
FLATPAK = (ROOT / "native-offline/flatpak/space.an3tocom.offline.yml").read_text(encoding="utf-8")
VULKAN = (ROOT / "native-offline/native-runtime/video/vulkan/vulkan_backend.cpp").read_text(encoding="utf-8")


class LinuxNativeRuntimeTests(unittest.TestCase):
    def test_build_entrypoint_creates_real_deb_and_flatpak(self):
        self.assertNotIn("LINUX_NATIVE_RUNTIME=BLOCKED", BUILD)
        for required in ("libretro_host.cpp", "vulkan_backend.cpp", "linux_runtime.cpp",
                         "linux_controls.cpp", "sdl_audio_backend.cpp", "sdl_gl_backend.cpp",
                         "bundle-linux-runtime.mjs", "npm run tauri -- build --bundles deb",
                         "flatpak-builder", "fetch-linux-gba-nds-libretro.mjs"):
            self.assertIn(required, BUILD)

        self.assertIn('cp -a deb-extract/usr/lib/. /app/lib/', FLATPAK)
        self.assertNotIn('cp -a deb-extract/usr/lib/. /app/lib/an3-offline-native/', FLATPAK)
        self.assertIn('--runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo', BUILD)
        self.assertIn('flatpak_deb_path="$root/releases/$deb_name"', BUILD)
        self.assertIn('The Flatpak source DEB is stale or differs from the selected staged DEB.', BUILD)

    def test_flatpak_bundle_is_clean_installable_without_a_builder_runtime_cache(self):
        self.assertIn('flatpak --user install --noninteractive "$bundle"', FLATPAK_INSTALL_VERIFY)
        self.assertIn('flatpak --user info "$app_id"', FLATPAK_INSTALL_VERIFY)
        self.assertIn('flatpak run --command=an3-native-player "$app_id" --help', FLATPAK_INSTALL_VERIFY)
        self.assertIn('AN3_FLATPAK_SMOKE_ROM', FLATPAK_INSTALL_VERIFY)
        self.assertIn('FLATPAK_RUNTIME_SMOKE=PASS', FLATPAK_INSTALL_VERIFY)

    def test_linux_surface_audio_and_file_picker_are_native(self):
        self.assertIn("SDL_Vulkan_CreateSurface", SURFACE)
        self.assertIn("SDL_WINDOW_VULKAN", SURFACE)
        self.assertIn("SDL_WINDOW_OPENGL", SURFACE)
        self.assertIn("SDL_OpenAudioDevice", AUDIO)
        self.assertIn("queue_limit_frames_", AUDIO)
        self.assertIn("GTK_FILE_CHOOSER_ACTION_OPEN", RUNTIME)
        self.assertIn("org.freedesktop.portal.Desktop", FLATPAK)
        self.assertNotIn("WebView", RUNTIME)
        self.assertNotIn("OffscreenCanvas", RUNTIME)
        self.assertIn('std::strcmp(path, "libvulkan.so")', VULKAN)
        self.assertIn('dlopen("libvulkan.so.1", RTLD_NOW | RTLD_LOCAL)', VULKAN)

    def test_3ds_is_vulkan_only_and_software_cores_can_select_gl(self):
        self.assertIn('system == "3ds" && options.renderer == "opengl"', RUNTIME)
        self.assertIn('options.renderer == "auto" || options.renderer == "opengl"', RUNTIME)
        self.assertIn("VulkanHardwareBackend", RUNTIME)
        self.assertIn("LinuxSdlGlBackend", RUNTIME)
        self.assertIn("prohibited GPU readback", RUNTIME)
        self.assertIn("hardware-frame: desktop OpenGL fallback cannot consume Vulkan images", GL)

    def test_gl_reuses_resources_and_has_no_finish_or_readback_hot_path(self):
        self.assertIn("std::array<std::vector<uint8_t>, 2> staging", GL)
        self.assertIn("if (impl_->texture_width != width || impl_->texture_height != height)", GL)
        self.assertIn("glTexSubImage2D", GL)
        self.assertNotIn("glFinish", GL)
        self.assertNotIn("glReadPixels", GL)
        self.assertLess(GL.index("SDL_GL_SetAttribute"), GL.index("surface->recreate_for_opengl"))

    def test_f1_uses_the_shared_layout_state_and_persists_the_live_choice(self):
        self.assertIn("host.set_screen_layout(value, detail)", RUNTIME)
        self.assertIn("std::ofstream output(layout_file, std::ios::trunc)", RUNTIME)
        self.assertIn("output << options.layout", RUNTIME)
        self.assertIn("next_supported_layout(options.system, options.layout)", RUNTIME)
        self.assertIn("is_supported_layout(options.system, options.layout)", RUNTIME)
        self.assertIn("set_touch(host.input(), options.system, options.layout", RUNTIME)

    def test_linux_toolbar_save_exposes_ten_slots_and_menu_owns_pointer(self):
        self.assertIn("void show_save_menu()", CONTROLS)
        self.assertIn("add_slots(std::string(player_ui::toolbar_quick_save), true)", CONTROLS)
        self.assertIn("slot <= 10", CONTROLS)
        # An open controls panel owns pointer input; a menu tap must not also
        # drive the emulated touchscreen.
        self.assertIn("controls && controls->visible()", RUNTIME)
        self.assertIn("cancel_pointer()", RUNTIME)

    def test_linux_control_panel_reuses_native_state_and_matches_the_desktop_menu_surface(self):
        model = json.loads((ROOT / "native-offline/shared/player-ui.json").read_text())
        self.assertEqual(model["tabs"], ["General", "Graphics", "Audio", "Keyboard", "Controller", "Emulation", "Save States", "Diagnostics", "About"])
        self.assertIn("append_page(player_ui::tabs[i]", CONTROLS)
        for action in ("Toggle fullscreen", "Return to library", "x4", "x8",
                       "Export Save State…", "Import Save State…", "Release held native input"):
            self.assertIn(action, CONTROLS)
        self.assertIn("player_ui::auto_save_label", CONTROLS)
        self.assertIn("player_ui::auto_save_titles", CONTROLS)
        self.assertIn("player_ui::auto_save_tokens", CONTROLS)
        self.assertNotIn("Auto Save (state snapshot)", CONTROLS)
        for speed in ("player_ui::toolbar_speed[0]", "player_ui::toolbar_speed[1]", "player_ui::toolbar_speed[2]"):
            self.assertIn(speed, CONTROLS)
        self.assertIn("host_.core_options()", CONTROLS)
        self.assertIn("host_.set_core_option", CONTROLS)
        self.assertIn("host_.save_state", CONTROLS)
        self.assertIn("host_.load_state", CONTROLS)
        self.assertIn("callbacks_.set_layout", CONTROLS)
        for forbidden in ("WebView", "OffscreenCanvas", "glReadPixels", "glFinish"):
            self.assertNotIn(forbidden, CONTROLS)

    def test_linux_native_autosave_uses_the_single_shared_mode(self):
        self.assertIn('#include "../../core/auto_save_mode.h"', RUNTIME)
        self.assertIn("set_auto_save_mode", RUNTIME)
        self.assertIn("parse_auto_save_mode", RUNTIME)
        self.assertIn("auto_save.enabled", RUNTIME)
        self.assertIn("auto_save.on_exit", RUNTIME)
        self.assertNotIn("set_autosave_interval", RUNTIME)
        self.assertNotIn("autosave_interval", RUNTIME)
        # The shared model is the single source for the offered mode tokens.
        native = (ROOT / "native-offline/shared/generated/player_ui.h").read_text(encoding="utf-8")
        for token in ('"off"', '"exit"', '"30"', '"10"', '"5"'):
            self.assertIn(token, native)


if __name__ == "__main__":
    unittest.main()
