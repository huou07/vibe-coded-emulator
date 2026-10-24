// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstdint>
#include <cstddef>
#include <deque>
#include <string>
#include <vector>

namespace an3 {

// This transport is intentionally scoped to the melonDS DS libretro
// netpacket callback. It is not an AN3 sync/controller protocol and must not
// be reused for either of those features.
enum class MelonDsNetplayRole { Disabled, Host, Join };

struct MelonDsNetplayConfig {
    MelonDsNetplayRole role = MelonDsNetplayRole::Disabled;
    std::string address;
    uint16_t port = 47834;
    std::string core_id = "melonds-ds";
    std::string protocol_version;
    std::string game_identity;
};

struct MelonDsNetplayEvent {
    enum class Kind { Connected, Packet, Disconnected, Rejected };
    Kind kind = Kind::Disconnected;
    uint16_t client_id = 0;
    int flags = 0;
    std::vector<uint8_t> payload;
    std::string detail;
};

class MelonDsNetplayTransport {
public:
    MelonDsNetplayTransport();
    ~MelonDsNetplayTransport();
    MelonDsNetplayTransport(const MelonDsNetplayTransport&) = delete;
    MelonDsNetplayTransport& operator=(const MelonDsNetplayTransport&) = delete;

    bool open(const MelonDsNetplayConfig& config, std::string& error);
    void close();
    bool pump(std::vector<MelonDsNetplayEvent>& events, std::string& error);
    bool send(int flags, const void* data, std::size_t length, uint16_t client_id,
              std::string& error);

    bool active() const noexcept { return active_; }
    bool connected() const noexcept { return connected_; }
    bool listening() const noexcept { return listening_; }
    uint16_t local_port() const noexcept { return local_port_; }
    const std::string& detail() const noexcept { return detail_; }

private:
    struct SocketState;

    bool open_host(const MelonDsNetplayConfig& config, std::string& error);
    bool open_join(const MelonDsNetplayConfig& config, std::string& error);
    bool accept_host(std::string& error);
    bool read_frames(std::vector<MelonDsNetplayEvent>& events, std::string& error);
    bool process_frame(const std::vector<uint8_t>& frame,
                       std::vector<MelonDsNetplayEvent>& events, std::string& error);
    bool queue_frame(uint8_t kind, int flags, uint16_t client_id,
                     const std::vector<uint8_t>& payload, std::string& error);
    bool flush(std::string& error);
    bool queue_handshake(uint8_t kind, std::string& error);
    void disconnect(std::vector<MelonDsNetplayEvent>* events, const std::string& detail);

    SocketState* sockets_ = nullptr;
    MelonDsNetplayConfig config_;
    std::vector<uint8_t> receive_buffer_;
    std::deque<std::vector<uint8_t>> transmit_queue_;
    std::size_t transmit_offset_ = 0;
    bool active_ = false;
    bool listening_ = false;
    bool connected_ = false;
    bool handshake_sent_ = false;
    uint16_t local_port_ = 0;
    std::string detail_;
};

} // namespace an3
