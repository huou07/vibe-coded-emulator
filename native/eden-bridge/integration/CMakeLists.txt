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
    # VMA is header-only and Eden only instantiates it in its frontends, which
    # this build disables; supply the single implementation object ourselves.
    "${CMAKE_CURRENT_SOURCE_DIR}/vma_impl.cpp"
)

# Eden's Vulkan renderer requires a Cocoa CAMetalLayer on macOS; the bridge
# creates an offscreen one.
if(APPLE)
    target_sources(an3_eden_bridge PRIVATE "${AN3_EDEN_BRIDGE_DIR}/src/cocoa_surface.mm")
endif()
target_include_directories(an3_eden_bridge
    PUBLIC "${AN3_EDEN_BRIDGE_DIR}/include"
    PRIVATE "${AN3_EDEN_BRIDGE_DIR}/src"
    # Eden's headers are not exported by its `core` target; include its source
    # root explicitly (this file is included from Eden's top-level CMakeLists).
    PRIVATE "${CMAKE_SOURCE_DIR}/src"
)
# Eden compiles every target with -fno-rtti (src/CMakeLists.txt), so `core`
# emits no `typeinfo for Core::Frontend::EmuWindow`. A derived class that keeps
# RTTI would reference a symbol that does not exist; the bridge uses no RTTI.
target_compile_options(an3_eden_bridge PRIVATE
    $<$<COMPILE_LANGUAGE:CXX>:-fno-rtti>
)
# Link Eden's `core` properly so its PRIVATE dependencies (video_core, audio_core,
# hid_core, network, dynarmic, ...) are pulled in transitively. `video_core`
# PUBLIC-links the Vulkan headers and GPUOpen::VulkanMemoryAllocator.
# input_common/hid_core are linked explicitly because the bridge drives the
# virtual_gamepad engine through the ABI.
target_link_libraries(an3_eden_bridge PRIVATE core frontend_common)
foreach(_an3_eden_target IN ITEMS input_common hid_core)
    if(TARGET ${_an3_eden_target})
        target_link_libraries(an3_eden_bridge PRIVATE ${_an3_eden_target})
    endif()
endforeach()
target_compile_features(an3_eden_bridge PUBLIC cxx_std_20)

# libcommon's power-status code needs IOKit on macOS.
if(APPLE)
    target_link_libraries(an3_eden_bridge PRIVATE "-framework IOKit")
    # Hosted CAMetalLayer surface (cocoa_surface.mm): AppKit hosts the hidden
    # window/view that gives the layer a real size and recycles drawables.
    target_link_libraries(an3_eden_bridge PRIVATE
        "-framework AppKit" "-framework Metal" "-framework QuartzCore" "-framework Foundation")
endif()

# Eden's own GPU dependencies (FetchContent external projects). Link them
# explicitly: `core` links `video_core` PRIVATE, so their PUBLIC usage
# requirements (Vulkan and VMA headers) do not reach this target's compiles.
# vma_impl.cpp includes video_core/vulkan_common/vma.h, which needs Vulkan.
foreach(_an3_vk_target IN ITEMS Vulkan::Headers Vulkan::UtilityHeaders
                                GPUOpen::VulkanMemoryAllocator VulkanMemoryAllocator)
    if(TARGET ${_an3_vk_target})
        target_link_libraries(an3_eden_bridge PRIVATE ${_an3_vk_target})
    endif()
endforeach()

add_executable(an3_eden_bridge_smoke "${AN3_EDEN_BRIDGE_DIR}/tests/bridge_smoke.c")
target_link_libraries(an3_eden_bridge_smoke PRIVATE an3_eden_bridge)

# Separate-process companion that ships Switch support: it owns its own window,
# input and lifecycle; AN3 launches it (never links Eden into the AN3 binary).
add_executable(an3_switch_companion "${AN3_EDEN_BRIDGE_DIR}/companion/main.cpp")
target_link_libraries(an3_switch_companion PRIVATE an3_eden_bridge)
target_include_directories(an3_switch_companion PRIVATE "${AN3_EDEN_BRIDGE_DIR}/src")
