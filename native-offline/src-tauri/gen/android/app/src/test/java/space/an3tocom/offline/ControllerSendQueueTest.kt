// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ControllerSendQueueTest {
    private data class Frame(val sequence: Long, val label: String)

    private fun queue(limit: Int = 4) = ControllerSendQueue<Frame>(limit) { it.sequence }

    @Test
    fun motionIsReplaceableAndConvergesToLatestSequence() {
        val queue = queue()
        assertTrue(queue.offer(Frame(1, "move-1"), motion = true))
        assertTrue(queue.offer(Frame(2, "move-2"), motion = true))
        assertTrue(queue.offer(Frame(3, "move-3"), motion = true))
        assertEquals("move-3", queue.poll()?.label)
        assertNull(queue.poll())
    }

    @Test
    fun buttonAndTouchEdgesRemainOrderedWhileOldMotionIsDiscarded() {
        val queue = queue()
        queue.offer(Frame(1, "touch-down"), motion = false)
        queue.offer(Frame(2, "touch-move"), motion = true)
        queue.offer(Frame(3, "touch-up"), motion = false)
        queue.offer(Frame(4, "button-down"), motion = false)
        queue.offer(Frame(5, "button-up"), motion = false)

        assertEquals("touch-down", queue.poll()?.label)
        assertEquals("touch-up", queue.poll()?.label)
        assertEquals("button-down", queue.poll()?.label)
        assertEquals("button-up", queue.poll()?.label)
        assertNull(queue.poll())
    }

    @Test
    fun utilityEventsShareOrderedBoundedQueueAndOverflowIsExplicit() {
        val queue = queue(limit = 2)
        assertTrue(queue.offer(Frame(1, "quick-save"), motion = false))
        assertTrue(queue.offer(Frame(2, "open-menu"), motion = false))
        assertFalse(queue.offer(Frame(3, "quick-load"), motion = false))
        assertEquals(2, queue.pendingEvents())
        assertEquals("quick-save", queue.poll()?.label)
        assertEquals("open-menu", queue.poll()?.label)
    }

    @Test
    fun newerMotionFollowsEarlierEventsWithoutSequenceReordering() {
        val queue = queue()
        queue.offer(Frame(1, "button-down"), motion = false)
        queue.offer(Frame(2, "move"), motion = true)
        assertEquals("button-down", queue.poll()?.label)
        assertEquals("move", queue.poll()?.label)
        assertNull(queue.poll())
    }

    @Test
    fun utilityCompletionRequiresValidCommandIdentityActionAndSlot() {
        val result = controllerUtilityResult(
            "native-session-4", "quick_save", 10, true, "Quick save complete.",
        )
        assertEquals(
            ControllerUtilityResult("native-session-4", "QUICK_SAVE", 10, true, "Quick save complete."),
            result,
        )
        assertNull(controllerUtilityResult("", "QUICK_SAVE", 1, true, "ok"))
        assertNull(controllerUtilityResult("session\n1", "QUICK_SAVE", 1, true, "ok"))
        assertNull(controllerUtilityResult("session-1", "UNSUPPORTED", 1, false, "no"))
        assertNull(controllerUtilityResult("session-1", "QUICK_LOAD", 11, false, "no"))
        assertNull(controllerUtilityResult("session-1", "QUICK_SAVE", 1, false, "x".repeat(257)))
    }

}
