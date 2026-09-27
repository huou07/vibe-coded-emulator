// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NativeInputActionsTest {
    @Test
    fun circularControlMapsCardinalsAndDiagonalsToLocalButtons() {
        assertEquals(setOf("UP"), NativeInputActions.circularDirections(0f, -1f, null).actions)
        assertEquals(setOf("DOWN"), NativeInputActions.circularDirections(0f, 1f, null).actions)
        assertEquals(setOf("LEFT"), NativeInputActions.circularDirections(-1f, 0f, null).actions)
        assertEquals(setOf("RIGHT"), NativeInputActions.circularDirections(1f, 0f, null).actions)
        assertEquals(setOf("UP", "RIGHT"), NativeInputActions.circularDirections(1f, -1f, null).actions)
        assertEquals(setOf("DOWN", "LEFT"), NativeInputActions.circularDirections(-1f, 1f, null).actions)
    }

    @Test
    fun circularControlKeepsItsDeadzoneAndHysteresis() {
        val neutral = NativeInputActions.circularDirections(0.1f, 0.1f, null)
        assertEquals(emptySet<String>(), neutral.actions)
        assertNull(neutral.region)

        val x = Math.sin(Math.toRadians(25.0)).toFloat()
        val y = -Math.cos(Math.toRadians(25.0)).toFloat()
        assertEquals(setOf("UP"), NativeInputActions.circularDirections(x, y, "N").actions)
        assertEquals(setOf("UP", "RIGHT"), NativeInputActions.circularDirections(x, y, null).actions)
    }

    @Test
    fun pressedDirectionsMapToExistingLibretroButtonIds() {
        assertEquals(setOf(NativeInputActions.UP, NativeInputActions.RIGHT),
            NativeInputActions.pressedCardinals(setOf("UP", "RIGHT")))
        assertEquals(4, NativeInputActions.UP)
        assertEquals(8, NativeInputActions.A)
        assertEquals(0, NativeInputActions.B)
    }
}
