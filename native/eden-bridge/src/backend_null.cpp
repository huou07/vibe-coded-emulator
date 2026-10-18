/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Fallback backend used when the bridge is built without Eden. It keeps the ABI
 * fully usable (lifecycle, validation, error reporting) and fails every
 * emulation operation with a clear UNAVAILABLE status, so no Switch
 * functionality is ever faked.
 */
#include "an3_eden_internal.h"

namespace {

using an3::eden::Backend;

an3_eden_status null_initialize(an3_eden_core* core, const char*, const char*) {
    an3::eden::set_error(core,
                         "This build has no Eden backend. Rebuild with -DAN3_EDEN_ENABLED=ON "
                         "and a configured Eden checkout.");
    return AN3_EDEN_ERR_UNAVAILABLE;
}

an3_eden_status null_unavailable(an3_eden_core* core) {
    an3::eden::set_error(core, "Eden backend unavailable");
    return AN3_EDEN_ERR_UNAVAILABLE;
}

an3_eden_status null_load(an3_eden_core* core, const char*) { return null_unavailable(core); }
an3_eden_status null_start(an3_eden_core* core) { return null_unavailable(core); }
an3_eden_status null_pause(an3_eden_core* core, int) { return null_unavailable(core); }
an3_eden_status null_run_frame(an3_eden_core* core, an3_eden_frame_callback, void*) {
    return null_unavailable(core);
}
an3_eden_status null_submit_button(an3_eden_core* core, uint32_t, uint32_t, int) {
    return null_unavailable(core);
}
an3_eden_status null_submit_analog(an3_eden_core* core, uint32_t, uint32_t, int16_t, int16_t) {
    return null_unavailable(core);
}
an3_eden_status null_get_button(an3_eden_core* core, uint32_t, uint32_t, int*) {
    return null_unavailable(core);
}
an3_eden_status null_get_analog(an3_eden_core* core, uint32_t, uint32_t, int16_t*, int16_t*) {
    return null_unavailable(core);
}
an3_eden_status null_save_data(an3_eden_core* core, const char*) { return null_unavailable(core); }
an3_eden_status null_get_save_dir(an3_eden_core* core, char*, uint32_t) {
    return null_unavailable(core);
}
an3_eden_status null_get_audio_info(an3_eden_core* core, an3_eden_audio_info*) {
    return null_unavailable(core);
}
an3_eden_status null_stop(an3_eden_core*) { return AN3_EDEN_OK; }
an3_eden_status null_shutdown(an3_eden_core*) { return AN3_EDEN_OK; }

const Backend kNullBackend{
    "null",         null_initialize,  null_load,          null_start,
    null_pause,     null_run_frame,   null_submit_button, null_submit_analog,
    null_get_button, null_get_analog, null_save_data,     null_get_save_dir,
    null_get_audio_info, null_stop,   null_shutdown,
};

}  // namespace

const an3::eden::Backend& an3::eden::active_backend() {
    return kNullBackend;
}
