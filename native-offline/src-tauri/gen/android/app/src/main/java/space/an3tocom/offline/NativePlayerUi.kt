// Generated from native-offline/shared/player-ui.json; edit the shared model.
package space.an3tocom.offline
import kotlin.math.hypot
import kotlin.math.max
object NativePlayerUi {
    val tabs = listOf("General", "Graphics", "Audio", "Keyboard", "Controller", "Emulation", "Save States", "Diagnostics", "About")
    const val MENU_LABEL = "Menu"
    const val PAD_LABEL = "Pad"
    const val LAYOUT_LABEL = "Layout"
    const val SAVE_LABEL = "Save"
    const val QUICK_SAVE_LABEL = "Quick Save"
    const val QUICK_LOAD_LABEL = "Quick Load"
    const val CURSOR_LOCK_LABEL = "Lock cursor"
    val speedLabels = listOf("0.5x", "1x", "x2")
    const val AUTO_SAVE_LABEL = "Auto Save"
    val autoSaveTitles = listOf("Off", "On game exit", "Every 30 seconds", "Every 10 seconds", "Every 5 seconds")
    val autoSaveTokens = listOf("off", "exit", "30", "10", "5")
    const val CONTROL_COLOR = -1206643692
    const val BORDER_COLOR = -2130706433
    const val THUMB_COLOR = -637534209
    const val TEXT_COLOR = -1
    const val THUMB_RADIUS_RATIO = 0.3f
    const val TRAVEL_RATIO = 0.6111111111111112f
    const val DEADZONE = 0.15f
    const val PANEL_WIDTH = 820
    const val PANEL_HEIGHT = 620
    data class Axis(val x: Float = 0f, val y: Float = 0f)
    fun normalize(x: Float, y: Float): Axis {
        if (!x.isFinite() || !y.isFinite()) return Axis()
        val length = hypot(x, y)
        if (length < DEADZONE) return Axis()
        val scale = max(1f, length)
        return Axis(x / scale, y / scale)
    }
}
