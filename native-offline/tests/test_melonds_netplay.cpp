// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "../native-runtime/core/melonds_netplay.h"

#include <cassert>
#include <chrono>
#include <cstdint>
#include <string>
#include <thread>
#include <vector>

using an3::MelonDsNetplayConfig;
using an3::MelonDsNetplayEvent;
using an3::MelonDsNetplayRole;
using an3::MelonDsNetplayTransport;

int main() {
    constexpr uint16_t port = 48973;
    MelonDsNetplayConfig host_config;
    host_config.role = MelonDsNetplayRole::Host;
    host_config.port = port;
    host_config.protocol_version = "test-protocol";
    host_config.game_identity = "fixture-rom-hash";

    MelonDsNetplayConfig client_config = host_config;
    client_config.role = MelonDsNetplayRole::Join;
    client_config.address = "127.0.0.1";

    MelonDsNetplayTransport host;
    MelonDsNetplayTransport client;
    std::string error;
    assert(host.open(host_config, error));
    assert(client.open(client_config, error));

    bool host_connected = false;
    bool client_connected = false;
    for (int attempt = 0; attempt < 200 && (!host_connected || !client_connected); ++attempt) {
        std::vector<MelonDsNetplayEvent> host_events;
        std::vector<MelonDsNetplayEvent> client_events;
        assert(host.pump(host_events, error));
        assert(client.pump(client_events, error));
        for (const auto& event : host_events) host_connected |= event.kind == MelonDsNetplayEvent::Kind::Connected;
        for (const auto& event : client_events) client_connected |= event.kind == MelonDsNetplayEvent::Kind::Connected;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    assert(host_connected && client_connected);

    const std::string fixture = "official-libretro-netpacket-path";
    assert(client.send(1, fixture.data(), fixture.size(), 0, error));
    bool received = false;
    for (int attempt = 0; attempt < 100 && !received; ++attempt) {
        std::vector<MelonDsNetplayEvent> events;
        assert(host.pump(events, error));
        for (const auto& event : events) {
            if (event.kind == MelonDsNetplayEvent::Kind::Packet) {
                received = std::string(event.payload.begin(), event.payload.end()) == fixture &&
                    event.client_id == 1 && event.flags == 1;
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    assert(received);

    host.close();
    client.close();
    MelonDsNetplayConfig host2_config = host_config;
    host2_config.port = static_cast<uint16_t>(port + 1);
    MelonDsNetplayTransport host2;
    assert(host2.open(host2_config, error));
    MelonDsNetplayConfig mismatch = client_config;
    mismatch.port = static_cast<uint16_t>(port + 1);
    mismatch.game_identity = "different-game";
    MelonDsNetplayTransport rejected;
    assert(rejected.open(mismatch, error));
    bool rejected_seen = false;
    for (int attempt = 0; attempt < 100 && !rejected_seen; ++attempt) {
        std::vector<MelonDsNetplayEvent> events;
        const bool host_ok = host2.pump(events, error);
        (void)rejected.pump(events, error);
        rejected_seen = !host_ok && error.find("does not match") != std::string::npos;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    assert(rejected_seen);
    rejected.close();
    host2.close();

    MelonDsNetplayConfig public_address = client_config;
    public_address.address = "8.8.8.8";
    public_address.port = port;
    MelonDsNetplayTransport public_peer;
    assert(!public_peer.open(public_address, error));
    assert(error.find("private") != std::string::npos || error.find("local") != std::string::npos);
    return 0;
}
