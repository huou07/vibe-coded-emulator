// Generated from native-offline/shared/native-settings-schema.json; edit the shared model.
package space.an3tocom.offline

/** Canonical definition of every native application and per-core setting. */
object NativeSettingsSchema {
    const val STORE = "an3-native-game"
    const val VERSION = 1
    val systems = listOf("gba", "nds", "3ds", "switch")
    val systemLabels = mapOf(
        "gba" to "GBA",
        "nds" to "NDS",
        "3ds" to "3DS",
        "switch" to "Switch",
    )

    enum class Type { ENUM, INT, BOOL, STRING }

    data class Definition(
        val id: String,
        val label: String,
        val category: String,
        val type: Type,
        val storage: String,
        val values: List<String>,
        val labels: Map<String, String>,
        val min: Int?,
        val max: Int?,
        val default: String?,
        val legacyKeys: List<String>,
        val legacyResolve: String?,
        val restart: String,
        val note: String?,
        val external: Boolean,
    )

    val global: List<Definition> = listOf(
        Definition("volume", "Volume", "audio", Type.INT, "int", emptyList(), emptyMap(), 0, 100, "100", emptyList(), null, "none", null, true),
        Definition("mute", "Mute", "audio", Type.BOOL, "bool", emptyList(), emptyMap(), null, null, "false", emptyList(), null, "none", null, true),
        Definition("latency", "Audio latency", "audio", Type.ENUM, "int", listOf("32", "64", "96", "128"), mapOf("32" to "32 ms", "64" to "64 ms", "96" to "96 ms", "128" to "128 ms"), null, null, "64", emptyList(), null, "none", null, true),
        Definition("quality", "Resampler quality", "audio", Type.ENUM, "string", listOf("low", "medium", "high"), mapOf("low" to "Low", "medium" to "Medium", "high" to "High"), null, null, "medium", emptyList(), null, "none", null, true),
        Definition("autosave-mode", "Auto Save", "emulation", Type.ENUM, "string", listOf("off", "exit", "30", "10", "5"), mapOf("5" to "Every 5 seconds", "10" to "Every 10 seconds", "30" to "Every 30 seconds", "off" to "Off", "exit" to "On game exit"), null, null, null, emptyList(), "native-autosave", "none", null, true),
        Definition("show-fps", "Show FPS", "display", Type.BOOL, "bool", emptyList(), emptyMap(), null, null, "false", emptyList(), null, "none", null, true),
        Definition("start-fullscreen", "Start fullscreen on launch", "display", Type.BOOL, "bool", emptyList(), emptyMap(), null, null, "true", emptyList(), null, "app", null, true),
        Definition("key-map", "Keyboard map", "controls", Type.STRING, "string", emptyList(), emptyMap(), null, null, "{}", emptyList(), null, "none", null, false),
        Definition("controller-server", "Controller server", "network", Type.STRING, "string", emptyList(), emptyMap(), null, null, "", emptyList(), null, "none", null, false)
    )

    val graphics: Map<String, List<Definition>> = mapOf(
        "gba" to listOf(
            Definition("renderer", "Renderer", "graphics", Type.ENUM, "string", listOf("auto", "vulkan", "opengl"), mapOf("auto" to "Auto", "vulkan" to "Vulkan", "opengl" to "OpenGL ES"), null, null, "auto", listOf("renderer"), null, "renderer", "Applies on the next launch. Auto picks the stable backend for each system.", true)
        ),
        "nds" to listOf(
            Definition("renderer", "Renderer", "graphics", Type.ENUM, "string", listOf("auto", "vulkan", "opengl"), mapOf("auto" to "Auto", "vulkan" to "Vulkan", "opengl" to "OpenGL ES"), null, null, "auto", listOf("renderer"), null, "renderer", "Applies on the next launch. Auto picks the stable backend for each system.", true),
            Definition("screen-layout", "Screen layout", "graphics", Type.ENUM, "string", listOf("left-right", "right-left", "top-bottom", "bottom-top", "hybrid-top", "hybrid-bottom", "flipped-hybrid-top", "flipped-hybrid-bottom", "largescreen-top", "largescreen-bottom", "flipped-largescreen-top", "flipped-largescreen-bottom"), mapOf("left-right" to "Left / Right", "right-left" to "Right / Left", "top-bottom" to "Top / Bottom", "bottom-top" to "Bottom / Top", "hybrid-top" to "Hybrid (focus top)", "hybrid-bottom" to "Hybrid (focus bottom)", "flipped-hybrid-top" to "Flipped hybrid (focus top)", "flipped-hybrid-bottom" to "Flipped hybrid (focus bottom)", "largescreen-top" to "Large screen (top)", "largescreen-bottom" to "Large screen (bottom)", "flipped-largescreen-top" to "Flipped large screen (top)", "flipped-largescreen-bottom" to "Flipped large screen (bottom)"), null, null, "left-right", listOf("screen-layout-nds", "nds-layout"), null, "game", "Applies immediately in-game and on the next launch outside the game.", true)
        ),
        "3ds" to listOf(
            Definition("renderer", "Renderer", "graphics", Type.ENUM, "string", listOf("auto", "vulkan", "opengl"), mapOf("auto" to "Auto", "vulkan" to "Vulkan", "opengl" to "OpenGL ES"), null, null, "auto", listOf("renderer"), null, "renderer", "Applies on the next launch. Auto picks the stable backend for each system.", true),
            Definition("screen-layout", "Screen layout", "graphics", Type.ENUM, "string", listOf("left-right", "top-bottom", "single-screen", "large-screen"), mapOf("left-right" to "Side by Side", "top-bottom" to "Top / Bottom", "single-screen" to "Single Screen", "large-screen" to "Large Screen"), null, null, "left-right", listOf("screen-layout-3ds", "nds-layout"), null, "game", "Applies immediately in-game and on the next launch outside the game.", true)
        ),
        "switch" to listOf(
            Definition("renderer", "Renderer", "graphics", Type.ENUM, "string", listOf("auto", "vulkan", "opengl"), mapOf("auto" to "Auto", "vulkan" to "Vulkan", "opengl" to "OpenGL ES"), null, null, "auto", listOf("renderer"), null, "renderer", "Applies on the next launch. Auto picks the stable backend for each system.", true)
        ),
    )

    val emulation: Map<String, List<Definition>> = mapOf(
        "gba" to listOf(),
        "nds" to listOf(),
        "3ds" to listOf(),
        "switch" to listOf()
    )

    val pinnedCoreOptions: Map<String, List<String>> = mapOf(
        "gba" to emptyList(),
        "nds" to listOf("melonds_render_mode", "melonds_screen_layout1", "melonds_number_of_screen_layouts", "melonds_touch_mode"),
        "3ds" to listOf("citra_graphics_api", "citra_use_hw_shader", "citra_use_disk_shader_cache", "citra_layout_option"),
        "switch" to emptyList(),
    )

    // system -> platform -> reason. A missing entry means the system is available.
    val unavailable: Map<String, Map<String, String>> = mapOf(
        "switch" to mapOf(
            "android" to "Nintendo Switch is not supported on Android. Settings are stored but cannot launch here.",
            "ios" to "Nintendo Switch is not supported on iOS.",
        ),
    )

    fun key(id: String, system: String?): String = if (system == null) id else "$id-$system"

    fun definitionsFor(system: String): List<Definition> = graphics[system].orEmpty() + emulation[system].orEmpty()

    fun definition(id: String, system: String?): Definition? =
        if (system == null) global.firstOrNull { it.id == id } else definitionsFor(system).firstOrNull { it.id == id }

    fun isAvailable(platform: String, system: String): Boolean = unavailable[system]?.containsKey(platform) != true

    fun unavailableReason(platform: String, system: String): String? = unavailable[system]?.get(platform)

    fun pinned(system: String): List<String> = pinnedCoreOptions[system].orEmpty()
}
