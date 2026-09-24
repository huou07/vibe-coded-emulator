// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.content.Context
import android.net.wifi.WifiManager

/**
 * Keeps Android Wi-Fi multicast reception available while the installed AN3
 * shell is alive. Both the Rust sync peer and the Kotlin controller discovery
 * use the same LAN multicast envelope, so they must share one platform lock.
 */
object An3LanMulticast {
    private var lock: WifiManager.MulticastLock? = null

    @Synchronized
    fun acquire(context: Context) {
        if (lock?.isHeld == true) return
        val manager = context.applicationContext
            .getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return
        lock = manager.createMulticastLock("an3-direct-lan").apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    @Synchronized
    fun release() {
        lock?.let { current ->
            if (current.isHeld) current.release()
        }
        lock = null
    }
}
