// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import java.util.ArrayDeque

/** Small ordered event queue plus one replaceable latest-motion slot. */
internal class ControllerSendQueue<T>(
    private val maxEvents: Int,
    private val sequenceOf: (T) -> Long,
) {
    private val events = ArrayDeque<T>()
    private var latestMotion: T? = null

    @Synchronized
    fun offer(item: T, motion: Boolean): Boolean {
        if (motion) {
            latestMotion = item
            return true
        }
        if (events.size >= maxEvents) return false
        events.addLast(item)
        return true
    }

    @Synchronized
    fun poll(): T? {
        if (events.isNotEmpty()) {
            val newestEvent = events.peekLast() ?: return events.removeFirst()
            val newestEventSequence = sequenceOf(newestEvent)
            if (latestMotion?.let { sequenceOf(it) < newestEventSequence } == true) latestMotion = null
            return events.removeFirst()
        }
        val next = latestMotion
        latestMotion = null
        return next
    }

    @Synchronized
    fun clear() {
        events.clear()
        latestMotion = null
    }

    @Synchronized
    fun pendingEvents(): Int = events.size

    @Synchronized
    fun hasMotion(): Boolean = latestMotion != null
}
