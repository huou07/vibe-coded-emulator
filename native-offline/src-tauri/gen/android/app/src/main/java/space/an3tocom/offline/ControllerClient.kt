// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import org.json.JSONArray
import org.json.JSONObject
import java.io.DataInputStream
import java.io.DataOutputStream
import java.math.BigInteger
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.MulticastSocket
import java.net.NetworkInterface
import java.net.ServerSocket
import java.net.Socket
import java.nio.ByteBuffer
import java.security.AlgorithmParameters
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.interfaces.ECPublicKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPoint
import java.security.spec.ECPublicKeySpec
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.LinkedHashMap
import java.util.LinkedHashSet
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

data class ControllerUtilityResult(
    val commandId: String,
    val action: String,
    val slot: Int,
    val success: Boolean,
    val message: String,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("commandId", commandId)
        .put("action", action)
        .put("slot", slot)
        .put("success", success)
        .put("message", message)
}

/** Snapshot of the direct-LAN phone-controller host. No server token exists. */
data class ControllerStatus(
    val running: Boolean,
    val role: String,
    val paired: Boolean,
    val code: String,
    val inputActive: Boolean,
    val lastSequence: Int,
    val ackSequence: Int,
    val input: String,
    val error: String,
    val state: String = "idle",
    val utilityResultsSupported: Boolean = false,
    val utilityResults: List<ControllerUtilityResult> = emptyList(),
) {
    fun toJson(): String = JSONObject()
        .put("running", running)
        .put("role", role)
        .put("paired", paired)
        .put("code", code)
        .put("inputActive", inputActive)
        .put("lastSequence", lastSequence)
        .put("ackSequence", ackSequence)
        .put("input", input)
        .put("error", error)
        .put("state", state)
        .put("utilityResultsSupported", utilityResultsSupported)
        .put("utilityResults", JSONArray().apply { utilityResults.forEach { put(it.toJson()) } })
        .toString()
}

internal fun parseControllerUtilityResults(frame: JSONObject): List<ControllerUtilityResult> {
    val values = frame.optJSONArray("utilityResults") ?: return emptyList()
    val results = mutableListOf<ControllerUtilityResult>()
    for (index in 0 until minOf(values.length(), 64)) {
        val item = values.optJSONObject(index) ?: continue
        val commandId = item.optString("commandId", "")
        val action = item.optString("action", "").uppercase()
        val slot = item.optInt("slot", 0)
        val message = item.optString("message", "")
        controllerUtilityResult(commandId, action, slot, item.optBoolean("success", false), message)
            ?.let(results::add)
    }
    return results
}

internal fun controllerUtilityResult(
    commandId: String,
    action: String,
    slot: Int,
    success: Boolean,
    message: String,
): ControllerUtilityResult? {
    val canonicalAction = action.uppercase()
    if (commandId.length !in 1..128 || !commandId.all { it.code in 0x20..0x7e } ||
        canonicalAction !in setOf("QUICK_SAVE", "QUICK_LOAD", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU") ||
        slot !in 1..10 || message.length > 256) return null
    return ControllerUtilityResult(commandId, canonicalAction, slot, success, message)
}

/**
 * Direct LAN peer host for native gameplay.
 *
 * Discovery is a private multicast advertisement containing only public peer
 * metadata. The connection is a direct TCP stream. The six-digit code is used
 * once to derive an ephemeral AES-GCM session key from P-256 ECDH; it is never
 * sent to a server or retained after pairing.
 */
class ControllerClient(
    private val onStatus: (ControllerStatus) -> Unit,
    private val shouldApply: () -> Boolean,
    private val onButton: (Int, Boolean) -> Unit,
    private val onAnalog: (Float, Float) -> Unit,
    private val systemProvider: () -> String? = { null },
    private val onTouch: (Float, Float, Boolean) -> Unit = { _, _, _ -> },
    private val onUtility: (String, Int) -> Unit = { _, _ -> },
) {
    companion object {
        val BUTTONS = mapOf(
            "b" to 0, "y" to 1, "select" to 2, "start" to 3,
            "up" to 4, "down" to 5, "left" to 6, "right" to 7,
            "a" to 8, "x" to 9, "l" to 10, "r" to 11,
        )
        private const val DISCOVERY_ADDRESS = "239.255.43.3"
        private const val DISCOVERY_BROADCAST = "255.255.255.255"
        private const val DISCOVERY_PORT = 47831
        private const val CONTROL_PORT = 47832
        private const val PROTOCOL_VERSION = 1
        private const val MAX_FRAME_BYTES = 64 * 1024
        private const val CONNECT_TIMEOUT_MILLIS = 8_000
        private const val SOCKET_TIMEOUT_MILLIS = 10_000
        private const val PAIRING_TTL_MILLIS = 120_000L
        private const val MAX_FAILURES_PER_MINUTE = 6
        private const val FAILURE_WINDOW_MILLIS = 60_000L
        private const val MAX_PENDING_CONTROLLER_EVENTS = 64
        private const val AXIS_THRESHOLD = 0.35f
        private const val DIR_PHONE_TO_HOST = 1
        private const val DIR_HOST_TO_PHONE = 2
        private val EMPTY = ControllerStatus(false, "off", false, "", false, 0, 0, "", "")
        private val RANDOM = SecureRandom()
        private val failureLock = Any()
        private val failedAttempts = mutableMapOf<String, MutableList<Long>>()
    }

    private val executor = Executors.newCachedThreadPool { runnable ->
        Thread(runnable, "an3-lan-peer").apply { isDaemon = true }
    }
    private class ClientWriterSession(val connection: Socket, val key: ByteArray) {
        val outbound = ControllerSendQueue<JSONObject>(MAX_PENDING_CONTROLLER_EVENTS) { it.optLong("s", 0) }
        val monitor = java.lang.Object()
        var sendCounter = 1L
    }

    private val stopping = AtomicBoolean(false)
    private val operation = AtomicLong(0L)
    @Volatile private var server: ServerSocket? = null
    @Volatile private var discovery: DatagramSocket? = null
    @Volatile private var clientSocket: Socket? = null
    @Volatile private var connectingSocket: Socket? = null
    @Volatile private var clientKey: ByteArray? = null
    @Volatile private var clientSystem = "auto"
    @Volatile private var clientInputActive = false
    @Volatile private var clientUtilityResultsSupported = false
    @Volatile private var clientWriter: ClientWriterSession? = null
    private val clientUtilityResults = LinkedHashMap<String, ControllerUtilityResult>()
    @Volatile private var code = ""
    @Volatile private var codeExpiresAt = 0L
    @Volatile private var paired = false
    @Volatile private var lastSequence = 0
    @Volatile private var lastUtility = 0
    private val seenUtilityIds = LinkedHashSet<String>()
    @Volatile private var ackSequence = 0
    @Volatile private var input = ""
    @Volatile private var error = ""
    @Volatile private var connecting = false
    @Volatile private var applied = emptySet<String>()
    @Volatile private var axesEngaged = false
    @Volatile private var touchPressed = false
    private val deviceId = randomHex(16)
    private val pairingLock = Any()

    val running: Boolean get() = (server != null || clientSocket != null || connecting) && !stopping.get()

    private fun failureKey(address: InetAddress): String = address.hostAddress ?: address.toString()

    private fun rateLimited(address: InetAddress): Boolean = synchronized(failureLock) {
        val key = failureKey(address)
        val now = System.currentTimeMillis()
        val attempts = failedAttempts[key] ?: return@synchronized false
        attempts.removeAll { now - it >= FAILURE_WINDOW_MILLIS }
        if (attempts.isEmpty()) failedAttempts.remove(key)
        attempts.size >= MAX_FAILURES_PER_MINUTE
    }

    private fun noteFailure(address: InetAddress) = synchronized(failureLock) {
        val key = failureKey(address)
        val now = System.currentTimeMillis()
        val attempts = failedAttempts.getOrPut(key) { mutableListOf() }
        attempts.removeAll { now - it >= FAILURE_WINDOW_MILLIS }
        attempts.add(now)
    }

    private fun clearFailures(address: InetAddress) = synchronized(failureLock) {
        failedAttempts.remove(failureKey(address))
    }

    @Synchronized
    fun start() {
        if (running) return
        stop()
        stopping.set(false)
        connecting = false
        code = newPairingCode()
        codeExpiresAt = System.currentTimeMillis() + PAIRING_TTL_MILLIS
        paired = false
        lastSequence = 0
        lastUtility = 0
        synchronized(seenUtilityIds) { seenUtilityIds.clear() }
        ackSequence = 0
        input = ""
        error = ""
        try {
            server = ServerSocket(CONTROL_PORT, 8, InetAddress.getByName("0.0.0.0"))
        } catch (failure: Exception) {
            error = "Direct LAN controller unavailable: ${failure.message}"
            onStatus(status())
            return
        }
        onStatus(status())
        executor.execute { acceptLoop() }
        executor.execute { advertiseLoop() }
    }

    /** Join a direct controller host discovered on the local multicast LAN. */
    @Synchronized
    fun join(pairCode: String) {
        val normalized = pairCode.trim()
        if (!Regex("^[0-9]{6}$").matches(normalized)) {
            error = "Enter exactly six decimal digits."
            onStatus(status())
            return
        }
        stop()
        stopping.set(false)
        val operationId = operation.incrementAndGet()
        code = ""
        codeExpiresAt = 0L
        paired = false
        lastSequence = 0
        lastUtility = 0
        synchronized(seenUtilityIds) { seenUtilityIds.clear() }
        ackSequence = 0
        clientSystem = "auto"
        clientInputActive = false
        clientUtilityResultsSupported = false
        synchronized(clientUtilityResults) { clientUtilityResults.clear() }
        error = ""
        connecting = true
        onStatus(status())
        executor.execute { joinController(normalized, operationId) }
    }

    private fun isCurrent(operationId: Long): Boolean =
        operation.get() == operationId && !stopping.get()

    private fun joinController(normalized: String, operationId: Long) {
        var connection: Socket? = null
        var completed = false
        try {
            val peer = discoverController()
            if (!isCurrent(operationId)) return
            val socket = Socket()
            connection = socket
            connectingSocket = socket
            socket.connect(InetSocketAddress(peer.address, peer.port), CONNECT_TIMEOUT_MILLIS)
            socket.soTimeout = SOCKET_TIMEOUT_MILLIS
            val inputStream = DataInputStream(socket.getInputStream())
            val outputStream = DataOutputStream(socket.getOutputStream())
            val secret = ecKeyPair()
            val hello = JSONObject()
                .put("k", "hello")
                .put("v", PROTOCOL_VERSION)
                .put("pub", encode(publicKeyBytes(secret.public)))
                .put("id", deviceId)
                .put("name", "Android device")
                .put("capability", "controller")
            writeFrame(outputStream, hello.toString().toByteArray(Charsets.UTF_8))
            val response = JSONObject(String(readFrame(inputStream), Charsets.UTF_8))
            require(response.optString("k") == "hello" && response.optInt("v") == PROTOCOL_VERSION) {
                "The direct peer uses an incompatible protocol."
            }
            val peerPublic = publicKeyFromRaw(decode(response.optString("pub")))
            val agreement = KeyAgreement.getInstance("ECDH")
            agreement.init(secret.private)
            agreement.doPhase(peerPublic, true)
            val sharedSecret = agreement.generateSecret()
            val sessionKey = deriveKey(sharedSecret, normalized.toByteArray(Charsets.UTF_8))
            writeFrame(outputStream, seal(sessionKey, DIR_PHONE_TO_HOST, 0, JSONObject().put("k", "auth")))
            val ready = open(sessionKey, DIR_HOST_TO_PHONE, 0, readFrame(inputStream))
                ?: throw IllegalStateException("The direct peer rejected the pairing code.")
            require(ready.optString("k") == "ready") { "The direct peer did not confirm pairing." }
            // The handshake is bounded; the authenticated controller stream
            // stays open while the host is idle in a menu or has no game.
            socket.soTimeout = 0
            if (!isCurrent(operationId)) return
            val writerSession = synchronized(this) {
                if (!isCurrent(operationId)) return
                ClientWriterSession(socket, sessionKey).also { session ->
                    clientSocket = socket
                    connectingSocket = null
                    clientKey = sessionKey
                    clientWriter = session
                    clientSystem = ready.optString("system", "auto")
                    paired = true
                    connecting = false
                    completed = true
                }
            }
            onStatus(status())
            executor.execute { clientWriteLoop(writerSession) }
            executor.execute { clientReadLoop(writerSession, inputStream) }
        } catch (failure: Exception) {
            if (isCurrent(operationId)) {
                try { clientSocket?.close() } catch (_: Exception) {}
                clientSocket = null
                clientKey = null
                paired = false
                clientInputActive = false
                connecting = false
                error = failure.message ?: "Could not join the direct LAN host."
                onStatus(status())
            }
        } finally {
            if (connectingSocket === connection) connectingSocket = null
            if (connection != null && clientSocket !== connection) {
                try { connection.close() } catch (_: Exception) {}
            }
            if (!completed && isCurrent(operationId) && connecting) {
                connecting = false
                onStatus(status())
            }
        }
    }

    @Synchronized
    fun stop() {
        operation.incrementAndGet()
        stopping.set(true)
        clientWriter?.let { writer ->
            writer.outbound.clear()
            synchronized(writer.monitor) { writer.monitor.notifyAll() }
        }
        try { server?.close() } catch (_: Exception) {}
        try { discovery?.close() } catch (_: Exception) {}
        try { clientSocket?.close() } catch (_: Exception) {}
        try { connectingSocket?.close() } catch (_: Exception) {}
        server = null
        discovery = null
        clientSocket = null
        connectingSocket = null
        clientKey = null
        clientWriter = null
        clientSystem = "auto"
        clientInputActive = false
        connecting = false
        release()
        code = ""
        codeExpiresAt = 0L
        paired = false
        lastUtility = 0
        synchronized(seenUtilityIds) { seenUtilityIds.clear() }
        synchronized(clientUtilityResults) { clientUtilityResults.clear() }
        input = ""
        error = ""
        onStatus(EMPTY.copy(error = ""))
    }

    fun releaseInput() = release()

    /** Send one complete controller snapshot over the encrypted direct session. */
    fun sendState(state: JSONObject): ControllerStatus {
        val writer = clientWriter ?: return status().copy(error = "No direct controller session is active.")
        if (clientSocket !== writer.connection || clientKey !== writer.key) {
            return status().copy(error = "The direct controller session is not authenticated.")
        }
        return try {
            val queued = JSONObject(state.toString())
            val motion = queued.optString("_an3q") == "motion"
            queued.remove("_an3q")
            queued.put("k", "state")
            if (!writer.outbound.offer(queued, motion)) {
                failClientWriter(writer, IllegalStateException("The controller event queue is full; the session was stopped to preserve input transitions."))
                return status()
            }
            synchronized(writer.monitor) { writer.monitor.notifyAll() }
            status()
        } catch (failure: Exception) {
            setError("Direct controller send failed: ${failure.message ?: "connection closed"}")
            status()
        }
    }

    fun status(): ControllerStatus {
        val client = clientSocket != null
        return ControllerStatus(
            running = running,
            role = if (client || connecting) "controller" else if (server != null) "host" else "off",
            paired = paired,
            code = if (!client && running && !paired && System.currentTimeMillis() < codeExpiresAt) code else "",
            inputActive = if (client) clientInputActive else shouldApply() && paired,
            lastSequence = lastSequence,
            ackSequence = ackSequence,
            input = if (client) "" else input,
            error = error,
            utilityResultsSupported = client && clientUtilityResultsSupported,
            utilityResults = if (client) synchronized(clientUtilityResults) {
                clientUtilityResults.values.toList()
            } else emptyList(),
            state = when {
                error.isNotEmpty() -> "error"
                paired && client -> "connected"
                connecting -> "connecting"
                server != null -> "waiting"
                else -> "idle"
            },
        )
    }

    private fun acceptLoop() {
        while (!stopping.get()) {
            try {
                val socket = server?.accept() ?: break
                executor.execute { handle(socket) }
            } catch (_: Exception) {
                if (!stopping.get()) setError("Direct LAN controller stopped unexpectedly")
            }
        }
    }

    private fun advertiseLoop() {
        try {
            val address = InetAddress.getByName(DISCOVERY_ADDRESS)
            // Android devices can expose a down cellular interface before the
            // active Wi-Fi interface (this phone is wlan1).  Letting the
            // multicast socket choose the default interface makes discovery
            // silently disappear even though direct TCP to the peer works.
            val socket = MulticastSocket().apply {
                localMulticastInterface()?.let { networkInterface = it }
            }
            discovery = socket
            while (!stopping.get()) {
                val advertisement = JSONObject()
                    .put("an3", "peer")
                    .put("service", "an3-peer")
                    .put("v", PROTOCOL_VERSION)
                    .put("id", deviceId)
                    .put("name", "Android device")
                    .put("port", CONTROL_PORT)
                    // Native sync is intentionally not advertised until this
                    // shell has an account-backed peer proof provider.
                    .put("capabilities", JSONArray().put("controller"))
                    .toString()
                    .toByteArray(Charsets.UTF_8)
                socket.send(DatagramPacket(advertisement, advertisement.size, address, DISCOVERY_PORT))
                socket.broadcast = true
                socket.send(DatagramPacket(advertisement, advertisement.size, InetAddress.getByName(DISCOVERY_BROADCAST), DISCOVERY_PORT))
                Thread.sleep(2000)
            }
        } catch (_: Exception) {
            if (!stopping.get()) setError("Direct LAN discovery unavailable")
        }
    }

    private data class DiscoveredPeer(val address: InetAddress, val port: Int)

    private fun discoverController(): DiscoveredPeer {
        MulticastSocket(null).use { socket ->
            socket.reuseAddress = true
            socket.bind(InetSocketAddress(DISCOVERY_PORT))
            localMulticastInterface()?.let { socket.networkInterface = it }
            val group = InetAddress.getByName(DISCOVERY_ADDRESS)
            socket.joinGroup(group)
            socket.soTimeout = 250
            val deadline = System.currentTimeMillis() + 3_000L
            val buffer = ByteArray(4096)
            while (System.currentTimeMillis() < deadline) {
                try {
                    val packet = DatagramPacket(buffer, buffer.size)
                    socket.receive(packet)
                    val record = JSONObject(String(packet.data, packet.offset, packet.length, Charsets.UTF_8))
                    val sensitive = record.keys().asSequence().any { it.matches(Regex("(?i)account|email|token|accessToken|refreshToken|password|credential|secret|auth")) }
                    val capabilities = record.optJSONArray("capabilities")
                    val controller = capabilities != null && (0 until capabilities.length()).any { capabilities.optString(it) == "controller" }
                    val id = record.optString("id")
                    val name = record.optString("name")
                    val port = record.optInt("port", 0)
                    if (!sensitive && record.optString("an3") == "peer" && record.optString("service") == "an3-peer" && record.optInt("v") == PROTOCOL_VERSION && controller && port in 1..65535 && Regex("^[A-Za-z0-9._-]{8,64}$").matches(id) && name.length in 1..64) {
                        return DiscoveredPeer(packet.address, port)
                    }
                } catch (_: Exception) {
                    // Keep listening until the bounded discovery window expires.
                }
            }
        }
        throw IllegalStateException("No AN3 controller host was found on the local network.")
    }

    private fun localMulticastInterface(): NetworkInterface? {
        val interfaces = NetworkInterface.getNetworkInterfaces() ?: return null
        var fallback: NetworkInterface? = null
        while (interfaces.hasMoreElements()) {
            val candidate = interfaces.nextElement()
            if (!candidate.isUp || candidate.isLoopback || !candidate.supportsMulticast()) continue
            val hasIpv4 = candidate.inetAddresses.asSequence().any { address ->
                address is java.net.Inet4Address && !address.isLoopbackAddress
            }
            if (!hasIpv4) continue
            if (candidate.name.startsWith("wlan") || candidate.name.startsWith("wifi")) return candidate
            if (fallback == null) fallback = candidate
        }
        return fallback
    }

    private fun clientReadLoop(writer: ClientWriterSession, inputStream: DataInputStream) {
        val connection = writer.connection
        var receiveCounter = 1L
        try {
            while (!stopping.get() && !connection.isClosed) {
                val frame = open(writer.key, DIR_HOST_TO_PHONE, receiveCounter, readFrame(inputStream))
                    ?: throw IllegalStateException("The direct controller acknowledgement failed authentication.")
                receiveCounter += 1
                if (frame.optString("k") == "ack") {
                    val utilityResults = parseControllerUtilityResults(frame)
                    val update = synchronized(this) {
                        if (clientWriter !== writer || clientSocket !== connection) null
                        else {
                            ackSequence = frame.optLong("s", 0).coerceAtMost(Int.MAX_VALUE.toLong()).toInt()
                            clientInputActive = frame.optBoolean("inputActive", false)
                            clientSystem = frame.optString("system", clientSystem)
                            clientUtilityResultsSupported = frame.optBoolean("utilityResultsSupported", false)
                            synchronized(clientUtilityResults) {
                                utilityResults.forEach { clientUtilityResults[it.commandId] = it }
                                while (clientUtilityResults.size > 64) {
                                    clientUtilityResults.remove(clientUtilityResults.keys.first())
                                }
                            }
                            error = ""
                            status()
                        }
                    }
                    if (update == null) return
                    onStatus(update)
                }
            }
        } catch (failure: Exception) {
            if (!stopping.get()) setError("Direct controller session ended")
        } finally {
            val disconnected = synchronized(this) {
                if (clientWriter !== writer || clientSocket !== connection) false
                else {
                    clientSocket = null
                    clientKey = null
                    clientWriter = null
                    paired = false
                    clientInputActive = false
                    writer.outbound.clear()
                    synchronized(writer.monitor) { writer.monitor.notifyAll() }
                    true
                }
            }
            if (disconnected && !stopping.get()) onStatus(status())
            try { connection.close() } catch (_: Exception) {}
        }
    }

    /** The sole writer for authenticated client frames; never called by the WebView bridge. */
    private fun clientWriteLoop(writer: ClientWriterSession) {
        val connection = writer.connection
        try {
            val output = DataOutputStream(connection.getOutputStream())
            while (!stopping.get() && clientSocket === connection && clientWriter === writer) {
                val next = synchronized(writer.monitor) {
                    var queued = if (clientWriter === writer && clientSocket === connection) writer.outbound.poll() else null
                    while (queued == null && !stopping.get() && clientSocket === connection && clientWriter === writer) {
                        writer.monitor.wait()
                        queued = if (clientWriter === writer && clientSocket === connection) writer.outbound.poll() else null
                    }
                    queued
                } ?: return
                writeFrame(output, seal(writer.key, DIR_PHONE_TO_HOST, writer.sendCounter, next))
                writer.sendCounter += 1
            }
        } catch (failure: Exception) {
            if (!stopping.get() && clientSocket === connection && clientWriter === writer) failClientWriter(writer, failure)
        }
    }

    private fun failClientWriter(writer: ClientWriterSession, failure: Exception) {
        val update = synchronized(this) {
            if (clientWriter !== writer || clientSocket !== writer.connection) return
            error = failure.message ?: "Direct controller send failed."
            clientSocket = null
            clientKey = null
            clientWriter = null
            paired = false
            clientInputActive = false
            writer.outbound.clear()
            synchronized(writer.monitor) { writer.monitor.notifyAll() }
            status()
        }
        try { writer.connection.close() } catch (_: Exception) {}
        onStatus(update)
    }

    private fun handle(socket: Socket) {
        socket.use { connection ->
            try {
                val peerAddress = connection.inetAddress
                connection.soTimeout = 30_000
                val inputStream = DataInputStream(connection.getInputStream())
                val outputStream = DataOutputStream(connection.getOutputStream())
                val hello = JSONObject(String(readFrame(inputStream), Charsets.UTF_8))
                val peerId = hello.optString("id")
                if (hello.optString("k") != "hello" || hello.optInt("v") != PROTOCOL_VERSION || hello.optString("capability") != "controller" || !Regex("^[A-Za-z0-9._-]{8,64}$").matches(peerId)) {
                    noteFailure(peerAddress)
                    return
                }
                if (rateLimited(peerAddress)) return
                val peerPublic = publicKeyFromRaw(decode(hello.optString("pub")))
                val keyPair = ecKeyPair()
                val agreement = KeyAgreement.getInstance("ECDH")
                agreement.init(keyPair.private)
                agreement.doPhase(peerPublic, true)
                val shared = agreement.generateSecret()
                val response = JSONObject()
                    .put("k", "hello")
                    .put("v", PROTOCOL_VERSION)
                    .put("pub", encode(publicKeyBytes(keyPair.public)))
                    .put("id", deviceId)
                    .put("name", "Android device")
                writeFrame(outputStream, response.toString().toByteArray(Charsets.UTF_8))

                if (paired || System.currentTimeMillis() >= codeExpiresAt) return
                    val sessionKey = deriveKey(shared, code.toByteArray(Charsets.UTF_8))
                val auth = open(sessionKey, DIR_PHONE_TO_HOST, 0, readFrame(inputStream))
                if (auth?.optString("k") != "auth") {
                    noteFailure(peerAddress)
                    return
                }
                // Pairing is one-shot even when two peers race to use the
                // same displayed code. The second authenticated socket is
                // rejected before it can receive a ready frame.
                synchronized(pairingLock) {
                    if (paired || System.currentTimeMillis() >= codeExpiresAt) {
                        noteFailure(peerAddress)
                        return
                    }
                    paired = true
                    code = ""
                    codeExpiresAt = 0L
                    lastSequence = 0
                    lastUtility = 0
                    synchronized(seenUtilityIds) { seenUtilityIds.clear() }
                    release()
                }
                clearFailures(peerAddress)
                onStatus(status())
                val ready = JSONObject()
                    .put("k", "ready")
                    .put("token", JSONObject.NULL)
                    .put("system", systemProvider() ?: "auto")
                writeFrame(outputStream, seal(sessionKey, DIR_HOST_TO_PHONE, 0, ready))
                connection.soTimeout = 0
                readFrames(inputStream, outputStream, sessionKey)
            } catch (failure: Exception) {
                if (!stopping.get()) setError("Direct LAN controller session ended")
            } finally {
                // A controller session is per-connection.  If the remote peer
                // closes its authenticated stream, keep the host available for a
                // fresh hosting session but do not leave the UI claiming that the
                // old controller is still paired.
                if (!stopping.get()) {
                    paired = false
                    clientInputActive = false
                    onStatus(status())
                }
                release()
            }
        }
    }

    private fun readFrames(inputStream: DataInputStream, outputStream: DataOutputStream, key: ByteArray) {
        var receiveCounter = 1L
        var sendCounter = 1L
        while (!stopping.get()) {
            val frame = open(key, DIR_PHONE_TO_HOST, receiveCounter, readFrame(inputStream)) ?: return
            receiveCounter += 1
            if (frame.optString("k") != "state") continue
            val sequence = frame.optLong("s", 0).coerceAtMost(Int.MAX_VALUE.toLong()).toInt()
            if (sequence <= lastSequence) continue
            lastSequence = sequence
            if (shouldApply()) {
                apply(frame)
                error = ""
            } else {
                release()
            }
            val ack = JSONObject()
                .put("k", "ack")
                .put("s", lastSequence)
                .put("utilitySequence", lastUtility)
                .put("inputActive", shouldApply() && paired)
                .put("system", systemProvider() ?: "auto")
            writeFrame(outputStream, seal(key, DIR_HOST_TO_PHONE, sendCounter, ack))
            sendCounter += 1
            ackSequence = lastSequence
            onStatus(status())
        }
    }

    private fun apply(frame: JSONObject) {
        val state = frame.optJSONArray("b")
        val pressed = mutableSetOf<String>()
        if (state != null) for (index in 0 until state.length()) {
            val name = state.optString(index)
            if (BUTTONS.containsKey(name)) pressed.add(name)
        }
        for (name in applied) if (!pressed.contains(name)) BUTTONS[name]?.let { onButton(it, false) }
        for (name in pressed) if (!applied.contains(name)) BUTTONS[name]?.let { onButton(it, true) }
        applied = pressed
        val axes = frame.optJSONArray("a")
        val leftX = axes?.optDouble(0, 0.0)?.toFloat() ?: 0f
        val leftY = axes?.optDouble(1, 0.0)?.toFloat() ?: 0f
        val engaged = kotlin.math.abs(leftX) > AXIS_THRESHOLD || kotlin.math.abs(leftY) > AXIS_THRESHOLD
        if (engaged) { onAnalog(leftX, leftY); axesEngaged = true }
        else if (axesEngaged) { onAnalog(0f, 0f); axesEngaged = false }
        val touch = frame.optJSONArray("t")
        if (touch != null && touch.length() == 2) {
            onTouch(touch.optDouble(0, 0.0).toFloat(), touch.optDouble(1, 0.0).toFloat(), true)
            touchPressed = true
        } else if (touchPressed) {
            onTouch(0f, 0f, false)
            touchPressed = false
        }
        dispatchUtilities(frame)
        input = pressed.sorted().joinToString(",")
    }

    /** Apply each one-shot utility action once, even when a state frame is retried. */
    private fun dispatchUtilities(frame: JSONObject) {
        frame.optJSONArray("u")?.let { utilities ->
            for (index in 0 until utilities.length()) {
                val item = utilities.optJSONObject(index) ?: continue
                val sequence = item.optInt("sequence", 0)
                val commandId = item.optString("command_id", item.optString("commandId", "")).trim()
                if (commandId.isNotEmpty()) {
                    val duplicate = synchronized(seenUtilityIds) {
                        if (!seenUtilityIds.add(commandId)) true
                        else {
                            if (seenUtilityIds.size > 64) seenUtilityIds.iterator().next().let { seenUtilityIds.remove(it) }
                            false
                        }
                    }
                    if (duplicate) continue
                } else if (sequence <= lastUtility) continue
                lastUtility = maxOf(lastUtility, sequence)
                val action = item.optString("action").uppercase()
                if (action !in setOf("QUICK_SAVE", "QUICK_LOAD", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU")) continue
                val slot = item.optInt("slot", 1)
                if (slot !in 1..10) continue
                onUtility(action, slot)
            }
        }
    }

    private fun release() {
        for (name in applied) BUTTONS[name]?.let { onButton(it, false) }
        applied = emptySet()
        if (axesEngaged) { onAnalog(0f, 0f); axesEngaged = false }
        if (touchPressed) { onTouch(0f, 0f, false); touchPressed = false }
    }

    private fun setError(message: String) {
        error = message
        onStatus(status())
    }

    private fun newPairingCode(): String = buildString {
        repeat(6) { append(('0'.code + RANDOM.nextInt(10)).toChar()) }
    }

    private fun randomHex(bytes: Int): String {
        val value = ByteArray(bytes)
        RANDOM.nextBytes(value)
        return value.joinToString("") { "%02x".format(it) }
    }

    private fun ecKeyPair() = KeyPairGenerator.getInstance("EC").apply {
        initialize(ECGenParameterSpec("secp256r1"), RANDOM)
    }.generateKeyPair()

    private fun publicKeyBytes(key: java.security.PublicKey): ByteArray {
        val point = (key as ECPublicKey).w
        val xBytes = point.affineX.toByteArray()
        val yBytes = point.affineY.toByteArray()
        val x = xBytes.copyOfRange(maxOf(0, xBytes.size - 32), xBytes.size)
        val y = yBytes.copyOfRange(maxOf(0, yBytes.size - 32), yBytes.size)
        return byteArrayOf(4) + ByteArray(32 - x.size) + x + ByteArray(32 - y.size) + y
    }

    private fun publicKeyFromRaw(raw: ByteArray): java.security.PublicKey {
        require(raw.size == 65 && raw[0].toInt() == 4)
        val parameters = AlgorithmParameters.getInstance("EC").apply { init(ECGenParameterSpec("secp256r1")) }
            .getParameterSpec(ECParameterSpec::class.java)
        val point = ECPoint(BigInteger(1, raw.copyOfRange(1, 33)), BigInteger(1, raw.copyOfRange(33, 65)))
        return KeyFactory.getInstance("EC").generatePublic(ECPublicKeySpec(point, parameters))
    }

    private fun deriveKey(shared: ByteArray, secret: ByteArray): ByteArray {
        val salt = MessageDigest.getInstance("SHA-256").digest("an3-ctrl-v1|".toByteArray() + secret)
        val prk = hmac(salt, shared)
        val info = "an3-ctrl|v1|session".toByteArray()
        var previous = ByteArray(0)
        val output = ByteArray(32)
        var offset = 0
        for (counter in 1..2) {
            previous = hmac(prk, previous + info + byteArrayOf(counter.toByte()))
            val count = minOf(previous.size, output.size - offset)
            previous.copyInto(output, offset, 0, count)
            offset += count
        }
        return output
    }

    private fun hmac(key: ByteArray, data: ByteArray): ByteArray = Mac.getInstance("HmacSHA256").run {
        init(SecretKeySpec(key, "HmacSHA256")); doFinal(data)
    }

    private fun shortDigest(value: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(value).take(4).joinToString("") { "%02x".format(it) }

    private fun nonce(direction: Int, counter: Long): ByteArray = ByteBuffer.allocate(12).putInt(direction).putLong(counter).array()

    private fun seal(key: ByteArray, direction: Int, counter: Long, value: JSONObject): ByteArray {
        val nonce = nonce(direction, counter)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce))
        return nonce + cipher.doFinal(value.toString().toByteArray(Charsets.UTF_8))
    }

    private fun open(key: ByteArray, direction: Int, counter: Long, body: ByteArray): JSONObject? {
        if (body.size < 28 || !body.copyOfRange(0, 12).contentEquals(nonce(direction, counter))) return null
        return try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, body.copyOfRange(0, 12)))
            JSONObject(String(cipher.doFinal(body.copyOfRange(12, body.size)), Charsets.UTF_8))
        } catch (_: Exception) { null }
    }

    private fun readFrame(input: DataInputStream): ByteArray {
        val length = input.readInt()
        require(length in 1..MAX_FRAME_BYTES)
        return ByteArray(length).also { input.readFully(it) }
    }

    private fun writeFrame(output: DataOutputStream, body: ByteArray) {
        require(body.isNotEmpty() && body.size <= MAX_FRAME_BYTES)
        output.writeInt(body.size); output.write(body); output.flush()
    }

    private fun encode(bytes: ByteArray): String = android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
    private fun decode(value: String): ByteArray = android.util.Base64.decode(value, android.util.Base64.DEFAULT)
}
