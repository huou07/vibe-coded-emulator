// Generated from native-offline/shared/input-actions-schema.json; edit the shared model.
package space.an3tocom.offline

import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.hypot

/** Canonical input/action contract shared by the in-game overlay and Phone Controller. */
object NativeInputActions {
    const val B = 0
    const val Y = 1
    const val SELECT = 2
    const val START = 3
    const val UP = 4
    const val DOWN = 5
    const val LEFT = 6
    const val RIGHT = 7
    const val A = 8
    const val X = 9
    const val L = 10
    const val R = 11

    val buttonIds: Map<String, Int> = mapOf("B" to 0, "Y" to 1, "SELECT" to 2, "START" to 3, "UP" to 4, "DOWN" to 5, "LEFT" to 6, "RIGHT" to 7, "A" to 8, "X" to 9, "L" to 10, "R" to 11)
    val wireToId: Map<String, Int> = mapOf("b" to 0, "y" to 1, "select" to 2, "start" to 3, "up" to 4, "down" to 5, "left" to 6, "right" to 7, "a" to 8, "x" to 9, "l" to 10, "r" to 11)
    val buttonLabels: Map<String, String> = mapOf("B" to "B", "Y" to "Y", "SELECT" to "Select", "START" to "Start", "UP" to "Up", "DOWN" to "Down", "LEFT" to "Left", "RIGHT" to "Right", "A" to "A", "X" to "X", "L" to "L", "R" to "R")

    val utilityActions: List<String> = listOf("QUICK_SAVE", "QUICK_LOAD", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU")
    val utilityWireToAction: Map<String, String> = mapOf("quick_save" to "QUICK_SAVE", "quick_load" to "QUICK_LOAD", "speed_up" to "SPEED_UP", "speed_down" to "SPEED_DOWN", "open_menu" to "OPEN_MENU")
    val utilityLabels: Map<String, String> = mapOf("QUICK_SAVE" to "Quick Save", "QUICK_LOAD" to "Quick Load", "SPEED_UP" to "Speed Up", "SPEED_DOWN" to "Speed Down", "OPEN_MENU" to "Menu")

    val speeds: List<String> = listOf("0.5", "1", "2", "4", "8")
    val directionalControls: List<String> = listOf("dpad", "joystick", "circular")
    val directionalControlLabels: Map<String, String> = mapOf("dpad" to "D-Pad", "joystick" to "Analog Joystick", "circular" to "Circular D-pad")

    private val sectorIds = listOf("E", "NE", "N", "NW", "W", "SW", "S", "SE")
    private val sectorCenters = listOf(0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)
    private val sectorActions = listOf(setOf("RIGHT"), setOf("UP", "RIGHT"), setOf("UP"), setOf("UP", "LEFT"), setOf("LEFT"), setOf("DOWN", "LEFT"), setOf("DOWN"), setOf("DOWN", "RIGHT"))
    private const val DEADZONE = 0.3
    private const val HYSTERESIS = 6

    data class CircularResult(val actions: Set<String>, val region: String?)

    /**
     * Directional geometry for a pointer at (dx, dy) normalized so one control
     * radius is 1.0. Returns the cardinal/diagonal digital actions; a diagonal
     * is two simultaneous cardinals, never a synthetic button.
     */
    fun circularDirections(dx: Float, dy: Float, previous: String?): CircularResult {
        if (!dx.isFinite() || !dy.isFinite()) return CircularResult(emptySet(), null)
        val radius = hypot(dx.toDouble(), dy.toDouble())
        if (radius < DEADZONE) return CircularResult(emptySet(), null)
        var angle = Math.toDegrees(atan2((-dy).toDouble(), dx.toDouble()))
        if (angle < 0.0) angle += 360.0
        if (previous != null) {
            val index = sectorIds.indexOf(previous)
            if (index >= 0) {
                var distance = abs(angle - sectorCenters[index])
                if (distance > 180.0) distance = 360.0 - distance
                if (distance <= 22.5 + HYSTERESIS) return CircularResult(sectorActions[index], sectorIds[index])
            }
        }
        var best = 0
        var bestDistance = Double.MAX_VALUE
        for (index in sectorIds.indices) {
            var distance = abs(angle - sectorCenters[index])
            if (distance > 180.0) distance = 360.0 - distance
            if (distance < bestDistance) { bestDistance = distance; best = index }
        }
        return CircularResult(sectorActions[best], sectorIds[best])
    }

    /** Pressed cardinal actions for a pointer, preserving the previous region's hysteresis. */
    fun pressedCardinals(actions: Set<String>): Set<Int> =
        actions.mapNotNull { buttonIds[it] }.toSet()
}
