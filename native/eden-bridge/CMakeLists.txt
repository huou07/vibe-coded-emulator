# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Standalone build for the Eden bridge. It builds and tests without Eden; with
# -DAN3_EDEN_ENABLED=ON it links the Eden backend (see README.md).
cmake_minimum_required(VERSION 3.20)
project(an3_eden_bridge C CXX)

option(AN3_EDEN_ENABLED "Build the Eden-backed bridge backend" OFF)
set(AN3_EDEN_ROOT "" CACHE PATH "Path to an Eden source checkout (required with AN3_EDEN_ENABLED=ON)")

add_library(an3_eden_bridge STATIC
    src/an3_eden_bridge.cpp
)
target_include_directories(an3_eden_bridge PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include" PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_compile_features(an3_eden_bridge PUBLIC cxx_std_17)

if(AN3_EDEN_ENABLED)
    if(NOT AN3_EDEN_ROOT)
        message(FATAL_ERROR "AN3_EDEN_ENABLED=ON requires AN3_EDEN_ROOT=/path/to/eden")
    endif()
    target_sources(an3_eden_bridge PRIVATE src/backend_eden.cpp)
    target_compile_definitions(an3_eden_bridge PUBLIC AN3_EDEN_ENABLED=1)
    # The Eden backend is compiled inside Eden's own build tree so it can link
    # Eden's `core` target; see README.md for the current status.
    target_include_directories(an3_eden_bridge PRIVATE "${AN3_EDEN_ROOT}/src")
else()
    target_sources(an3_eden_bridge PRIVATE src/backend_null.cpp)
endif()

enable_testing()
add_executable(an3_eden_bridge_smoke tests/bridge_smoke.c)
target_link_libraries(an3_eden_bridge_smoke PRIVATE an3_eden_bridge)
add_test(NAME an3_eden_bridge_smoke COMMAND an3_eden_bridge_smoke)

# Hosted-frame consumer harness (macOS only): a separate process that attaches
# to the producer's shared-memory ring and imports each published IOSurface as
# an MTLTexture. It never links Eden, proving the out-of-process boundary.
if(APPLE)
    enable_language(OBJCXX)
    add_executable(an3_eden_hosted_consumer
        tests/hosted_frame_consumer.mm
        src/an3_eden_hosted_frame.c
        src/an3_eden_hosted_frame_shm.c
    )
    target_include_directories(an3_eden_hosted_consumer PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/include")
    target_compile_features(an3_eden_hosted_consumer PRIVATE cxx_std_17)
    set_source_files_properties(tests/hosted_frame_consumer.mm PROPERTIES
        COMPILE_OPTIONS "-fobjc-arc")
    target_link_libraries(an3_eden_hosted_consumer PRIVATE
        "-framework Foundation" "-framework Metal" "-framework IOSurface")
endif()
