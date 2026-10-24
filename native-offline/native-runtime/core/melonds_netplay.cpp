// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "melonds_netplay.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstring>
#include <limits>
#include <sstream>

#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace an3 {
namespace {

constexpr std::array<uint8_t, 8> kMagic = {'A', 'N', '3', 'M', 'D', 'S', 'N', 'P'};
constexpr uint8_t kHello = 1;
constexpr uint8_t kHelloAck = 2;
constexpr uint8_t kData = 3;
constexpr uint8_t kBye = 4;
constexpr uint8_t kReject = 5;
constexpr std::size_t kHeaderBytes = 19;
constexpr std::size_t kMaxPayloadBytes = 64u * 1024u;
constexpr std::size_t kMaxHandshakeField = 96;

#if defined(_WIN32)
using NativeSocket = SOCKET;
using SocketLength = int;
constexpr NativeSocket kInvalidSocket = INVALID_SOCKET;
#else
using NativeSocket = int;
using SocketLength = socklen_t;
constexpr NativeSocket kInvalidSocket = -1;
#endif

struct SocketBundle {
    NativeSocket listener = kInvalidSocket;
    NativeSocket connection = kInvalidSocket;
};

void close_socket(NativeSocket socket) {
    if (socket == kInvalidSocket) return;
#if defined(_WIN32)
    closesocket(socket);
#else
    ::close(socket);
#endif
}

bool would_block() {
#if defined(_WIN32)
    const int value = WSAGetLastError();
    return value == WSAEWOULDBLOCK || value == WSAEINPROGRESS || value == WSAEALREADY;
#else
    return errno == EAGAIN || errno == EWOULDBLOCK || errno == EINPROGRESS || errno == EALREADY;
#endif
}

std::string socket_error() {
#if defined(_WIN32)
    return "socket error " + std::to_string(WSAGetLastError());
#else
    return std::strerror(errno);
#endif
}

bool set_nonblocking(NativeSocket socket, std::string& error) {
#if defined(_WIN32)
    u_long value = 1;
    if (ioctlsocket(socket, FIONBIO, &value) != 0) {
        error = "Could not configure LAN multiplayer socket: " + socket_error();
        return false;
    }
#else
    const int flags = fcntl(socket, F_GETFL, 0);
    if (flags < 0 || fcntl(socket, F_SETFL, flags | O_NONBLOCK) < 0) {
        error = "Could not configure LAN multiplayer socket: " + socket_error();
        return false;
    }
#endif
    return true;
}

bool is_lan_ipv4(const in_addr& address) {
    const uint32_t value = ntohl(address.s_addr);
    const uint8_t first = static_cast<uint8_t>(value >> 24);
    const uint8_t second = static_cast<uint8_t>(value >> 16);
    return first == 10 ||
           (first == 172 && second >= 16 && second <= 31) ||
           (first == 192 && second == 168) ||
           (first == 127) ||
           (first == 169 && second == 254);
}

bool ensure_sockets(std::string& error) {
#if defined(_WIN32)
    static bool initialized = false;
    if (!initialized) {
        WSADATA data{};
        if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
            error = "Could not initialize the Windows LAN multiplayer socket layer.";
            return false;
        }
        initialized = true;
    }
#else
    (void)error;
#endif
    return true;
}

uint16_t read_u16(const uint8_t* value) {
    return static_cast<uint16_t>((static_cast<uint16_t>(value[0]) << 8) | value[1]);
}

uint32_t read_u32(const uint8_t* value) {
    return (static_cast<uint32_t>(value[0]) << 24) |
           (static_cast<uint32_t>(value[1]) << 16) |
           (static_cast<uint32_t>(value[2]) << 8) | value[3];
}

void append_u16(std::vector<uint8_t>& output, uint16_t value) {
    output.push_back(static_cast<uint8_t>(value >> 8));
    output.push_back(static_cast<uint8_t>(value));
}

void append_u32(std::vector<uint8_t>& output, uint32_t value) {
    output.push_back(static_cast<uint8_t>(value >> 24));
    output.push_back(static_cast<uint8_t>(value >> 16));
    output.push_back(static_cast<uint8_t>(value >> 8));
    output.push_back(static_cast<uint8_t>(value));
}

bool append_field(std::vector<uint8_t>& output, const std::string& value) {
    if (value.size() > kMaxHandshakeField || value.size() > 255) return false;
    output.push_back(static_cast<uint8_t>(value.size()));
    output.insert(output.end(), value.begin(), value.end());
    return true;
}

bool read_field(const std::vector<uint8_t>& payload, std::size_t& offset, std::string& value) {
    if (offset >= payload.size()) return false;
    const std::size_t length = payload[offset++];
    if (length > kMaxHandshakeField || length > payload.size() - offset) return false;
    value.assign(reinterpret_cast<const char*>(payload.data() + offset), length);
    offset += length;
    return true;
}

std::vector<uint8_t> handshake_payload(const MelonDsNetplayConfig& config) {
    std::vector<uint8_t> payload;
    payload.reserve(3 + config.core_id.size() + config.protocol_version.size() + config.game_identity.size());
    (void)append_field(payload, config.core_id);
    (void)append_field(payload, config.protocol_version);
    (void)append_field(payload, config.game_identity);
    return payload;
}

bool wait_for_connection(NativeSocket socket, std::string& error) {
    fd_set writable;
    FD_ZERO(&writable);
    FD_SET(socket, &writable);
    timeval timeout{};
    timeout.tv_sec = 3;
    const int result = select(
#if defined(_WIN32)
        0,
#else
        socket + 1,
#endif
        nullptr, &writable, nullptr, &timeout);
    if (result <= 0) {
        error = result == 0 ? "The LAN multiplayer host did not answer within three seconds."
                            : "Could not connect to the LAN multiplayer host: " + socket_error();
        return false;
    }
    int status = 0;
    SocketLength length = sizeof(status);
    if (getsockopt(socket, SOL_SOCKET, SO_ERROR, reinterpret_cast<char*>(&status), &length) != 0 || status != 0) {
        error = "Could not connect to the LAN multiplayer host: " + std::to_string(status);
        return false;
    }
    return true;
}

} // namespace

struct MelonDsNetplayTransport::SocketState : SocketBundle {};

MelonDsNetplayTransport::MelonDsNetplayTransport() : sockets_(new SocketState) {}

MelonDsNetplayTransport::~MelonDsNetplayTransport() {
    close();
    delete sockets_;
    sockets_ = nullptr;
}

bool MelonDsNetplayTransport::open(const MelonDsNetplayConfig& config, std::string& error) {
    close();
    config_ = config;
    if (config_.role == MelonDsNetplayRole::Disabled) return true;
    if (config_.core_id.empty() || config_.protocol_version.empty() || config_.game_identity.empty()) {
        error = "LAN multiplayer needs a core, protocol version, and game identity.";
        return false;
    }
    if (config_.core_id.size() > kMaxHandshakeField ||
        config_.protocol_version.size() > kMaxHandshakeField ||
        config_.game_identity.size() > kMaxHandshakeField) {
        error = "LAN multiplayer identity fields are too long.";
        return false;
    }
    if (config_.port == 0) {
        error = "LAN multiplayer needs a non-zero port.";
        return false;
    }
    if (!ensure_sockets(error)) return false;
    if (config_.role == MelonDsNetplayRole::Host) return open_host(config_, error);
    return open_join(config_, error);
}

bool MelonDsNetplayTransport::open_host(const MelonDsNetplayConfig& config, std::string& error) {
    sockets_->listener = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sockets_->listener == kInvalidSocket) {
        error = "Could not create the LAN multiplayer host socket: " + socket_error();
        return false;
    }
    int reuse = 1;
    (void)setsockopt(sockets_->listener, SOL_SOCKET, SO_REUSEADDR,
                     reinterpret_cast<const char*>(&reuse), sizeof(reuse));
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons(config.port);
    if (bind(sockets_->listener, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) != 0 ||
        listen(sockets_->listener, 1) != 0 || !set_nonblocking(sockets_->listener, error)) {
        error = "Could not listen for LAN multiplayer: " + socket_error();
        close_socket(sockets_->listener);
        sockets_->listener = kInvalidSocket;
        return false;
    }
    local_port_ = config.port;
    active_ = true;
    listening_ = true;
    detail_ = "Hosting melonDS LAN game on port " + std::to_string(local_port_);
    return true;
}

bool MelonDsNetplayTransport::open_join(const MelonDsNetplayConfig& config, std::string& error) {
    if (config.address.empty()) {
        error = "Enter the host's current LAN address.";
        return false;
    }
    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    addrinfo* results = nullptr;
    const std::string service = std::to_string(config.port);
    const int lookup = getaddrinfo(config.address.c_str(), service.c_str(), &hints, &results);
    if (lookup != 0 || !results) {
        error = "The LAN multiplayer address is not valid or cannot be resolved.";
        return false;
    }
    if (results->ai_family != AF_INET ||
        !is_lan_ipv4(reinterpret_cast<const sockaddr_in*>(results->ai_addr)->sin_addr)) {
        freeaddrinfo(results);
        error = "LAN multiplayer requires a private, loopback, or link-local IPv4 address.";
        return false;
    }
    sockets_->connection = ::socket(results->ai_family, results->ai_socktype, results->ai_protocol);
    if (sockets_->connection == kInvalidSocket) {
        freeaddrinfo(results);
        error = "Could not create the LAN multiplayer client socket: " + socket_error();
        return false;
    }
    if (!set_nonblocking(sockets_->connection, error)) {
        freeaddrinfo(results);
        close_socket(sockets_->connection);
        sockets_->connection = kInvalidSocket;
        return false;
    }
    const int connected = connect(sockets_->connection, results->ai_addr, static_cast<int>(results->ai_addrlen));
    freeaddrinfo(results);
    if (connected != 0 && !would_block()) {
        error = "Could not connect to the LAN multiplayer host: " + socket_error();
        close_socket(sockets_->connection);
        sockets_->connection = kInvalidSocket;
        return false;
    }
    if (connected != 0 && !wait_for_connection(sockets_->connection, error)) {
        close_socket(sockets_->connection);
        sockets_->connection = kInvalidSocket;
        return false;
    }
    active_ = true;
    detail_ = "Connecting directly to the melonDS LAN host";
    return queue_handshake(kHello, error);
}

bool MelonDsNetplayTransport::accept_host(std::string& error) {
    if (sockets_->listener == kInvalidSocket || sockets_->connection != kInvalidSocket) return true;
    sockaddr_storage peer{};
    SocketLength length = sizeof(peer);
    const NativeSocket accepted = accept(sockets_->listener, reinterpret_cast<sockaddr*>(&peer), &length);
    if (accepted == kInvalidSocket) {
        if (would_block()) return true;
        error = "The LAN multiplayer host could not accept a peer: " + socket_error();
        return false;
    }
    if (peer.ss_family != AF_INET ||
        !is_lan_ipv4(reinterpret_cast<const sockaddr_in*>(&peer)->sin_addr)) {
        close_socket(accepted);
        error = "LAN multiplayer accepts only a local private, loopback, or link-local peer.";
        return false;
    }
    if (!set_nonblocking(accepted, error)) {
        close_socket(accepted);
        return false;
    }
    sockets_->connection = accepted;
    detail_ = "Peer connected; validating melonDS game and protocol";
    return true;
}

bool MelonDsNetplayTransport::queue_frame(uint8_t kind, int flags, uint16_t client_id,
                                           const std::vector<uint8_t>& payload, std::string& error) {
    if (payload.size() > kMaxPayloadBytes) {
        error = "The melonDS LAN packet exceeds the 64 KiB libretro limit.";
        return false;
    }
    std::vector<uint8_t> frame;
    frame.reserve(kHeaderBytes + payload.size());
    frame.insert(frame.end(), kMagic.begin(), kMagic.end());
    frame.push_back(kind);
    append_u32(frame, static_cast<uint32_t>(flags));
    append_u16(frame, client_id);
    append_u32(frame, static_cast<uint32_t>(payload.size()));
    frame.insert(frame.end(), payload.begin(), payload.end());
    transmit_queue_.push_back(std::move(frame));
    return flush(error);
}

bool MelonDsNetplayTransport::flush(std::string& error) {
    while (!transmit_queue_.empty()) {
        const auto& frame = transmit_queue_.front();
        const auto remaining = frame.size() - transmit_offset_;
        const int sent = static_cast<int>(::send(sockets_->connection,
            reinterpret_cast<const char*>(frame.data() + transmit_offset_),
            static_cast<int>(remaining), 0));
        if (sent > 0) {
            transmit_offset_ += static_cast<std::size_t>(sent);
            if (transmit_offset_ == frame.size()) {
                transmit_queue_.pop_front();
                transmit_offset_ = 0;
            }
            continue;
        }
        if (sent < 0 && would_block()) return true;
        error = "The direct melonDS LAN session closed while sending a packet.";
        return false;
    }
    return true;
}

bool MelonDsNetplayTransport::queue_handshake(uint8_t kind, std::string& error) {
    return queue_frame(kind, 0, 0, handshake_payload(config_), error);
}

bool MelonDsNetplayTransport::process_frame(const std::vector<uint8_t>& frame,
                                            std::vector<MelonDsNetplayEvent>& events,
                                            std::string& error) {
    if (frame.size() < kHeaderBytes || !std::equal(kMagic.begin(), kMagic.end(), frame.begin()) ||
        frame[8] == 0 || frame[8] > kReject) {
        error = "The peer sent a malformed melonDS LAN frame.";
        return false;
    }
    const uint8_t kind = frame[8];
    const int flags = static_cast<int>(read_u32(frame.data() + 9));
    const uint16_t client_id = read_u16(frame.data() + 13);
    const uint32_t length = read_u32(frame.data() + 15);
    if (length > kMaxPayloadBytes || frame.size() != kHeaderBytes + length) {
        error = "The peer sent an oversized or truncated melonDS LAN frame.";
        return false;
    }
    const auto payload_begin = frame.begin() + static_cast<std::ptrdiff_t>(kHeaderBytes);
    const std::vector<uint8_t> payload(payload_begin, frame.end());
    if (kind == kHello) {
        if (!listening_ || connected_) {
            error = "The melonDS LAN host received an unexpected second peer.";
            return false;
        }
        std::size_t offset = 0;
        std::string core, protocol, game;
        if (!read_field(payload, offset, core) || !read_field(payload, offset, protocol) ||
            !read_field(payload, offset, game) || offset != payload.size() ||
            core != config_.core_id || protocol != config_.protocol_version || game != config_.game_identity) {
            const std::string reason = "The peer's melonDS core, protocol, or game does not match.";
            std::vector<uint8_t> text(reason.begin(), reason.end());
            (void)queue_frame(kReject, 0, 0, text, error);
            error = reason;
            return false;
        }
        if (!queue_handshake(kHelloAck, error)) return false;
        connected_ = true;
        detail_ = "Connected directly to a matching melonDS LAN game";
        events.push_back({MelonDsNetplayEvent::Kind::Connected, 1, 0, {}, detail_});
        return true;
    }
    if (kind == kHelloAck) {
        if (listening_ || connected_) {
            error = "The melonDS LAN client received an unexpected handshake.";
            return false;
        }
        std::size_t offset = 0;
        std::string core, protocol, game;
        if (!read_field(payload, offset, core) || !read_field(payload, offset, protocol) ||
            !read_field(payload, offset, game) || offset != payload.size() ||
            core != config_.core_id || protocol != config_.protocol_version || game != config_.game_identity) {
            error = "The LAN multiplayer host rejected the melonDS core, protocol, or game.";
            events.push_back({MelonDsNetplayEvent::Kind::Rejected, 0, 0, {}, error});
            return false;
        }
        connected_ = true;
        detail_ = "Connected directly to a matching melonDS LAN game";
        events.push_back({MelonDsNetplayEvent::Kind::Connected, 0, 0, {}, detail_});
        return true;
    }
    if (kind == kReject) {
        error.assign(payload.begin(), payload.end());
        if (error.empty()) error = "The peer rejected the melonDS LAN session.";
        events.push_back({MelonDsNetplayEvent::Kind::Rejected, 0, 0, {}, error});
        return false;
    }
    if (kind == kBye) {
        disconnect(&events, "The melonDS LAN peer disconnected.");
        return true;
    }
    if (kind == kData) {
        if (!connected_) {
            error = "The peer sent game data before the melonDS LAN handshake completed.";
            return false;
        }
        if (client_id != 0xffff && client_id != (listening_ ? 0 : 1)) {
            error = "The peer addressed a different melonDS LAN player.";
            return false;
        }
        events.push_back({MelonDsNetplayEvent::Kind::Packet, static_cast<uint16_t>(listening_ ? 1 : 0), flags, payload, {}});
        return true;
    }
    error = "The peer sent an unknown melonDS LAN frame.";
    return false;
}

bool MelonDsNetplayTransport::read_frames(std::vector<MelonDsNetplayEvent>& events, std::string& error) {
    std::array<uint8_t, 8192> buffer{};
    for (;;) {
        const int received = static_cast<int>(recv(sockets_->connection,
            reinterpret_cast<char*>(buffer.data()), static_cast<int>(buffer.size()), 0));
        if (received > 0) {
            if (receive_buffer_.size() + static_cast<std::size_t>(received) > (kMaxPayloadBytes + kHeaderBytes) * 2) {
                error = "The melonDS LAN peer sent too much buffered data.";
                return false;
            }
            receive_buffer_.insert(receive_buffer_.end(), buffer.begin(), buffer.begin() + received);
            continue;
        }
        if (received == 0) {
            disconnect(&events, "The melonDS LAN peer disconnected.");
            return true;
        }
        if (would_block()) break;
        error = "The direct melonDS LAN session could not read a peer packet: " + socket_error();
        return false;
    }
    while (receive_buffer_.size() >= kHeaderBytes) {
        const uint32_t length = read_u32(receive_buffer_.data() + 15);
        if (length > kMaxPayloadBytes) {
            error = "The melonDS LAN peer announced an oversized packet.";
            return false;
        }
        const std::size_t frame_size = kHeaderBytes + length;
        if (receive_buffer_.size() < frame_size) break;
        std::vector<uint8_t> frame(receive_buffer_.begin(), receive_buffer_.begin() + frame_size);
        receive_buffer_.erase(receive_buffer_.begin(), receive_buffer_.begin() + static_cast<std::ptrdiff_t>(frame_size));
        if (!process_frame(frame, events, error)) return false;
    }
    return true;
}

bool MelonDsNetplayTransport::pump(std::vector<MelonDsNetplayEvent>& events, std::string& error) {
    if (!active_) return true;
    if (listening_ && sockets_->connection == kInvalidSocket && !accept_host(error)) return false;
    if (sockets_->connection == kInvalidSocket) return true;
    if (!read_frames(events, error)) {
        disconnect(&events, error);
        return false;
    }
    if (!flush(error)) {
        disconnect(&events, error);
        return false;
    }
    return true;
}

bool MelonDsNetplayTransport::send(int flags, const void* data, std::size_t length,
                                   uint16_t client_id, std::string& error) {
    if (!connected_) return false;
    if (!data && length != 0) {
        error = "The melonDS core supplied an invalid LAN packet.";
        return false;
    }
    if (client_id != 0xffff && client_id != (listening_ ? 1 : 0)) {
        error = "The melonDS core addressed an unsupported LAN player.";
        return false;
    }
    std::vector<uint8_t> payload;
    if (data && length) {
        const auto* bytes = static_cast<const uint8_t*>(data);
        payload.assign(bytes, bytes + length);
    }
    if (!queue_frame(kData, flags, client_id, payload, error)) {
        disconnect(nullptr, error);
        return false;
    }
    return true;
}

void MelonDsNetplayTransport::disconnect(std::vector<MelonDsNetplayEvent>* events,
                                         const std::string& detail) {
    const bool was_connected = connected_;
    connected_ = false;
    if (sockets_->connection != kInvalidSocket) {
        close_socket(sockets_->connection);
        sockets_->connection = kInvalidSocket;
    }
    transmit_queue_.clear();
    receive_buffer_.clear();
    detail_ = detail;
    if (events && was_connected) events->push_back({MelonDsNetplayEvent::Kind::Disconnected, static_cast<uint16_t>(listening_ ? 1 : 0), 0, {}, detail});
}

void MelonDsNetplayTransport::close() {
    if (!sockets_) return;
    if (sockets_->connection != kInvalidSocket) {
        // A best-effort close frame is enough; no shutdown path waits for it.
        std::vector<uint8_t> empty;
        std::string ignored;
        if (connected_) (void)queue_frame(kBye, 0, 0, empty, ignored);
        close_socket(sockets_->connection);
        sockets_->connection = kInvalidSocket;
    }
    close_socket(sockets_->listener);
    sockets_->listener = kInvalidSocket;
    receive_buffer_.clear();
    transmit_queue_.clear();
    transmit_offset_ = 0;
    active_ = false;
    listening_ = false;
    connected_ = false;
    handshake_sent_ = false;
    local_port_ = 0;
    detail_.clear();
}

} // namespace an3
