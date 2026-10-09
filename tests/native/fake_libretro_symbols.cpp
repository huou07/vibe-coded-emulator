#include "../../native-offline/native-runtime/core/vendor/libretro.h"

// The direct-frame fixture predates NativeCoreHost's complete symbol loader.
// Keep the fixture tiny by supplying the otherwise-unused ABI entry points in
// this companion translation unit.
extern "C" {

void retro_reset() {}
void retro_cheat_reset() {}
void retro_cheat_set(unsigned, bool, const char*) {}
bool retro_load_game_special(unsigned, const retro_game_info*, size_t) { return false; }
unsigned retro_get_region() { return RETRO_REGION_NTSC; }
void* retro_get_memory_data(unsigned) { return nullptr; }
size_t retro_get_memory_size(unsigned) { return 0; }

} // extern "C"
