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
    # Versioned hosted-frame protocol + bounded ring (pure C).
    "${AN3_EDEN_BRIDGE_DIR}/src/an3_eden_hosted_frame.c"
    # VMA is header-only and Eden only instantiates it in its frontends, which
    # this build disables; supply the single implementation object ourselves.
    "${CMAKE_CURRENT_SOURCE_DIR}/vma_impl.cpp"
)

# The hosted-frame shared-memory path is used only by the desktop/macOS
# out-of-process presentation harness. Android presents directly through its
# ANativeWindow and does not expose POSIX shm_open/shm_unlink in the NDK libc.
if(NOT ANDROID AND NOT WIN32)
    target_sources(an3_eden_bridge PRIVATE
        "${AN3_EDEN_BRIDGE_DIR}/src/an3_eden_hosted_frame_shm.c")
endif()

# Eden's upstream SDL3 frontend is the supported native window/input adapter
# for non-Apple desktop targets. Android uses Eden's ANativeWindow frontend and
# macOS keeps the hosted Cocoa/CAMetalLayer path below.
if(WIN32 OR (UNIX AND NOT APPLE AND NOT ANDROID))
    target_sources(an3_eden_bridge PRIVATE
        "${AN3_EDEN_BRIDGE_DIR}/src/desktop_surface.cpp")
endif()

# Eden's Vulkan renderer requires a Cocoa CAMetalLayer on macOS; the bridge
# creates an offscreen one.
if(APPLE)
    target_sources(an3_eden_bridge PRIVATE
        "${AN3_EDEN_BRIDGE_DIR}/src/cocoa_surface.mm"
        # Hosted-frame producer: implements the weak hook Eden's swapchain calls
        # and publishes the presented frame's IOSurface metadata.
        "${AN3_EDEN_BRIDGE_DIR}/src/hosted_frame_producer.cpp")
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
if(WIN32 OR (UNIX AND NOT APPLE AND NOT ANDROID))
    target_link_libraries(an3_eden_bridge PRIVATE SDL3::SDL3)
endif()
target_compile_features(an3_eden_bridge PUBLIC cxx_std_20)

# libcommon's power-status code needs IOKit on macOS.
if(APPLE)
    target_link_libraries(an3_eden_bridge PRIVATE "-framework IOKit")
    # Hosted CAMetalLayer surface (cocoa_surface.mm): AppKit hosts the hidden
    # window/view that gives the layer a real size and recycles drawables.
    target_link_libraries(an3_eden_bridge PRIVATE
        "-framework AppKit" "-framework Metal" "-framework QuartzCore" "-framework Foundation"
        "-framework IOSurface" "-framework CoreFoundation")
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

if(NOT ANDROID)
    add_executable(an3_eden_bridge_smoke "${AN3_EDEN_BRIDGE_DIR}/tests/bridge_smoke.c")
endif()

# Separate-process companion that ships Switch support: it owns its own window,
# input and lifecycle; AN3 launches it (never links Eden into the AN3 binary).
if(NOT ANDROID)
    add_executable(an3_switch_companion "${AN3_EDEN_BRIDGE_DIR}/companion/main.cpp")
    target_include_directories(an3_switch_companion PRIVATE "${AN3_EDEN_BRIDGE_DIR}/src")
    if(WIN32 OR (UNIX AND NOT APPLE AND NOT ANDROID))
        target_link_libraries(an3_switch_companion PRIVATE SDL3::SDL3)
    endif()
endif()

# The upstream Eden libraries are static and have intentional circular
# dependencies (for example core -> frontend_common -> PlayTime, while the
# bridge's VMA implementation is referenced from video_core).  A plain
# target_link_libraries() order is therefore insufficient on ELF platforms:
# the linker can discard an archive before a later archive introduces its
# references.  Keep the bridge's dependency closure in one deterministic
# RESCAN group so both the smoke binary and the shipped companion are
# genuinely linkable rather than merely compilable.
if(NOT ANDROID)
    if(UNIX AND NOT APPLE)
        # Keep this as raw linker flags rather than CMake's LINK_GROUP
        # generator expression.  Eden's transitive static-target graph is
        # itself cyclic (core <-> video/audio frontend targets), which makes a
        # LINK_GROUP target dependency graph cyclic before the linker runs.
        target_link_libraries(an3_eden_bridge_smoke PRIVATE
            "-Wl,--start-group" an3_eden_bridge frontend_common input_common
            core hid_core audio_core video_core "-Wl,--end-group")
        target_link_libraries(an3_switch_companion PRIVATE
            "-Wl,--start-group" an3_eden_bridge frontend_common input_common
            core hid_core audio_core video_core "-Wl,--end-group")
    else()
        # Static-library PRIVATE dependencies do not become link inputs for
        # a separate consumer on all desktop generators.  The bridge drives
        # Eden's virtual gamepad directly, so keep input_common explicit for
        # the macOS and Windows companion/smoke executables as well.
        if(WIN32)
            # The MinGW archive tool on the Windows builder can emit an
            # incomplete Sirit archive when the object-library members are
            # passed through CMake's static-library rule. Link those members
            # directly into the two AN3 executables; the upstream shader
            # recompiler still supplies the public Eden implementation.
            if(TARGET siritobj)
                target_sources(an3_eden_bridge_smoke PRIVATE $<TARGET_OBJECTS:siritobj>)
                target_sources(an3_switch_companion PRIVATE $<TARGET_OBJECTS:siritobj>)
            endif()
            # The MinGW build of Eden contains mutually dependent static
            # archives, and its network-interface implementation calls the
            # Windows IP helper API.  Keep the bridge/core closure in a
            # rescan group and link the narrow system dependency explicitly.
            target_link_libraries(an3_eden_bridge_smoke PRIVATE
                "-Wl,--start-group" an3_eden_bridge input_common frontend_common
                core hid_core audio_core video_core shader_recompiler
                $<$<TARGET_EXISTS:sirit>:sirit>
                "-Wl,--end-group" iphlpapi)
            target_link_libraries(an3_switch_companion PRIVATE
                "-Wl,--start-group" an3_eden_bridge input_common frontend_common
                core hid_core audio_core video_core shader_recompiler
                $<$<TARGET_EXISTS:sirit>:sirit>
                "-Wl,--end-group" iphlpapi)
        else()
            target_link_libraries(an3_eden_bridge_smoke PRIVATE an3_eden_bridge input_common)
            target_link_libraries(an3_switch_companion PRIVATE an3_eden_bridge input_common)
        endif()
    endif()
endif()
