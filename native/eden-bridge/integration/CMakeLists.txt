# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Integration target: included from Eden's top-level CMakeLists.txt so the
# Eden-backed bridge is compiled and linked against Eden's `core` target.
# Configure Eden with -DAN3_EDEN_BRIDGE_DIR=<repo>/native/eden-bridge and append
# this line to Eden's CMakeLists.txt:
#   add_subdirectory("${AN3_EDEN_BRIDGE_DIR}/integration" an3_eden_bridge)
if(NOT DEFINED AN3_EDEN_BRIDGE_DIR)
    message(FATAL_ERROR "AN3_EDEN_BRIDGE_DIR must point at <repo>/native/eden-bridge")
endif()

add_library(an3_eden_bridge STATIC
    "${AN3_EDEN_BRIDGE_DIR}/src/an3_eden_bridge.cpp"
    "${AN3_EDEN_BRIDGE_DIR}/src/backend_eden.cpp"
)
target_include_directories(an3_eden_bridge
    PUBLIC "${AN3_EDEN_BRIDGE_DIR}/include"
    PRIVATE "${AN3_EDEN_BRIDGE_DIR}/src"
    # Eden's headers are not exported by its `core` target; include its source
    # root explicitly (this file is included from Eden's top-level CMakeLists).
    PRIVATE "${CMAKE_SOURCE_DIR}/src"
)
target_link_libraries(an3_eden_bridge PRIVATE frontend_common)
target_compile_features(an3_eden_bridge PUBLIC cxx_std_20)

# libcommon's power-status code needs IOKit on macOS.
if(APPLE)
    target_link_libraries(an3_eden_bridge PRIVATE "-framework IOKit")
endif()

# Eden's own GPU dependency (FetchContent external project). Link it explicitly
# because the standalone target does not inherit it through `core`.
if(TARGET GPUOpen::VulkanMemoryAllocator)
    target_link_libraries(an3_eden_bridge PRIVATE GPUOpen::VulkanMemoryAllocator)
elseif(TARGET VulkanMemoryAllocator)
    target_link_libraries(an3_eden_bridge PRIVATE VulkanMemoryAllocator)
endif()

add_executable(an3_eden_bridge_smoke "${AN3_EDEN_BRIDGE_DIR}/tests/bridge_smoke.c")
target_link_libraries(an3_eden_bridge_smoke PRIVATE an3_eden_bridge)

# A weak reference to a base-class typeinfo does not pull the archive member on
# macOS, so load Eden's core objects explicitly.
if(TARGET core)
    target_link_options(an3_eden_bridge_smoke PRIVATE "LINKER:-force_load,$<TARGET_FILE:core>")
endif()
