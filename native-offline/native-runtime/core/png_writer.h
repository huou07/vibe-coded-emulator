// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
//
// Minimal, dependency-free PNG writer for deterministic test captures.
//
// It emits a valid 8-bit RGBA PNG using stored (uncompressed) DEFLATE blocks, a
// fixed filter type per scanline, and a stable byte layout with no timestamps,
// so the same pixels always produce the same file bytes. That determinism is
// what lets the control plane hash a capture and diff it against a baseline.

#include <cstdint>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

namespace an3 {

inline uint32_t png_crc32(const uint8_t* data, std::size_t length) {
    static uint32_t table[256];
    static bool ready = false;
    if (!ready) {
        for (uint32_t n = 0; n < 256; ++n) {
            uint32_t c = n;
            for (int k = 0; k < 8; ++k) c = (c & 1) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
            table[n] = c;
        }
        ready = true;
    }
    uint32_t crc = 0xFFFFFFFFu;
    for (std::size_t i = 0; i < length; ++i) crc = table[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    return crc ^ 0xFFFFFFFFu;
}

inline uint32_t png_adler32(const uint8_t* data, std::size_t length) {
    uint32_t a = 1, b = 0;
    for (std::size_t i = 0; i < length; ++i) {
        a = (a + data[i]) % 65521u;
        b = (b + a) % 65521u;
    }
    return (b << 16) | a;
}

inline void png_append_be32(std::vector<uint8_t>& out, uint32_t value) {
    out.push_back(static_cast<uint8_t>(value >> 24));
    out.push_back(static_cast<uint8_t>(value >> 16));
    out.push_back(static_cast<uint8_t>(value >> 8));
    out.push_back(static_cast<uint8_t>(value));
}

inline void png_write_chunk(std::vector<uint8_t>& out, const char type[4], const std::vector<uint8_t>& payload) {
    png_append_be32(out, static_cast<uint32_t>(payload.size()));
    const std::size_t crc_start = out.size();
    out.insert(out.end(), type, type + 4);
    out.insert(out.end(), payload.begin(), payload.end());
    const uint32_t crc = png_crc32(out.data() + crc_start, out.size() - crc_start);
    png_append_be32(out, crc);
}

// `rgba` is width*height*4 bytes. Returns true when the file was written.
inline bool write_png_rgba(const std::string& path, uint32_t width, uint32_t height,
                           const std::vector<uint8_t>& rgba, std::string& error) {
    if (!width || !height || rgba.size() < static_cast<std::size_t>(width) * height * 4u) {
        error = "capture buffer is smaller than the declared frame";
        return false;
    }
    // Raw image data: one filter byte (0 = None) per scanline, then RGBA pixels.
    std::vector<uint8_t> raw;
    raw.reserve(static_cast<std::size_t>(height) * (1u + static_cast<std::size_t>(width) * 4u));
    for (uint32_t y = 0; y < height; ++y) {
        raw.push_back(0);
        const uint8_t* row = rgba.data() + static_cast<std::size_t>(y) * width * 4u;
        raw.insert(raw.end(), row, row + static_cast<std::size_t>(width) * 4u);
    }
    // zlib stream with stored DEFLATE blocks.
    std::vector<uint8_t> zlib;
    zlib.push_back(0x78);
    zlib.push_back(0x01);
    std::size_t offset = 0;
    while (offset < raw.size()) {
        const std::size_t block = (raw.size() - offset) > 65535u ? 65535u : (raw.size() - offset);
        const bool last = (offset + block) >= raw.size();
        zlib.push_back(last ? 1 : 0);
        zlib.push_back(static_cast<uint8_t>(block & 0xFF));
        zlib.push_back(static_cast<uint8_t>((block >> 8) & 0xFF));
        const uint16_t inverse = static_cast<uint16_t>(~static_cast<uint16_t>(block));
        zlib.push_back(static_cast<uint8_t>(inverse & 0xFF));
        zlib.push_back(static_cast<uint8_t>((inverse >> 8) & 0xFF));
        zlib.insert(zlib.end(), raw.begin() + static_cast<std::ptrdiff_t>(offset),
                    raw.begin() + static_cast<std::ptrdiff_t>(offset + block));
        offset += block;
    }
    png_append_be32(zlib, png_adler32(raw.data(), raw.size()));

    std::vector<uint8_t> out;
    const uint8_t signature[8] = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    out.insert(out.end(), signature, signature + 8);
    {
        std::vector<uint8_t> ihdr;
        png_append_be32(ihdr, width);
        png_append_be32(ihdr, height);
        ihdr.push_back(8);  // bit depth
        ihdr.push_back(6);  // color type: RGBA
        ihdr.push_back(0);  // compression
        ihdr.push_back(0);  // filter
        ihdr.push_back(0);  // interlace
        png_write_chunk(out, "IHDR", ihdr);
    }
    png_write_chunk(out, "IDAT", zlib);
    png_write_chunk(out, "IEND", {});

    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    if (!file) {
        error = "could not open capture path for writing";
        return false;
    }
    file.write(reinterpret_cast<const char*>(out.data()), static_cast<std::streamsize>(out.size()));
    if (!file) {
        error = "could not write capture bytes";
        return false;
    }
    return true;
}

// Raw RGBA dump for exact-pixel hashing without PNG framing.
inline bool write_raw_rgba(const std::string& path, const std::vector<uint8_t>& rgba, std::string& error) {
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    if (!file) {
        error = "could not open raw capture path for writing";
        return false;
    }
    file.write(reinterpret_cast<const char*>(rgba.data()), static_cast<std::streamsize>(rgba.size()));
    if (!file) {
        error = "could not write raw capture bytes";
        return false;
    }
    return true;
}

} // namespace an3
