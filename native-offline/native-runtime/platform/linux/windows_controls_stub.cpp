// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "linux_controls.h"

namespace an3 {

class LinuxControlPanel::Impl {};

LinuxControlPanel::LinuxControlPanel(NativeCoreHost&, LinuxSdlAudioBackend&,
                                     std::string, LinuxControlCallbacks)
    : impl_(std::make_unique<Impl>()) {}

LinuxControlPanel::~LinuxControlPanel() = default;

bool LinuxControlPanel::initialize(std::string& error) {
    error = "Windows native controls are provided by the application shell.";
    return false;
}

void LinuxControlPanel::pump() {}
void LinuxControlPanel::show() {}
void LinuxControlPanel::hide() {}
void LinuxControlPanel::toggle() {}
void LinuxControlPanel::show_pad() {}
bool LinuxControlPanel::visible() const { return false; }

} // namespace an3
