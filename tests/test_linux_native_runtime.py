# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression contracts for the real portable Linux native package.

The Debian release job compiles and runs these adapters.  These lightweight
checks ensure a later UI-only change cannot silently restore the former
"blocked" browser-package placeholder or put a GPU-frame core on a readback
path.
"""

from pathlib import Path
import hashlib
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "native-offline/native-runtime/platform/linux"
BUILD = (ROOT / "native-offline/scripts/build-linux-staging.sh").read_text(encoding="utf-8")
FETCH_LINUX_CORES = (ROOT / "native-offline/scripts/fetch-linux-gba-nds-libretro.mjs").read_text(encoding="utf-8")
LINUX_CORE_MANIFEST = ROOT / "native-offline/vendor/libretro/linux-x86_64/manifest.json"
BUNDLED_CORE_MANIFEST = ROOT / "native-offline/vendor/runtime/linux-x86_64/libretro/manifest.json"
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

    def test_prepare_web_names_the_runtime_source_it_needs(self):
        """A missing runtime source must fail with the boundary named.

        `latest/data-v2/*` (the repaired Azahar runtime) is published only by a
        seeded local runtime source, never by the public EmulatorJS CDN. A bare
        `TypeError: fetch failed` reads like a broken build host, so the failure
        must name the asset, the origin, the cache and `AN3_OFFLINE_RUNTIME_SOURCE`.
        """
        prepare_web = (ROOT / "native-offline/scripts/prepare-web.mjs").read_text(encoding="utf-8")
        self.assertIn("AN3_OFFLINE_RUNTIME_SOURCE", prepare_web)
        self.assertIn("AN3_DEPENDENCY_CACHE", prepare_web)
        self.assertIn("comes from a seeded local runtime source", prepare_web)
        # The frozen lock still guards every asset, including the seeded ones.
        self.assertIn("differs from the frozen dependency lock", prepare_web)
        self.assertIn("Frozen dependency cache is missing or corrupt", prepare_web)

    def test_linux_core_pins_describe_the_cores_the_repository_ships(self):
        """The Linux build must reuse the verified cores, not chase a mutable nightly.

        `fetch-linux-gba-nds-libretro.mjs` downloads from a rolling buildbot
        `latest` URL and verifies both the archive and the unpacked core. Pins
        that describe different bytes than the tracked vendor tree make the DEB
        lane fail closed on every fresh run (the 2026-10-08 refresh pinned
        nightly-20261007 while the repository shipped nightly-20260911), so the
        pins must equal the tracked manifest and the core actually bundled into
        the runtime.
        """
        if not LINUX_CORE_MANIFEST.exists():
            self.skipTest("vendored Linux core manifest is not present in this checkout")
        pinned = {core["coreName"]: core for core in json.loads(LINUX_CORE_MANIFEST.read_text(encoding="utf-8"))["cores"]}
        self.assertIn("mgba_libretro.so", pinned)
        self.assertIn("melondsds_libretro.so", pinned)

        for core_name in ("mgba_libretro.so", "melondsds_libretro.so"):
            core = pinned[core_name]
            self.assertIn(core["coreSha256"], FETCH_LINUX_CORES, f"{core_name} core pin drifted from the build script")
            self.assertIn(core["archiveSha256"], FETCH_LINUX_CORES, f"{core_name} archive pin drifted from the build script")
            self.assertIn(core["version"], FETCH_LINUX_CORES, f"{core_name} version pin drifted from the build script")

            staged = ROOT / f"native-offline/vendor/libretro/linux-x86_64/{core_name}"
            if staged.exists():
                self.assertEqual(
                    hashlib.sha256(staged.read_bytes()).hexdigest(),
                    core["coreSha256"],
                    f"staged {core_name} does not match its pinned manifest hash",
                )

        if BUNDLED_CORE_MANIFEST.exists():
            bundled = {core["coreName"]: core for core in json.loads(BUNDLED_CORE_MANIFEST.read_text(encoding="utf-8"))["cores"]}
            for core_name in ("mgba_libretro.so", "melondsds_libretro.so"):
                self.assertEqual(
                    bundled[core_name]["coreSha256"],
                    pinned[core_name]["coreSha256"],
                    f"the bundled runtime ships a different {core_name} than the build pins",
                )

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
